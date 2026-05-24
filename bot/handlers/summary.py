"""Handlers for /day (manual daily digest) and /summary (weekly digest)."""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.session import AsyncSessionLocal
from bot.services.daily_digest import generate_daily_summary, generate_weekly_summary

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("day"))
async def cmd_day(message: Message) -> None:
    """Manually trigger a daily digest for today's entries."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"
    thinking = await message.answer("📋 Generating daily summary…")

    try:
        async with AsyncSessionLocal() as session:
            summary = await generate_daily_summary(session, user_id, first_name)
            if summary:
                await session.commit()

        if summary is None:
            await thinking.edit_text(
                "Nothing logged today. Send a voice message or type a note first."
            )
            return

        await thinking.edit_text(f"📋 <b>Daily summary</b>\n\n{summary}")
    except Exception:
        logger.exception("Daily digest failed for user %s", user_id)
        await thinking.edit_text("Failed to generate summary. Please try again.")


@router.message(Command("summary"))
async def cmd_summary(message: Message) -> None:
    """Generate a weekly digest from the last 7 daily summaries."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"
    thinking = await message.answer("📊 Generating weekly summary…")

    try:
        async with AsyncSessionLocal() as session:
            summary = await generate_weekly_summary(session, user_id, first_name)
            if summary:
                await session.commit()

        if summary is None:
            await thinking.edit_text(
                "No daily summaries found for the past week.\n"
                "Use /day to generate today's digest — come back after a few days."
            )
            return

        await thinking.edit_text(f"📊 <b>Weekly summary</b>\n\n{summary}")
    except Exception:
        logger.exception("Weekly summary failed for user %s", user_id)
        await thinking.edit_text("Failed to generate summary. Please try again.")
