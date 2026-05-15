import logging

from aiogram import F, Router
from aiogram.types import Message

from bot.db.models import Entry
from bot.db.session import AsyncSessionLocal
from bot.services.embeddings import get_embedding

logger = logging.getLogger(__name__)
router = Router()

_MIN_LENGTH = 10
_MAX_LENGTH = 4000


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message) -> None:
    if not message.from_user:
        return
    text = (message.text or "").strip()

    if len(text) < _MIN_LENGTH:
        return  # Silently ignore very short messages (reactions, "ok", etc.)

    if len(text) > _MAX_LENGTH:
        await message.answer(
            f"Note is too long ({len(text)} chars). Maximum is {_MAX_LENGTH} characters."
        )
        return

    try:
        embedding = await get_embedding(text)
    except Exception:
        logger.exception("Embedding failed for user %s", message.from_user.id)
        embedding = None

    async with AsyncSessionLocal() as session:
        entry = Entry(
            user_id=message.from_user.id,  # narrowed above
            text=text,
            source="text",
            embedding=embedding,
        )
        session.add(entry)
        await session.commit()

    preview = text[:80] + ("…" if len(text) > 80 else "")
    await message.answer(f"✅ Saved: <code>{preview}</code>")
