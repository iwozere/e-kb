"""Access middleware: restricts the bot to configured admins only.

v2 pivoted to a personal tool — this bot is not meant for the public.
Anyone not listed in ``config.yaml``'s ``admins:`` is dropped silently before
any handler, DB write, or LLM call runs (so a stranger can't rack up
Anthropic/OpenAI usage or learn the bot exists/does anything).

Per-admin data isolation is handled elsewhere: every query in
bot/services and bot/handlers is scoped by ``user_id`` (see Entry,
UserProfile, EmailExample — all keyed off the caller's Telegram id), so each
admin already only ever sees their own entries. This middleware only gates
*entry* to the bot.
"""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.db.session import AsyncSessionLocal
from bot.services.users import get_or_create_user
from bot.utils.config import settings

logger = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    """Drop any update from a user not in settings.admins; upsert admins."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        if tg_user.id not in settings.admins:
            logger.info(
                "Rejected update from non-admin user_id=%s (@%s)",
                tg_user.id,
                tg_user.username,
            )
            return  # silently ignore — no reply, no DB write, no LLM call

        async with AsyncSessionLocal() as session:
            await get_or_create_user(
                session,
                tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
            )

        return await handler(event, data)
