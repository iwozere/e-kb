from openai import AsyncOpenAI

from bot.utils.config import settings

_client = AsyncOpenAI(api_key=settings.openai_api_key)


async def transcribe_voice(file_path: str) -> str:
    with open(file_path, "rb") as f:
        response = await _client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
        )
    return response.text
