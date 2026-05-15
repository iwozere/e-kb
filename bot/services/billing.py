import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Entry, Subscription, User
from bot.utils.config import settings


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        user = User(id=user_id, username=username, first_name=first_name)
        session.add(user)
        sub = Subscription(user_id=user_id, status="trial")
        session.add(sub)
        await session.commit()
        await session.refresh(user)
    return user


async def get_subscription(session: AsyncSession, user_id: int) -> Subscription | None:
    result = await session.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_entry_count(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(Entry).where(Entry.user_id == user_id)
    )
    return result.scalar() or 0


async def can_access(session: AsyncSession, user_id: int) -> tuple[bool, str]:
    """Returns (allowed, reason). Admins must be checked by caller before this."""
    sub = await get_subscription(session, user_id)

    if sub is None:
        return False, "no_subscription"

    if sub.status == "active":
        if sub.valid_until and sub.valid_until > datetime.now(timezone.utc):
            return True, "active"
        sub.status = "expired"
        await session.commit()
        return False, "expired"

    if sub.status == "trial":
        count = await get_entry_count(session, user_id)
        if count < settings.billing.trial_notes:
            return True, f"trial:{count}"
        return False, "trial_exhausted"

    return False, "expired"


async def activate_subscription(
    session: AsyncSession,
    user_id: int,
    stripe_sub_id: str,
    stripe_customer_id: str = "",
) -> None:
    sub = await get_subscription(session, user_id)
    if sub is None:
        sub = Subscription(user_id=user_id)
        session.add(sub)

    sub.status = "active"
    sub.stripe_sub_id = stripe_sub_id
    if stripe_customer_id:
        sub.stripe_customer_id = stripe_customer_id
    sub.valid_until = datetime.now(timezone.utc) + timedelta(days=30)
    await session.commit()


def make_payment_token(user_id: int) -> str:
    payload = json.dumps({"uid": user_id, "exp": int(time.time()) + 86400})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.digest(
        settings.payment_hmac_secret.encode(),
        payload_b64.encode(),
        hashlib.sha256,
    ).hex()
    return f"{payload_b64}.{sig}"


def verify_payment_token(token: str) -> int | None:
    try:
        payload_b64, sig = token.rsplit(".", 1)
        expected = hmac.digest(
            settings.payment_hmac_secret.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).hex()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode())
        if payload["exp"] < int(time.time()):
            return None
        return int(payload["uid"])
    except Exception:
        return None
