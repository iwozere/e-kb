from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.session import AsyncSessionLocal
from bot.services.vector_store import search_similar

router = Router()


@router.message(Command("search"))
async def cmd_search(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Usage: /search &lt;query&gt;")
        return

    if not message.from_user:
        return
    query = parts[1].strip()

    async with AsyncSessionLocal() as session:
        results = await search_similar(session, message.from_user.id, query)

    if not results:
        await message.answer("No notes found for your query.")
        return

    safe_query = query.replace("<", "&lt;").replace(">", "&gt;")
    lines = [f'🔍 Search: "<b>{safe_query}</b>"\n']
    for i, row in enumerate(results, 1):
        pct = int(row.similarity * 100)
        date = row.created_at.strftime("%Y-%m-%d")
        preview = row.text[:150].replace("<", "&lt;").replace(">", "&gt;")
        if len(row.text) > 150:
            preview += "…"
        lines.append(f"{i}. [{pct}%] {date}\n   {preview}")

    await message.answer("\n\n".join(lines))
