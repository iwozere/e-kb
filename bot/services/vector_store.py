"""pgvector similarity search and entry fetch helpers."""
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import Row, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Entry
from bot.services.embeddings import get_embedding


async def search_similar(
    session: AsyncSession,
    user_id: int,
    query: str,
    limit: int = 5,
    entry_type: Optional[str] = None,
) -> Sequence[Row]:
    """
    Semantic search over a user's entries.

    Optional ``entry_type`` filter (e.g. ``type:sport`` in /search).
    Returns rows with (id, text, entry_type, title, created_at, similarity).
    """
    query_embedding = await get_embedding(query)
    distance = Entry.embedding.cosine_distance(query_embedding)

    stmt = (
        select(
            Entry.id,
            Entry.text,
            Entry.entry_type,
            Entry.title,
            Entry.created_at,
            (1 - distance).label("similarity"),
        )
        .where(Entry.user_id == user_id)
        .where(Entry.embedding.is_not(None))
    )
    if entry_type:
        stmt = stmt.where(Entry.entry_type == entry_type)

    stmt = stmt.order_by(distance).limit(limit)
    result = await session.execute(stmt)
    return result.fetchall()


async def fetch_today_entries(session: AsyncSession, user_id: int) -> list[Entry]:
    """All non-summary entries created today (UTC date)."""
    from sqlalchemy import Date  # noqa: PLC0415

    result = await session.execute(
        select(Entry)
        .where(Entry.user_id == user_id)
        .where(cast(Entry.created_at, Date) == func.current_date())
        .where(Entry.entry_type.not_in(["daily_summary", "weekly_summary"]))
        .order_by(Entry.created_at)
    )
    return list(result.scalars().all())


async def fetch_recent_summaries(
    session: AsyncSession,
    user_id: int,
    days: int = 7,
) -> list[Entry]:
    """Daily summaries from the last ``days`` days, newest first."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(Entry)
        .where(Entry.user_id == user_id)
        .where(Entry.entry_type == "daily_summary")
        .where(Entry.created_at >= cutoff)
        .order_by(Entry.created_at.desc())
        .limit(days)
    )
    return list(result.scalars().all())
