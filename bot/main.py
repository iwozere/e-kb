import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import text as sql_text

from bot.db.session import engine
import bot.handlers.admin as admin
import bot.handlers.export as export
import bot.handlers.payment as payment
import bot.handlers.search as search
import bot.handlers.start as start
import bot.handlers.summary as summary
import bot.handlers.text_note as text_note
import bot.handlers.voice as voice
from bot.utils.config import settings
from bot.utils.middleware import AccessMiddleware

logger = logging.getLogger(__name__)


def _build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.middleware(AccessMiddleware())
    dp.include_router(start.router)
    dp.include_router(voice.router)
    dp.include_router(text_note.router)
    dp.include_router(search.router)
    dp.include_router(summary.router)
    dp.include_router(export.router)
    dp.include_router(admin.router)
    return dp


async def _init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
    logger.info("pgvector extension ensured")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    await _init_db()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = _build_dispatcher()

    # Always start a web server so Stripe webhooks can reach the bot
    stripe_handler = payment.stripe_webhook_handler(bot)
    app = web.Application()
    app.router.add_post("/stripe-webhook", stripe_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("Web server started on :8080 (Stripe webhook at /stripe-webhook)")

    if settings.webhook_host:
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

        webhook_url = f"{settings.webhook_host}{settings.webhook_path}"
        await bot.set_webhook(webhook_url)
        logger.info("Webhook set: %s", webhook_url)

        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.webhook_path)
        setup_application(app, dp, bot=bot)

        # Block forever — aiohttp runner is already serving
        await asyncio.Event().wait()
    else:
        logger.info("Starting polling…")
        try:
            await dp.start_polling(bot)
        finally:
            await runner.cleanup()
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
