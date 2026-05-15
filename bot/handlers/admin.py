from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select

from bot.db.models import Entry, Subscription, User
from bot.db.session import AsyncSessionLocal
from bot.utils.config import settings

router = Router()


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message) -> None:
    if not message.from_user or message.from_user.id not in settings.admins:
        return

    async with AsyncSessionLocal() as session:
        total_users = (
            await session.execute(select(func.count()).select_from(User))
        ).scalar() or 0

        active_subs = (
            await session.execute(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.status == "active")
                .where(Subscription.valid_until > datetime.now(timezone.utc))
            )
        ).scalar() or 0

        trial_users = (
            await session.execute(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.status == "trial")
            )
        ).scalar() or 0

        total_notes = (
            await session.execute(select(func.count()).select_from(Entry))
        ).scalar() or 0

    await message.answer(
        "<b>📊 Bot Stats</b>\n\n"
        f"Total users:          {total_users}\n"
        f"Active subscriptions: {active_subs}\n"
        f"Trial users:          {trial_users}\n"
        f"Total notes:          {total_notes}"
    )
