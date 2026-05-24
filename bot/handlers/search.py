from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.session import AsyncSessionLocal
from bot.services.vector_store import search_similar

router = Router()

_TYPE_EMOJI = {"note": "📝", "book": "📚", "health": "💊", "sport": "🏃",
               "daily_summary": "📋", "weekly_summary": "📊"}

_DIVIDER = "━" * 24


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    if not message.from_user:
        return

    raw = (message.text or "").split(maxsplit=1)
    if len(raw) < 2 or not raw[1].strip():
        await message.answer(
            "Usage: /search &lt;query&gt;\n\n"
            "Optional type filter: /search energy type:sport"
        )
        return

    query_full = raw[1].strip()

    # Parse optional "type:foo" suffix
    entry_type: str | None = None
    query = query_full
    if " type:" in query_full:
        parts = query_full.rsplit(" type:", 1)
        query = parts[0].strip()
        entry_type = parts[1].strip().lower() or None

    async with AsyncSessionLocal() as session:
        results = await search_similar(
            session,
            message.from_user.id,
            query,
            limit=5,
            entry_type=entry_type,
        )

    if not results:
        await message.answer("No notes found for your query.")
        return

    safe_q = query.replace("<", "&lt;").replace(">", "&gt;")
    filter_str = f" · type:{entry_type}" if entry_type else ""
    lines = [_DIVIDER, f"🔍 <b>{safe_q}</b>{filter_str}\n"]

    for i, row in enumerate(results, 1):
        pct = int(row.similarity * 100)
        date = row.created_at.strftime("%b %d")
        emoji = _TYPE_EMOJI.get(str(row.entry_type), "📝")
        type_label = str(row.entry_type)
        preview = str(row.text)[:150].replace("<", "&lt;").replace(">", "&gt;")
        if len(str(row.text)) > 150:
            preview += "…"

        title_part = f" · {row.title}" if row.title else ""
        entry_id = str(row.id)
        lines.append(
            f"{i}. [{pct}%] {emoji} {type_label}{title_part} · {date}\n"
            f"   <code>{entry_id}</code>\n"
            f"   {preview}"
        )

    lines.append(_DIVIDER)
    await message.answer("\n\n".join(lines))
