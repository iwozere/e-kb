import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot.db.session import AsyncSessionLocal
from bot.services.billing import (
    can_access,
    get_entry_count,
    get_or_create_user,
    make_payment_token,
)
from bot.utils.config import settings

logger = logging.getLogger(__name__)

_FREE_COMMANDS = frozenset({"/start", "/help", "/status"})


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        user_id: int = tg_user.id

        # Free commands bypass billing but still need user record
        is_free_command = False
        if isinstance(event, Message) and event.text and event.text.startswith("/"):
            cmd = event.text.split()[0].split("@")[0].lower()
            is_free_command = cmd in _FREE_COMMANDS

        # Admins are always allowed
        if user_id in settings.admins:
            async with AsyncSessionLocal() as session:
                await get_or_create_user(session, user_id, tg_user.username, tg_user.first_name)
            return await handler(event, data)

        async with AsyncSessionLocal() as session:
            await get_or_create_user(session, user_id, tg_user.username, tg_user.first_name)

            if is_free_command or not settings.billing.enabled:
                return await handler(event, data)

            allowed, reason = await can_access(session, user_id)

            if allowed:
                return await handler(event, data)

            # Access denied — send payment prompt
            if isinstance(event, Message):
                token = make_payment_token(user_id)
                payment_url = f"{settings.billing.payment_url}?ref={token}"

                if reason == "trial_exhausted":
                    count = await get_entry_count(session, user_id)
                    text = (
                        f"Your free trial has ended ({count} notes used).\n\n"
                        f"To continue, subscribe for "
                        f"${settings.billing.monthly_price_usd:.2f}/month:\n"
                        f'<a href="{payment_url}">👉 Pay here</a>\n\n'
                        f"Your notes are saved and will be available after payment."
                    )
                else:
                    text = (
                        f"Your subscription has expired.\n\n"
                        f"Renew for ${settings.billing.monthly_price_usd:.2f}/month:\n"
                        f'<a href="{payment_url}">👉 Pay here</a>'
                    )
                await event.answer(text)
