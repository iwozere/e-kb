"""Bot entry point — dispatcher setup, middleware, scheduler, polling/webhook."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from sqlalchemy import select

from bot.db.models import User
from bot.db.session import AsyncSessionLocal
import bot.handlers.admin as admin
import bot.handlers.ask as ask
import bot.handlers.delete as delete
import bot.handlers.draft as draft
import bot.handlers.export as export
import bot.handlers.log as log
import bot.handlers.profile as profile
import bot.handlers.search as search
import bot.handlers.start as start
import bot.handlers.summary as summary
import bot.handlers.text_note as text_note
import bot.handlers.voice as voice
import bot.services.scheduler as sched
from bot.utils.config import settings
from bot.utils.middleware import AccessMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


async def _fetch_first_names(user_ids: list[int]) -> dict[int, str]:
    """Look up first_names for admin users from the DB (best-effort)."""
    if not user_ids:
        return {}
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User.id, User.first_name).where(User.id.in_(user_ids))
        )
        return {row[0]: row[1] or "User" for row in result.fetchall()}


async def main() -> None:
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # ── Middleware ────────────────────────────────────────────────────────────
    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())

    # ── Routers (order matters: specific before catch-all) ────────────────────
    dp.include_router(start.router)      # /start /help /status
    dp.include_router(ask.router)        # /ask
    dp.include_router(draft.router)      # /draft + save_example/regen callbacks
    dp.include_router(log.router)        # /log
    dp.include_router(summary.router)    # /day /summary
    dp.include_router(search.router)     # /search
    dp.include_router(delete.router)     # /delete + confirm/cancel callbacks
    dp.include_router(profile.router)    # /profile
    dp.include_router(export.router)     # /export
    dp.include_router(admin.router)      # /admin_stats
    dp.include_router(voice.router)      # voice messages
    dp.include_router(text_note.router)  # plain text (catch-all — must be last)

    # ── Register bot commands (shows in Telegram UI / BotFather list) ────────
    await bot.set_my_commands([
        BotCommand(command="start",       description="Welcome & full command list"),
        BotCommand(command="help",        description="Command list"),
        BotCommand(command="ask",         description="Ask your AI clone anything"),
        BotCommand(command="search",      description="Semantic search your notes"),
        BotCommand(command="log",         description="Structured log: /log book|health|sport …"),
        BotCommand(command="draft",       description="Draft email reply in your style"),
        BotCommand(command="profile",     description="View or update your profile & writing style"),
        BotCommand(command="day",         description="Generate today's digest"),
        BotCommand(command="summary",     description="Generate weekly digest"),
        BotCommand(command="status",      description="Note count & streak"),
        BotCommand(command="export",      description="Download all notes as Markdown"),
        BotCommand(command="delete",      description="Delete an entry by ID"),
    ])
    logger.info("Bot commands registered.")

    # ── Scheduler ────────────────────────────────────────────────────────────
    first_names = await _fetch_first_names(settings.admins)
    for uid in settings.admins:
        first_names.setdefault(uid, "User")

    sched.setup_schedules(bot, settings.admins, first_names)
    sched.start()

    # ── Start polling or webhook ──────────────────────────────────────────────
    try:
        if settings.webhook_host:
            await _run_webhook(bot, dp)
        else:
            logger.info("Starting in polling mode.")
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot)
    finally:
        sched.stop()
        await bot.session.close()


async def _run_webhook(bot: Bot, dp: Dispatcher) -> None:
    from aiohttp import web  # noqa: PLC0415
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application  # noqa: PLC0415

    webhook_url = f"{settings.webhook_host}{settings.webhook_path}"
    await bot.set_webhook(
        url=webhook_url,
        allowed_updates=dp.resolve_used_update_types(),
    )
    logger.info("Webhook set: %s", webhook_url)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.web_port)
    await site.start()
    logger.info("Webhook server on :%s", settings.web_port)

    await asyncio.Event().wait()  # run until interrupted


if __name__ == "__main__":
    asyncio.run(main())
