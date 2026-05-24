"""Handler for /ask — conversational query against the personal knowledge base.

Features:
  • Multi-turn conversation: last 5 exchanges remembered for 15 minutes.
    Follow-up questions like "tell me more" work naturally.
  • Prompt caching: the static system prompt (user identity + about) is marked
    cacheable, cutting token costs ~60-70 % on warm hits.
  • Dynamic context (search results) goes in the user message, not the system
    prompt, so caching stays effective despite per-query variation.
"""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.session import AsyncSessionLocal
from bot.db.models import UserProfile
from bot.services.conversation import add_turn, clear_history, get_history
from bot.services.llm import complete_with_history
from bot.services.vector_store import search_similar

logger = logging.getLogger(__name__)
router = Router()

_ASK_SYSTEM = """\
You are an AI assistant with access to {first_name}'s personal knowledge base.
Answer questions about their life, interests, and thinking based solely on the
provided context. Be specific — reference actual entries by date and type when
possible. If the context doesn't contain enough information, say so directly.

{about}\
"""


@router.message(Command("ask"))
async def cmd_ask(message: Message) -> None:
    if not message.from_user:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Usage: /ask &lt;question&gt;\n\n"
            "Example: /ask what books shaped my thinking on decision-making?\n\n"
            "Follow-up questions work too — I remember the last 5 exchanges."
        )
        return

    question = parts[1].strip()
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"

    thinking = await message.answer("🤔 Thinking…")

    try:
        async with AsyncSessionLocal() as session:
            profile = await session.get(UserProfile, user_id)
            about = str(profile.about) if profile and profile.about else ""

            results = await search_similar(session, user_id, question, limit=10)

        system = _ASK_SYSTEM.format(first_name=first_name, about=about)

        if results:
            context_text = "\n\n".join(
                f"[{row.entry_type} · {row.created_at.strftime('%b %d')}] {row.text[:400]}"
                for row in results
            )
        else:
            context_text = "No relevant entries found."

        # Dynamic context goes in the user message (not system) to keep caching effective
        user_msg = (
            f"Context (most relevant entries):\n{context_text}\n\n"
            f"Question: {question}"
        )

        history = get_history(user_id)
        answer = await complete_with_history(
            system=system,
            history=history,
            user=user_msg,
            max_tokens=1500,
            cache_system=True,
        )

        # Store only the plain question/answer pair, not the context injection
        add_turn(user_id, question, answer)
        await thinking.edit_text(answer)

    except Exception:
        logger.exception("Ask failed for user %s", user_id)
        clear_history(user_id)
        await thinking.edit_text("Something went wrong. Please try again.")
