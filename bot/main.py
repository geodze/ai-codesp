import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from .config import ALLOWED_USER_IDS, BOT_TOKEN, MODE, PORT, WEBHOOK_PATH, WEBHOOK_URL
from .handlers import router
from .storage import storage
from .wizard import wizard_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _build_bot() -> Bot:
    return Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def _build_dispatcher() -> Dispatcher:
    # MemoryStorage is fine — wizard FSM only holds short-lived "awaiting input"
    # states; if the bot restarts mid-onboarding the user just taps the button
    # again. No need for a Redis/SQLite FSM backend.
    dp = Dispatcher(storage=MemoryStorage())
    # Wizard router goes first so its /start, /setup and callback queries win
    # over the generic handlers in `router`.
    dp.include_router(wizard_router)
    dp.include_router(router)
    return dp


async def _health(_: web.Request) -> web.Response:
    return web.Response(text="ok")


async def _run_polling() -> None:
    """Long-polling mode + a tiny aiohttp server for cloud health checks.

    Render free, Railway, Fly etc. usually require a process to bind a port
    so they know the deploy is healthy. A 200-OK on ``/`` and ``/healthz`` is
    enough; we keep the same paths the webhook mode exposes.
    """
    bot = _build_bot()
    dp = _build_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)

    health_app = web.Application()
    health_app.router.add_get("/", _health)
    health_app.router.add_get("/healthz", _health)
    runner = web.AppRunner(health_app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    logger.info("health server listening on 0.0.0.0:%s", PORT)

    logger.info("starting polling")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
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
    owner = storage.get_owner_id()
    if owner is None and not ALLOWED_USER_IDS:
        logger.info(
            "No owner claimed yet and ALLOWED_USER_IDS is empty. "
            "First user to send /start in Telegram becomes the owner."
        )
    elif owner is not None:
        logger.info("Owner already claimed: telegram id %s", owner)

    # Webhook mode requires PUBLIC_URL. If the user picked webhook but didn't
    # set the URL (typical right after a one-click cloud deploy), silently
    # fall back to polling so the bot still comes up.
    if MODE == "webhook" and not WEBHOOK_URL:
        logger.warning(
            "BOT_MODE=webhook but PUBLIC_URL is empty — falling back to polling. "
            "Set PUBLIC_URL=https://<your-host> to switch back."
        )
        asyncio.run(_run_polling())
    elif MODE == "polling":
        asyncio.run(_run_polling())
    else:
        _run_webhook()


if __name__ == "__main__":
    main()
