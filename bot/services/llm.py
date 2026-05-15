from anthropic import AsyncAnthropic

from bot.utils.config import settings

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)
_MODEL = "claude-sonnet-4-20250514"
_MAX_SUMMARY_CHARS = 8000


async def generate_summary(entries_text: str) -> str:
    if len(entries_text) > _MAX_SUMMARY_CHARS:
        entries_text = entries_text[:_MAX_SUMMARY_CHARS] + "\n[earlier entries truncated]"

    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system="You are a personal knowledge assistant. Always respond in the same language as the notes.",
        messages=[
            {
                "role": "user",
                "content": (
                    "Below are notes taken by the user over the past week.\n\n"
                    "Produce a structured digest with:\n"
                    "1. Main themes (2-4 sentences)\n"
                    "2. Recurring patterns or observations\n"
                    "3. One actionable insight based on the notes\n\n"
                    f"Notes:\n{entries_text}\n\n"
                    "Be concise."
                ),
            }
        ],
    )
    return response.content[0].text
