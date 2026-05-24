"""Shared pipeline for creating, classifying, and saving entries.

Both voice.py and text_note.py call ``create_entry`` to avoid duplicating the
classify → title → embed → save flow.
"""
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Book, Entry, HealthMetric, SportLog
from bot.services.classifier import classify_entry, extract_structured, generate_title
from bot.services.embeddings import get_embedding
from bot.utils.config import settings

logger = logging.getLogger(__name__)


async def create_entry(
    session: AsyncSession,
    user_id: int,
    text: str,
    source: str,
    duration_s: int | None = None,
) -> Entry:
    """
    Full entry-creation pipeline:
      1. Truncate to config limit
      2. Classify → entry_type
      3. Generate 5-word title
      4. Embed
      5. INSERT into entries
      6. INSERT into structured sub-table (book / health_metric / sport_log)

    Returns the flushed (but not yet committed) Entry.
    Caller must ``await session.commit()`` after this.
    """
    text = text[: settings.features.max_text_length_chars]

    entry_type = await classify_entry(text)
    title = await generate_title(text)

    try:
        embedding = await get_embedding(text)
    except Exception:
        logger.warning("Embedding failed for user %s — storing without embedding", user_id)
        embedding = None

    entry = Entry(
        user_id=user_id,
        text=text,
        entry_type=entry_type,
        source=source,
        title=title,
        duration_s=duration_s,
        embedding=embedding,
    )
    session.add(entry)
    await session.flush()  # populate entry.id before structured save

    await _save_structured(session, user_id, entry.id, entry_type, text)

    return entry


async def _save_structured(
    session: AsyncSession,
    user_id: int,
    entry_id,
    entry_type: str,
    text: str,
) -> None:
    """Insert into the matching structured table. Silently skips on failure."""
    if entry_type not in {"book", "health", "sport"}:
        return

    data = await extract_structured(entry_type, text)
    if not data:
        return

    try:
        if entry_type == "book":
            session.add(
                Book(
                    user_id=user_id,
                    entry_id=entry_id,
                    title=data.get("title") or text[:50],
                    author=data.get("author"),
                    status=data.get("status") or "reading",
                    rating=data.get("rating"),
                )
            )
        elif entry_type == "health":
            session.add(
                HealthMetric(
                    user_id=user_id,
                    entry_id=entry_id,
                    date=date.today(),
                    metric_type=data.get("metric_type") or "custom",
                    value=data.get("value"),
                    unit=data.get("unit"),
                    notes=data.get("notes"),
                )
            )
        elif entry_type == "sport":
            session.add(
                SportLog(
                    user_id=user_id,
                    entry_id=entry_id,
                    date=date.today(),
                    activity=data.get("activity") or "custom",
                    duration_min=data.get("duration_min"),
                    intensity=data.get("intensity"),
                    distance_km=data.get("distance_km"),
                )
            )
    except Exception:
        logger.warning("Structured sub-record insert failed for entry %s", entry_id)
