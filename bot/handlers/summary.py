import logging
from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from bot.db.models import Entry
from bot.db.session import AsyncSessionLocal
from bot.services.llm import generate_summary

logger = logging.getLogger(__name__)
router = Router()

_LOOKBACK_DAYS = 7
_MAX_ENTRIES_FOR_SUMMARY = 100


@router.message(Command("summary"))
async def cmd_summary(message: Message) -> None:
    if not message.from_user:
        return
    since = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Entry)
            .where(Entry.user_id == message.from_user.id)
            .where(Entry.created_at >= since)
            .order_by(Entry.created_at)
            .limit(_MAX_ENTRIES_FOR_SUMMARY)
        )
        entries = result.scalars().all()

    if not entries:
        await message.answer(f"No notes from the past {_LOOKBACK_DAYS} days.")
        return

    status_msg = await message.answer(f"⏳ Generating digest from {len(entries)} notes…")

    entries_text = "\n\n".join(
        f"[{e.created_at.strftime('%Y-%m-%d %H:%M')}] {e.text}" for e in entries
    )

    try:
        digest = await generate_summary(entries_text)
    except Exception:
        logger.exception("Summary generation failed for user %s", message.from_user.id)
        await status_msg.edit_text("Failed to generate summary. Please try again later.")
        return

    await status_msg.edit_text(digest)
