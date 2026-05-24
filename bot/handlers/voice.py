import logging
import os
import tempfile

from aiogram import Bot, F, Router
from aiogram.types import Message

from bot.db.session import AsyncSessionLocal
from bot.services.entry_service import create_entry
from bot.services.transcription import transcribe_voice
from bot.utils.config import settings

logger = logging.getLogger(__name__)
router = Router()

_TYPE_EMOJI = {"note": "📝", "book": "📚", "health": "💊", "sport": "🏃"}


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot) -> None:
    if not message.from_user or not message.voice:
        return

    voice = message.voice
    user_id = message.from_user.id

    if voice.duration > settings.features.max_voice_duration_sec:
        max_min = settings.features.max_voice_duration_sec // 60
        await message.answer(f"Voice message too long. Maximum is {max_min} minutes.")
        return

    status_msg = await message.answer("🎙 Transcribing…")

    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp.close()
    try:
        await bot.download(voice, destination=tmp.name)
        transcript = await transcribe_voice(tmp.name)
    except Exception:
        logger.exception("Transcription failed for user %s", user_id)
        await status_msg.edit_text("Transcription failed. Please try again.")
        return
    finally:
        os.unlink(tmp.name)

    if not transcript.strip():
        await status_msg.edit_text("Could not transcribe the audio. Please try again.")
        return

    await status_msg.edit_text("🔖 Classifying…")

    try:
        async with AsyncSessionLocal() as session:
            entry = await create_entry(
                session,
                user_id=user_id,
                text=transcript,
                source="voice",
                duration_s=voice.duration,
            )
            await session.commit()
    except Exception:
        logger.exception("Entry save failed for user %s", user_id)
        await status_msg.edit_text("Failed to save. Please try again.")
        return

    emoji = _TYPE_EMOJI.get(str(entry.entry_type), "📝")
    await status_msg.edit_text(
        f"✅ {emoji} [{entry.entry_type}] saved: {entry.title}"
    )
