from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select, text

from bot.db.models import Entry, User
from bot.db.session import AsyncSessionLocal
from bot.utils.config import settings

router = Router()


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message) -> None:
    if not message.from_user or message.from_user.id not in settings.admins:
        return

    async with AsyncSessionLocal() as session:
        total_users = (
            await session.execute(select(func.count()).select_from(User))
        ).scalar() or 0

        total_entries = (
            await session.execute(select(func.count()).select_from(Entry))
        ).scalar() or 0

        # Entries by type
        type_counts = (
            await session.execute(
                select(Entry.entry_type, func.count().label("cnt"))
                .group_by(Entry.entry_type)
                .order_by(func.count().desc())
            )
        ).fetchall()

        # Entries today
        today_count = (
            await session.execute(
                text("""
                    SELECT COUNT(*) FROM entries
                    WHERE DATE(created_at AT TIME ZONE 'UTC') = CURRENT_DATE
                """)
            )
        ).scalar() or 0

        # Rough table sizes
        size_rows = (
            await session.execute(
                text("""
                    SELECT relname AS tbl,
                           pg_size_pretty(pg_total_relation_size(oid)) AS size
                    FROM pg_class
                    WHERE relname IN ('entries', 'users', 'books',
                                      'health_metrics', 'sport_logs', 'email_examples')
                    ORDER BY pg_total_relation_size(oid) DESC
                """)
            )
        ).fetchall()

    type_lines = "\n".join(f"  {r.entry_type}: {r.cnt}" for r in type_counts)
    size_lines = "\n".join(f"  {r.tbl}: {r.size}" for r in size_rows) if size_rows else "  n/a"

    await message.answer(
        "<b>📊 Admin Stats</b>\n\n"
        f"Total users:    {total_users}\n"
        f"Total entries:  {total_entries}\n"
        f"Entries today:  {today_count}\n\n"
        f"<b>By type:</b>\n{type_lines or '  none'}\n\n"
        f"<b>Table sizes:</b>\n{size_lines}"
    )
