"""Handler for /draft — generate an email reply in the user's style.

After generating a draft, two inline buttons appear:
  [✅ Save as Example]  — stores input/output pair in email_examples for future style matching
  [🔄 Regenerate]       — calls the style engine again for a different take

Pending drafts are stored in memory keyed by a short random ID.
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

from bot.db.models import EmailExample
from bot.db.session import AsyncSessionLocal
from bot.services.style_engine import draft_reply
from bot.utils.config import settings

logger = logging.getLogger(__name__)
router = Router()

# callback_id → (incoming_text, draft_text)
_pending: dict[str, tuple[str, str]] = {}


def _keyboard(callback_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="✅ Save as Example",
                callback_data=f"save_example:{callback_id}",
            ),
            InlineKeyboardButton(
                text="🔄 Regenerate",
                callback_data=f"regen_draft:{callback_id}",
            ),
        ]]
    )


@router.message(Command("draft"))
async def cmd_draft(message: Message) -> None:
    if not message.from_user:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Paste the incoming email text after /draft:\n\n"
            "/draft Hi, I wanted to follow up on our conversation…"
        )
        return

    incoming = parts[1].strip()[: settings.features.max_text_length_chars]
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "User"

    thinking = await message.answer("✍️ Drafting reply…")

    try:
        async with AsyncSessionLocal() as session:
            draft = await draft_reply(session, user_id, first_name, incoming)

        cid = str(uuid.uuid4())[:8]
        _pending[cid] = (incoming, draft)

        await thinking.edit_text(
            f"📧 <b>Draft reply:</b>\n\n{draft}",
            reply_markup=_keyboard(cid),
        )
    except Exception:
        logger.exception("Draft failed for user %s", user_id)
        await thinking.edit_text("Draft generation failed. Please try again.")


@router.callback_query(F.data.startswith("save_example:"))
async def cb_save_example(callback: CallbackQuery) -> None:
    if not callback.from_user:
        await callback.answer()
        return

    cid = callback.data.split(":", 1)[1]
    pending = _pending.pop(cid, None)

    if pending is None:
        await callback.answer("This draft has expired. Use /draft again.", show_alert=True)
        return

    incoming, draft = pending
    user_id = callback.from_user.id

    async with AsyncSessionLocal() as session:
        session.add(EmailExample(user_id=user_id, incoming=incoming, outgoing=draft))
        await session.commit()

    await callback.answer("✅ Saved as style example!")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("regen_draft:"))
async def cb_regen_draft(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return

    cid = callback.data.split(":", 1)[1]
    pending = _pending.get(cid)

    if pending is None:
        await callback.answer("This draft has expired. Use /draft again.", show_alert=True)
        return

    incoming, _ = pending
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name or "User"

    await callback.answer("Regenerating…")

    try:
        async with AsyncSessionLocal() as session:
            new_draft = await draft_reply(session, user_id, first_name, incoming)

        new_cid = str(uuid.uuid4())[:8]
        _pending[new_cid] = (incoming, new_draft)
        _pending.pop(cid, None)

        await callback.message.edit_text(
            f"📧 <b>Draft reply (regenerated):</b>\n\n{new_draft}",
            reply_markup=_keyboard(new_cid),
        )
    except Exception:
        logger.exception("Regenerate draft failed for user %s", user_id)
        await callback.message.answer("Regeneration failed. Please try again.")
