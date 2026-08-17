"""Voice transcription: local faster-whisper (primary) or OpenAI Whisper API (fallback).

Config:
  whisper.use_local: true   → faster-whisper on-device (RPi 5, ~15-20 s for 1 min audio)
  whisper.use_local: false  → OpenAI Whisper API ($0.006/min), good for dev

Telegram sends voice messages as OGG Opus.  Both backends accept OGG directly —
ffmpeg and pydub are NOT required.

The local model is loaded once at first use and kept in memory.
"""
import asyncio
import logging

from bot.utils.config import settings

logger = logging.getLogger(__name__)

_local_model = None  # loaded lazily


def _get_local_model():
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel  # noqa: PLC0415

        logger.info(
            "Loading faster-whisper model '%s' (first use — may take a moment)…",
            settings.whisper.local_model,
        )
        _local_model = WhisperModel(
            settings.whisper.local_model,
            device="cpu",
            compute_type="int8",
        )
        logger.info("faster-whisper model loaded.")
    return _local_model


def _local_model_available() -> bool:
    try:
        import faster_whisper  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


def _transcribe_local_sync(file_path: str) -> str:
    model = _get_local_model()
    segments, _ = model.transcribe(file_path, beam_size=5)
    return " ".join(s.text for s in segments).strip()


async def _transcribe_local(file_path: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _transcribe_local_sync, file_path)


async def _transcribe_api(file_path: str) -> str:
    from openai import AsyncOpenAI  # noqa: PLC0415

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    with open(file_path, "rb") as f:
        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
        )
    return response.text


async def transcribe_voice(file_path: str) -> str:
    """Transcribe an OGG audio file. Uses local model or API per config."""
    if settings.whisper.use_local:
        if _local_model_available():
            return await _transcribe_local(file_path)
        logger.warning(
            "whisper.use_local is true but faster-whisper is not installed "
            "(see requirements-local-whisper.txt) — falling back to the OpenAI API.",
        )
    return await _transcribe_api(file_path)
