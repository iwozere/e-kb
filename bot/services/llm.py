from google import genai
from google.genai import types

from bot.utils.config import settings

_client = genai.Client(api_key=settings.gemini_api_key)
_MODEL = "gemini-2.5-flash"
_MAX_SUMMARY_CHARS = 8000


async def generate_summary(entries_text: str) -> str:
    if len(entries_text) > _MAX_SUMMARY_CHARS:
        entries_text = entries_text[:_MAX_SUMMARY_CHARS] + "\n[earlier entries truncated]"

    response = await _client.aio.models.generate_content(
        model=_MODEL,
        contents=(
            "Below are notes taken by the user over the past week.\n\n"
            "Produce a structured digest with:\n"
            "1. Main themes (2-4 sentences)\n"
            "2. Recurring patterns or observations\n"
            "3. One actionable insight based on the notes\n\n"
            f"Notes:\n{entries_text}\n\n"
            "Be concise. Respond in the same language as the notes."
        ),
        config=types.GenerateContentConfig(
            system_instruction="You are a personal knowledge assistant.",
            max_output_tokens=1024,
        ),
    )
    return response.text or ""
