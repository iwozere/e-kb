from typing import Sequence

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Entry
from bot.services.embeddings import get_embedding


async def search_similar(
    session: AsyncSession,
    user_id: int,
    query: str,
    limit: int = 5,
) -> Sequence[Row]:
    query_embedding = await get_embedding(query)
    distance = Entry.embedding.cosine_distance(query_embedding)

    result = await session.execute(
        select(
            Entry.id,
            Entry.text,
            Entry.created_at,
            (1 - distance).label("similarity"),
        )
        .where(Entry.user_id == user_id)
        .where(Entry.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    return result.fetchall()
