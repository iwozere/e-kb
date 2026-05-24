"""Daily and weekly digest generation pipeline.

``generate_daily_summary`` / ``generate_weekly_summary`` are called by:
  - handlers/summary.py  (manual /day and /summary commands)
  - scheduled_*          (APScheduler automated jobs)

Both generators save the result as a new Entry in the DB, then return the text.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Entry
from bot.db.session import AsyncSessionLocal
from bot.services.embeddings import get_embedding
from bot.services.llm import complete
from bot.services.vector_store import fetch_recent_summaries, fetch_today_entries
from bot.utils.config import settings

logger = logging.getLogger(__name__)

_DAILY_PROMPT = """\
Below are {first_name}'s notes from today ({date}).

Write a structured daily summary with:
1. What happened / was done (factual)
2. Patterns or observations worth noting
3. One reflection or insight

Keep it under 200 words. Use the same language as the notes.

Notes:
{entries}\
"""

_WEEKLY_PROMPT = """\
Below are {first_name}'s daily summaries from the past week.

Write a weekly reflection covering:
1. Key themes and recurring topics
2. Progress on goals or habits
3. One insight worth carrying forward

Keep it under 300 words.

Daily summaries:
{entries}\
"""


async def generate_daily_summary(
    session: AsyncSession,
    user_id: int,
    first_name: str,
) -> str | None:
    """
    Fetch today's entries, summarise with Claude, save to DB.
    Returns the summary text or None if there are no entries today.
    """
    entries = await fetch_today_entries(session, user_id)
    if not entries:
        return None

    cap = settings.digest.max_entries_per_summary
    if len(entries) > cap:
        entries = entries[:cap]

    entries_text = "\n\n---\n\n".join(
        f"[{e.entry_type}] {e.text}" for e in entries
    )
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    summary = await complete(
        system="You are a personal assistant helping summarise daily notes.",
        user=_DAILY_PROMPT.format(
            first_name=first_name, date=today, entries=entries_text
        ),
        max_tokens=400,
    )

    embedding = await _safe_embed(summary)

    new_entry = Entry(
        user_id=user_id,
        text=summary,
        entry_type="daily_summary",
        source="system",
        title=f"Daily summary {today}",
        embedding=embedding,
    )
    session.add(new_entry)
    # Caller commits

    return summary


async def generate_weekly_summary(
    session: AsyncSession,
    user_id: int,
    first_name: str,
) -> str | None:
    """
    Summarise the last 7 daily summaries into a weekly reflection.
    Returns the summary text or None if no daily summaries exist.
    """
    summaries = await fetch_recent_summaries(session, user_id, days=7)
    if not summaries:
        return None

    entries_text = "\n\n---\n\n".join(str(e.text) for e in summaries)

    summary = await complete(
        system="You are a personal assistant helping create weekly reflections.",
        user=_WEEKLY_PROMPT.format(first_name=first_name, entries=entries_text),
        max_tokens=600,
    )

    embedding = await _safe_embed(summary)
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    new_entry = Entry(
        user_id=user_id,
        text=summary,
        entry_type="weekly_summary",
        source="system",
        title=f"Weekly summary {today}",
        embedding=embedding,
    )
    session.add(new_entry)
    # Caller commits

    return summary


# ── APScheduler job targets ───────────────────────────────────────────────────

async def scheduled_daily_digest(bot, user_id: int, first_name: str) -> None:
    """APScheduler target: run digest and push message to user."""
    try:
        async with AsyncSessionLocal() as session:
            text = await generate_daily_summary(session, user_id, first_name)
            if text:
                await session.commit()
        if text:
            await bot.send_message(
                user_id,
                f"📋 *Daily summary*\n\n{text}",
                parse_mode="Markdown",
            )
    except Exception:
        logger.exception("Scheduled daily digest failed for user %s", user_id)


async def scheduled_weekly_digest(bot, user_id: int, first_name: str) -> None:
    """APScheduler target: run weekly digest and push message to user."""
    try:
        async with AsyncSessionLocal() as session:
            text = await generate_weekly_summary(session, user_id, first_name)
            if text:
                await session.commit()
        if text:
            await bot.send_message(
                user_id,
                f"📊 *Weekly summary*\n\n{text}",
                parse_mode="Markdown",
            )
    except Exception:
        logger.exception("Scheduled weekly digest failed for user %s", user_id)


async def _safe_embed(text: str) -> list | None:
    try:
        return await get_embedding(text)
    except Exception:
        logger.warning("Could not embed summary")
        return None
