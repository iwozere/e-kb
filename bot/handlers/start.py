import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Entry
from bot.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = Router()

_HELP = """\
👋 Hello, <b>{name}</b>!

I'm your personal knowledge base and AI clone.

<b>Capture</b>
• Send <b>voice messages</b> — transcribed &amp; saved automatically
• Send <b>text messages</b> — saved as notes
• /log book|health|sport — structured entries

<b>Query</b>
• /ask &lt;question&gt; — ask your clone anything
• /search &lt;query&gt; — semantic search
• /day — today's digest
• /summary — weekly digest

<b>Email drafting</b>
• /draft &lt;incoming email&gt; — reply in your style
• /profile — view/set writing style &amp; about

<b>Other</b>
• /status — note count &amp; streak
• /export — download all notes as Markdown
• /delete &lt;id&gt; — delete an entry
• /help — this message\
"""


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return
    name = message.from_user.first_name or "there"
    await message.answer(_HELP.format(name=name))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not message.from_user:
        return
    user_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        total = (
            await session.execute(
                select(func.count())
                .select_from(Entry)
                .where(Entry.user_id == user_id)
            )
        ).scalar() or 0

        last_ts = (
            await session.execute(
                select(Entry.created_at)
                .where(Entry.user_id == user_id)
                .order_by(Entry.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        streak = await _compute_streak(session, user_id)

    last_str = last_ts.strftime("%b %d, %H:%M UTC") if last_ts else "never"

    if streak > 1:
        streak_str = f"🔥 {streak}-day streak"
    elif streak == 1:
        streak_str = "🔥 active today"
    else:
        streak_str = "no streak yet"

    await message.answer(
        f"<b>📋 Your stats</b>\n\n"
        f"Total notes: <b>{total}</b>\n"
        f"Last entry:  {last_str}\n"
        f"Streak:      {streak_str}"
    )


async def _compute_streak(session: AsyncSession, user_id: int) -> int:
    """
    Count consecutive calendar days (UTC) ending today or yesterday that have
    at least one non-summary entry.  Uses the islands-and-gaps technique.
    """
    row = (
        await session.execute(
            text("""
                WITH days AS (
                    SELECT DISTINCT DATE(created_at AT TIME ZONE 'UTC') AS day
                    FROM entries
                    WHERE user_id = :uid
                      AND entry_type NOT IN ('daily_summary', 'weekly_summary')
                ),
                grps AS (
                    SELECT day,
                           day - CAST(ROW_NUMBER() OVER (ORDER BY day) AS INT) AS grp
                    FROM days
                ),
                streaks AS (
                    SELECT MAX(day) AS last_day, COUNT(*) AS len
                    FROM grps
                    GROUP BY grp
                )
                SELECT len
                FROM streaks
                WHERE last_day >= CURRENT_DATE - INTERVAL '1 day'
                ORDER BY last_day DESC
                LIMIT 1
            """),
            {"uid": user_id},
        )
    ).fetchone()

    return int(row[0]) if row else 0
