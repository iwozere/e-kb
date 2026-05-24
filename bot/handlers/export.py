from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from sqlalchemy import select

from bot.db.models import Entry
from bot.db.session import AsyncSessionLocal

router = Router()

_TYPE_EMOJI = {"note": "📝", "book": "📚", "health": "💊", "sport": "🏃",
               "daily_summary": "📋", "weekly_summary": "📊"}


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    if not message.from_user:
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Entry)
            .where(Entry.user_id == message.from_user.id)
            .order_by(Entry.created_at)
        )
        entries = result.scalars().all()

    if not entries:
        await message.answer("You have no notes to export yet.")
        return

    now = datetime.now(timezone.utc)
    lines = [
        "# Knowledge Base Export\n",
        f"Exported: {now.strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"Total entries: {len(entries)}\n",
        "---\n",
    ]

    for entry in entries:
        entry_type = str(entry.entry_type)
        source = str(entry.source)
        emoji = _TYPE_EMOJI.get(entry_type, "📝")
        if source == "voice":
            emoji = "🎙"
        date = entry.created_at.strftime("%Y-%m-%d %H:%M")
        duration = f" ({entry.duration_s}s)" if entry.duration_s else ""
        title = f" — {entry.title}" if entry.title else ""
        type_label = f" [{entry_type}]"

        lines.append(f"\n## {emoji} {date}{duration}{type_label}{title}\n")
        lines.append(str(entry.text))
        lines.append("\n")

    content = "\n".join(lines).encode("utf-8")
    filename = f"kb_export_{now.strftime('%Y%m%d')}.md"

    await message.answer_document(
        BufferedInputFile(content, filename=filename),
        caption=f"📦 {len(entries)} entries exported.",
    )
