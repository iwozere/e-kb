import logging
import os
import tempfile

from aiogram import Bot, F, Router
from aiogram.types import Message

from bot.db.models import Entry
from bot.db.session import AsyncSessionLocal
from bot.services.embeddings import get_embedding
from bot.services.transcription import transcribe_voice
from bot.utils.config import settings
from bot.utils.rate_limit import check_voice_rate_limit

logger = logging.getLogger(__name__)
router = Router()


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

    if not check_voice_rate_limit(user_id):
        await message.answer(
            "You're sending voice notes too quickly. Limit: 20 per hour. Please wait a bit."
        )
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

    try:
        embedding = await get_embedding(transcript)
    except Exception:
        logger.exception("Embedding failed for user %s", user_id)
        embedding = None

    async with AsyncSessionLocal() as session:
        entry = Entry(
            user_id=user_id,
            text=transcript,
            source="voice",
            duration_s=voice.duration,
            embedding=embedding,
        )
        session.add(entry)
        await session.commit()

    preview = transcript[:80] + ("…" if len(transcript) > 80 else "")
    await status_msg.edit_text(f"✅ Saved: {preview}")
