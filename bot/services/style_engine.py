"""Email drafting engine: RAG + style prompt → reply in the user's voice.

Called by handlers/draft.py.  The system prompt (identity + style) is marked
for prompt caching because it is stable across /draft calls for a given user.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import EmailExample, UserProfile
from bot.services.llm import complete
from bot.services.vector_store import search_similar

logger = logging.getLogger(__name__)

_DRAFT_SYSTEM = """\
You are drafting an email reply on behalf of {first_name}.

THEIR WRITING STYLE:
{style_prompt}\
"""

_DRAFT_USER = """\
RELEVANT KNOWLEDGE FROM THEIR KNOWLEDGE BASE (use if applicable):
{search_results}

EXAMPLES OF THEIR PAST REPLIES:
{examples}

Now draft a reply to this incoming email:
{incoming}

Write only the reply body. Match their style exactly.\
"""


async def draft_reply(
    session: AsyncSession,
    user_id: int,
    first_name: str,
    incoming: str,
) -> str:
    """
    Generate a draft email reply in the user's style.

    Pipeline:
      1. Fetch style_prompt from user_profiles
      2. Semantic search for relevant KB entries
      3. Fetch up to 3 most recent email examples
      4. Call Claude (system prompt cached)
    """
    profile = await session.get(UserProfile, user_id)
    style_prompt = (
        profile.style_prompt
        if profile is not None and profile.style_prompt is not None
        else "Professional and concise."
    )

    # Relevant knowledge
    rows = await search_similar(session, user_id, incoming, limit=5)
    if rows:
        search_results = "\n\n".join(
            f"[{r.entry_type}] {r.text[:300]}" for r in rows
        )
    else:
        search_results = "No relevant entries found."

    # Email style examples
    result = await session.execute(
        select(EmailExample)
        .where(EmailExample.user_id == user_id)
        .order_by(EmailExample.created_at.desc())
        .limit(3)
    )
    examples = result.scalars().all()

    if examples:
        examples_text = "\n".join(
            f"---\nIncoming: {ex.incoming}\nTheir reply: {ex.outgoing}"
            for ex in examples
        )
    else:
        examples_text = "No examples yet — draft based on style only."

    system = _DRAFT_SYSTEM.format(first_name=first_name, style_prompt=style_prompt)
    user_msg = _DRAFT_USER.format(
        search_results=search_results,
        examples=examples_text,
        incoming=incoming,
    )

    return await complete(
        system=system,
        user=user_msg,
        max_tokens=800,
        cache_system=True,
        effort="medium",
    )
