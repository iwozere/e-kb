"""Access middleware: ensures a User record exists before every update.

v2: No billing, no subscription checks.  All users are allowed.
    Admin check happens inside individual handlers/commands that require it.
"""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.db.session import AsyncSessionLocal
from bot.services.users import get_or_create_user

logger = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    """Ensure a user row exists for every incoming update."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        async with AsyncSessionLocal() as session:
            await get_or_create_user(
                session,
                tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
            )

        return await handler(event, data)
