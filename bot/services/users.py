"""User creation and lookup — shared between middleware and other services."""
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    """Fetch user by id, creating a new record if they don't exist yet."""
    user = await session.get(User, user_id)
    if user is None:
        user = User(id=user_id, username=username, first_name=first_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif first_name and user.first_name != first_name:
        # Keep first_name current (user may have changed their Telegram name)
        user.first_name = first_name
        await session.commit()
    return user
