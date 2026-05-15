from openai import AsyncOpenAI

from bot.utils.config import settings

_client = AsyncOpenAI(api_key=settings.openai_api_key)
_MODEL = "text-embedding-3-small"
_MAX_CHARS = 8000  # ~2k tokens, well within model limit


async def get_embedding(text: str) -> list[float]:
    response = await _client.embeddings.create(
        model=_MODEL,
        input=text[:_MAX_CHARS],
    )
    return response.data[0].embedding
