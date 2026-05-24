import logging

from aiogram import F, Router
from aiogram.types import Message

from bot.db.session import AsyncSessionLocal
from bot.services.entry_service import create_entry
from bot.utils.config import settings

logger = logging.getLogger(__name__)
router = Router()

_MIN_LENGTH = 10
_TYPE_EMOJI = {"note": "📝", "book": "📚", "health": "💊", "sport": "🏃"}


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message) -> None:
    if not message.from_user:
        return

    text = (message.text or "").strip()

    if len(text) < _MIN_LENGTH:
        return  # Silently ignore very short messages

    max_len = settings.features.max_text_length_chars
    if len(text) > max_len:
        await message.answer(
            f"Note is too long ({len(text)} chars). Maximum is {max_len} characters."
        )
        return

    try:
        async with AsyncSessionLocal() as session:
            entry = await create_entry(
                session,
                user_id=message.from_user.id,
                text=text,
                source="text",
            )
            await session.commit()
    except Exception:
        logger.exception("Entry save failed for user %s", message.from_user.id)
        await message.answer("Failed to save note. Please try again.")
        return

    emoji = _TYPE_EMOJI.get(str(entry.entry_type), "📝")
    await message.answer(
        f"✅ {emoji} [{entry.entry_type}] saved: {entry.title}"
    )
