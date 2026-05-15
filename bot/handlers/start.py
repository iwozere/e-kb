from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.session import AsyncSessionLocal
from bot.services.billing import get_entry_count, get_subscription
from bot.utils.config import settings

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return
    await message.answer(
        f"👋 Hello, <b>{message.from_user.first_name}</b>!\n\n"
        "I'm your personal knowledge base. Send me:\n"
        "• <b>Voice messages</b> — I'll transcribe and save them\n"
        "• <b>Text messages</b> — I'll save them as notes\n\n"
        "<b>Commands</b>\n"
        "/search &lt;query&gt; — semantic search\n"
        "/summary — weekly AI digest\n"
        "/export — download all notes as Markdown\n"
        "/status — subscription status\n"
        "/help — this message"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not message.from_user:
        return
    user_id = message.from_user.id

    if user_id in settings.admins:
        await message.answer("✅ You have admin access (unlimited).")
        return

    async with AsyncSessionLocal() as session:
        sub = await get_subscription(session, user_id)
        count = await get_entry_count(session, user_id)

    if sub is None:
        await message.answer("No subscription found. Use /start to register.")
        return

    if sub.status == "trial":
        remaining = max(0, settings.billing.trial_notes - count)
        await message.answer(
            f"📋 <b>Trial</b>\n"
            f"Notes saved: {count}\n"
            f"Free notes remaining: {remaining} / {settings.billing.trial_notes}"
        )
    elif sub.status == "active" and sub.valid_until:
        expires = sub.valid_until.strftime("%Y-%m-%d")
        await message.answer(
            f"✅ <b>Active subscription</b>\n"
            f"Notes saved: {count}\n"
            f"Renews: {expires}"
        )
    else:
        await message.answer(
            f"❌ <b>Subscription expired</b>\n"
            f"Notes saved: {count}\n"
            f"Use /start to see payment options."
        )
