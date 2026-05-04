import asyncio
import logging
import random

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from .config import (
    ALLOWED_USER_IDS,
    BOT_TOKEN,
    KEEP_ALIVE_BIAS,
    KEEP_ALIVE_INTERVAL,
    KEEP_ALIVE_MAX_SECONDS,
    KEEP_ALIVE_MIN_SECONDS,
    KEEP_ALIVE_URL,
    MODE,
    PORT,
    WEBHOOK_PATH,
    WEBHOOK_URL,
)
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


def _next_keepalive_delay() -> float:
    """Compute the next ping delay in seconds.

    Three modes:
      * ``KEEP_ALIVE_INTERVAL`` is a positive int → fixed interval.
      * ``KEEP_ALIVE_INTERVAL`` is ``None`` (default, env var unset) →
        random delay in ``[MIN, MAX]`` with ``BIAS`` probability of
        landing in the upper half (closer to ``MAX``). This makes the
        ping pattern look human-ish rather than a fixed cron tick.
      * ``KEEP_ALIVE_INTERVAL == 0`` → disabled (caller short-circuits).
    """
    if KEEP_ALIVE_INTERVAL is not None and KEEP_ALIVE_INTERVAL > 0:
        return float(KEEP_ALIVE_INTERVAL)
    midpoint = (KEEP_ALIVE_MIN_SECONDS + KEEP_ALIVE_MAX_SECONDS) / 2
    if random.random() < KEEP_ALIVE_BIAS:
        return random.uniform(midpoint, KEEP_ALIVE_MAX_SECONDS)
    return random.uniform(KEEP_ALIVE_MIN_SECONDS, midpoint)


async def _keep_alive_loop() -> None:
    """Periodically GET our own ``/healthz`` to keep Render Free awake.

    Render counts only *incoming* HTTP traffic toward the 15-minute idle
    timer — the bot's outgoing Telegram polling doesn't qualify. Hitting
    our own public URL through the platform's load balancer DOES count.

    Disabled when no URL was resolved (local dev, VPS) or when
    ``KEEP_ALIVE_INTERVAL`` is explicitly set to ``0``.
    """
    if not KEEP_ALIVE_URL or KEEP_ALIVE_INTERVAL == 0:
        return
    target = f"{KEEP_ALIVE_URL}/healthz"
    if KEEP_ALIVE_INTERVAL is not None and KEEP_ALIVE_INTERVAL > 0:
        logger.info(
            "keep-alive: pinging %s every %ss (fixed)", target, KEEP_ALIVE_INTERVAL
        )
    else:
        logger.info(
            "keep-alive: pinging %s every %d-%ds (%.0f%% bias toward upper end)",
            target,
            KEEP_ALIVE_MIN_SECONDS,
            KEEP_ALIVE_MAX_SECONDS,
            KEEP_ALIVE_BIAS * 100,
        )
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # First ping after a short grace period so the health server has
        # time to bind and the platform DNS to resolve our URL.
        await asyncio.sleep(min(_next_keepalive_delay(), 30))
        while True:
            try:
                async with session.get(target) as resp:
                    if resp.status >= 400:
                        logger.warning(
                            "keep-alive ping returned HTTP %s", resp.status
                        )
            except Exception as exc:  # noqa: BLE001 — log everything, retry forever
                logger.warning("keep-alive ping failed: %s", exc)
            await asyncio.sleep(_next_keepalive_delay())


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

    keepalive_task = asyncio.create_task(_keep_alive_loop())
    logger.info("starting polling")
    try:
        await dp.start_polling(bot)
    finally:
        keepalive_task.cancel()
        try:
            await keepalive_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
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
