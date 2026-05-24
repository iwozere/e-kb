"""Handler for /delete <entry_id> — delete an entry with confirmation.

Shows the entry preview + an inline [🗑 Yes, delete] / [❌ Cancel] keyboard
before taking irreversible action.  Deleting an entry also removes linked
structured rows via ON DELETE CASCADE.
"""
import logging
import uuid

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.db.models import Entry
from bot.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = Router()

_TYPE_EMOJI = {"note": "📝", "book": "📚", "health": "💊", "sport": "🏃",
               "daily_summary": "📋", "weekly_summary": "📊"}


def _confirm_keyboard(entry_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🗑 Yes, delete",
                callback_data=f"confirm_delete:{entry_id}",
            ),
            InlineKeyboardButton(
                text="❌ Cancel",
                callback_data="cancel_delete",
            ),
        ]]
    )


@router.message(Command("delete"))
async def cmd_delete(message: Message) -> None:
    if not message.from_user:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Usage: /delete &lt;entry_id&gt;\n\n"
            "Find entry IDs in /search results (shown as short codes under each result)."
        )
        return

    raw_id = parts[1].strip()
    user_id = message.from_user.id

    try:
        entry_uuid = uuid.UUID(raw_id)
    except ValueError:
        await message.answer("Invalid entry ID. Copy the full UUID from /search results.")
        return

    async with AsyncSessionLocal() as session:
        entry = await session.get(Entry, entry_uuid)

        if entry is None or entry.user_id != user_id:
            await message.answer("Entry not found.")
            return

        entry_type = str(entry.entry_type)
        source = str(entry.source)
        date_str = entry.created_at.strftime("%Y-%m-%d %H:%M UTC")
        title_str = f" · {entry.title}" if entry.title else ""
        preview = str(entry.text)[:200].replace("<", "&lt;").replace(">", "&gt;")
        if len(str(entry.text)) > 200:
            preview += "…"

    emoji = "🎙" if source == "voice" else _TYPE_EMOJI.get(entry_type, "📝")

    await message.answer(
        f"{emoji} <b>{date_str}</b>{title_str} [{entry_type}]\n\n"
        f"{preview}\n\n"
        "⚠️ Delete this entry permanently?",
        reply_markup=_confirm_keyboard(str(entry_uuid)),
    )


@router.callback_query(F.data.startswith("confirm_delete:"))
async def cb_confirm_delete(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    raw_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    try:
        entry_uuid = uuid.UUID(raw_id)
    except ValueError:
        await callback.answer("Invalid entry ID.", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        entry = await session.get(Entry, entry_uuid)

        if entry is None or entry.user_id != user_id:
            await callback.answer("Entry not found.", show_alert=True)
            return

        await session.delete(entry)
        await session.commit()

    await callback.answer("🗑 Deleted.")
    if hasattr(callback.message, "edit_text"):
        await callback.message.edit_text("🗑 Entry deleted.")  # type: ignore[union-attr]


@router.callback_query(F.data == "cancel_delete")
async def cb_cancel_delete(callback: CallbackQuery) -> None:
    await callback.answer("Cancelled.")
    if callback.message and hasattr(callback.message, "edit_reply_markup"):
        await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
