"""Handler for /profile — view and update user style + about fields."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.db.models import UserProfile
from bot.db.session import AsyncSessionLocal

router = Router()


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    parts = (message.text or "").split(maxsplit=2)

    # ── Show current profile ──────────────────────────────────────────────────
    if len(parts) == 1:
        async with AsyncSessionLocal() as session:
            profile = await session.get(UserProfile, user_id)

        if profile is None or (not profile.about and not profile.style_prompt):
            await message.answer(
                "No profile set yet.\n\n"
                "Set it with:\n"
                "/profile about I'm a product designer based in Zurich…\n"
                "/profile style I write short, direct emails. No filler phrases…\n\n"
                "Both fields are used by /ask and /draft to personalise responses."
            )
            return

        about = str(profile.about) if profile.about else "<i>Not set.</i>"
        style = str(profile.style_prompt) if profile.style_prompt else "<i>Not set.</i>"
        await message.answer(
            f"<b>About you:</b>\n{about}\n\n"
            f"<b>Writing style:</b>\n{style}\n\n"
            "Update with /profile about &lt;text&gt; or /profile style &lt;text&gt;"
        )
        return

    # ── Update a field ────────────────────────────────────────────────────────
    if len(parts) < 3:
        await message.answer(
            "Usage:\n"
            "/profile about &lt;text&gt;\n"
            "/profile style &lt;text&gt;"
        )
        return

    field = parts[1].strip().lower()
    value = parts[2].strip()

    if field not in {"about", "style"}:
        await message.answer("Field must be <code>about</code> or <code>style</code>.")
        return

    async with AsyncSessionLocal() as session:
        profile = await session.get(UserProfile, user_id)
        if profile is None:
            profile = UserProfile(user_id=user_id)
            session.add(profile)

        if field == "about":
            profile.about = value
        else:
            profile.style_prompt = value

        await session.commit()

    label = "About" if field == "about" else "Writing style"
    await message.answer(f"✅ <b>{label}</b> updated.")
