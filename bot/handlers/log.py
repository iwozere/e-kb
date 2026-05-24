"""Handler for /log — structured data entry for books, health metrics, and sport.

Syntax:
  /log book "Antifragile" Nassim Taleb — finished — 9/10
  /log health weight 78 kg
  /log health sleep 7.5h
  /log sport run 45min 6km high

Claude parses the log line and populates both entries and the matching
structured table (books / health_metrics / sport_logs).
"""
import json
import logging
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.models import Book, Entry, HealthMetric, SportLog
from bot.db.session import AsyncSessionLocal
from bot.services.classifier import generate_title
from bot.services.embeddings import get_embedding
from bot.services.llm import complete

logger = logging.getLogger(__name__)
router = Router()

_PARSE_PROMPTS = {
    "book": (
        'Parse this book log entry and return ONLY valid JSON:\n'
        '"{text}"\n\n'
        'JSON: {{"title": "...", "author": "...", '
        '"status": "reading|finished|abandoned", "rating": null_or_1_to_10}}'
    ),
    "health": (
        'Parse this health log entry and return ONLY valid JSON:\n'
        '"{text}"\n\n'
        'JSON: {{"metric_type": "weight|sleep|blood_pressure|glucose|custom", '
        '"value": number_or_null, "unit": "...", "notes": "..."}}'
    ),
    "sport": (
        'Parse this sport log entry and return ONLY valid JSON:\n'
        '"{text}"\n\n'
        'JSON: {{"activity": "run|gym|swim|bike|yoga|custom", '
        '"duration_min": number_or_null, "intensity": "low|medium|high|null", '
        '"distance_km": number_or_null, "notes": "..."}}'
    ),
}


@router.message(Command("log"))
async def cmd_log(message: Message) -> None:
    if not message.from_user:
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "<b>Usage:</b>\n"
            '/log book "Antifragile" Nassim Taleb — finished — 9/10\n'
            "/log health weight 78 kg\n"
            "/log health sleep 7.5h\n"
            "/log sport run 45min 6km high"
        )
        return

    log_type = parts[1].strip().lower()
    log_text = parts[2].strip()

    if log_type not in _PARSE_PROMPTS:
        await message.answer("Type must be one of: <code>book</code>, <code>health</code>, <code>sport</code>")
        return

    user_id = message.from_user.id
    thinking = await message.answer(f"📥 Parsing {log_type} entry…")

    # Parse structured data
    try:
        raw = await complete(
            system="You are a structured data parser. Return ONLY valid JSON, no prose.",
            user=_PARSE_PROMPTS[log_type].format(text=log_text),
            max_tokens=200,
        )
        data = json.loads(raw.strip())
    except Exception:
        logger.exception("Log parse failed for user %s", user_id)
        await thinking.edit_text("Failed to parse log entry. Please try again.")
        return

    full_text = f"{log_type}: {log_text}"
    title = await generate_title(full_text)

    try:
        embedding = await get_embedding(full_text)
    except Exception:
        embedding = None

    try:
        async with AsyncSessionLocal() as session:
            entry = Entry(
                user_id=user_id,
                text=full_text,
                entry_type=log_type,
                source="text",
                title=title,
                embedding=embedding,
            )
            session.add(entry)
            await session.flush()

            if log_type == "book":
                session.add(Book(
                    user_id=user_id,
                    entry_id=entry.id,
                    title=data.get("title") or log_text[:50],
                    author=data.get("author"),
                    status=data.get("status") or "reading",
                    rating=data.get("rating"),
                ))
            elif log_type == "health":
                session.add(HealthMetric(
                    user_id=user_id,
                    entry_id=entry.id,
                    date=date.today(),
                    metric_type=data.get("metric_type") or "custom",
                    value=data.get("value"),
                    unit=data.get("unit"),
                    notes=data.get("notes"),
                ))
            elif log_type == "sport":
                session.add(SportLog(
                    user_id=user_id,
                    entry_id=entry.id,
                    date=date.today(),
                    activity=data.get("activity") or "custom",
                    duration_min=data.get("duration_min"),
                    intensity=data.get("intensity"),
                    distance_km=data.get("distance_km"),
                    notes=data.get("notes"),
                ))

            await session.commit()
    except Exception:
        logger.exception("Log save failed for user %s", user_id)
        await thinking.edit_text("Failed to save. Please try again.")
        return

    emoji = {"book": "📚", "health": "💊", "sport": "🏃"}[log_type]
    await thinking.edit_text(f"✅ {emoji} {log_type.capitalize()} logged: {title}")
