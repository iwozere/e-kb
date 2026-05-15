from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from sqlalchemy import select

from bot.db.models import Entry
from bot.db.session import AsyncSessionLocal

router = Router()


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    if not message.from_user:
        return
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Entry)
            .where(Entry.user_id == message.from_user.id)  # narrowed above
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
        f"Total notes: {len(entries)}\n",
        "---\n",
    ]
    for entry in entries:
        icon = "🎙" if entry.source == "voice" else "📝"
        date = entry.created_at.strftime("%Y-%m-%d %H:%M")
        duration = f" ({entry.duration_s}s)" if entry.duration_s else ""
        lines.append(f"\n## {icon} {date}{duration}\n")
        lines.append(entry.text)
        lines.append("\n")

    content = "\n".join(lines).encode("utf-8")
    filename = f"notes_{now.strftime('%Y%m%d')}.md"

    await message.answer_document(
        BufferedInputFile(content, filename=filename),
        caption=f"📦 {len(entries)} notes exported.",
    )
