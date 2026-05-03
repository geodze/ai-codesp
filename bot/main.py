import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from .config import ALLOWED_USER_IDS, BOT_TOKEN, MODE, PORT, WEBHOOK_PATH, WEBHOOK_URL
from .handlers import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _build_bot() -> Bot:
    return Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def _health(_: web.Request) -> web.Response:
    return web.Response(text="ok")


async def _run_polling() -> None:
    bot = _build_bot()
    dp = _build_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("starting polling")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def _run_webhook() -> None:
    if not WEBHOOK_URL:
        raise RuntimeError(
            "PUBLIC_URL is not set; cannot run in webhook mode. "
            "Set BOT_MODE=polling or provide PUBLIC_URL."
        )

    bot = _build_bot()
    dp = _build_dispatcher()

    async def _on_startup(app: web.Application) -> None:
        logger.info("setting webhook to %s", WEBHOOK_URL)
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

    async def _on_cleanup(app: web.Application) -> None:
        logger.info("removing webhook")
        try:
            await bot.delete_webhook()
        finally:
            await bot.session.close()

    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/healthz", _health)
    SimpleRequestHandler(dp, bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    logger.info("starting webhook server on 0.0.0.0:%s, path %s", PORT, WEBHOOK_PATH)
    web.run_app(app, host="0.0.0.0", port=PORT)


def main() -> None:
    if not ALLOWED_USER_IDS:
        logger.warning(
            "ALLOWED_USER_IDS is empty — every Telegram user will be DENIED. "
            "Set ALLOWED_USER_IDS=<your_id> in env."
        )
    if MODE == "polling":
        asyncio.run(_run_polling())
    else:
        _run_webhook()


if __name__ == "__main__":
    main()
