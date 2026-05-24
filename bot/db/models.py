import uuid

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = sa.Column(sa.BigInteger, primary_key=True)  # Telegram user_id
    username = sa.Column(sa.Text, nullable=True)
    first_name = sa.Column(sa.Text, nullable=True)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), server_default=sa.func.now())
    is_active = sa.Column(sa.Boolean, server_default="true", nullable=False)

    entries = relationship("Entry", back_populates="user")
    profile = relationship("UserProfile", back_populates="user", uselist=False)


# Kept for backwards compatibility — not used in v2 (no billing)
class Subscription(Base):
    __tablename__ = "subscriptions"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"), nullable=False)
    status = sa.Column(sa.Text, nullable=False)
    stripe_customer_id = sa.Column(sa.Text, nullable=True)
    stripe_sub_id = sa.Column(sa.Text, nullable=True)
    valid_until = sa.Column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), server_default=sa.func.now())


class UserProfile(Base):
    """Writing style and identity profile for /ask and /draft context."""

    __tablename__ = "user_profiles"

    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"), primary_key=True)
    about = sa.Column(sa.Text, nullable=True)         # who you are
    style_prompt = sa.Column(sa.Text, nullable=True)  # your writing style
    updated_at = sa.Column(
        sa.TIMESTAMP(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )

    user = relationship("User", back_populates="profile")


class Entry(Base):
    __tablename__ = "entries"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"), nullable=False)
    text = sa.Column(sa.Text, nullable=False)
    entry_type = sa.Column(sa.Text, nullable=False, server_default="note")
    # 'note' | 'book' | 'health' | 'sport' | 'daily_summary' | 'weekly_summary'
    source = sa.Column(sa.Text, nullable=False, server_default="text")
    # 'text' | 'voice' | 'system'
    title = sa.Column(sa.Text, nullable=True)          # auto-generated 5-word label
    duration_s = sa.Column(sa.Integer, nullable=True)  # voice duration in seconds
    embedding = sa.Column(Vector(1536), nullable=True)
    chroma_synced = sa.Column(sa.Boolean, server_default="true")  # legacy compat field
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), server_default=sa.func.now())

    user = relationship("User", back_populates="entries")
    book = relationship("Book", back_populates="entry", uselist=False)
    health_metric = relationship("HealthMetric", back_populates="entry", uselist=False)
    sport_log = relationship("SportLog", back_populates="entry", uselist=False)


class Book(Base):
    __tablename__ = "books"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"), nullable=False)
    entry_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("entries.id", ondelete="CASCADE"),
        nullable=True,
    )
    title = sa.Column(sa.Text, nullable=False)
    author = sa.Column(sa.Text, nullable=True)
    status = sa.Column(sa.Text, server_default="reading")  # reading | finished | abandoned
    rating = sa.Column(sa.Integer, nullable=True)          # 1–10
    notes = sa.Column(sa.Text, nullable=True)
    date_finished = sa.Column(sa.Date, nullable=True)

    entry = relationship("Entry", back_populates="book")


class HealthMetric(Base):
    __tablename__ = "health_metrics"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"), nullable=False)
    entry_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("entries.id", ondelete="CASCADE"),
        nullable=True,
    )
    date = sa.Column(sa.Date, nullable=False, server_default=sa.func.current_date())
    metric_type = sa.Column(sa.Text, nullable=False)
    # weight | sleep | blood_pressure | glucose | custom
    value = sa.Column(sa.Numeric, nullable=True)
    unit = sa.Column(sa.Text, nullable=True)
    notes = sa.Column(sa.Text, nullable=True)

    entry = relationship("Entry", back_populates="health_metric")


class SportLog(Base):
    __tablename__ = "sport_logs"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"), nullable=False)
    entry_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("entries.id", ondelete="CASCADE"),
        nullable=True,
    )
    date = sa.Column(sa.Date, nullable=False, server_default=sa.func.current_date())
    activity = sa.Column(sa.Text, nullable=False)
    # run | gym | swim | bike | yoga | custom
    duration_min = sa.Column(sa.Integer, nullable=True)
    intensity = sa.Column(sa.Text, nullable=True)  # low | medium | high
    distance_km = sa.Column(sa.Numeric, nullable=True)
    notes = sa.Column(sa.Text, nullable=True)

    entry = relationship("Entry", back_populates="sport_log")


class EmailExample(Base):
    """Past email input/reply pairs used for /draft style matching."""

    __tablename__ = "email_examples"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"), nullable=False)
    incoming = sa.Column(sa.Text, nullable=False)
    outgoing = sa.Column(sa.Text, nullable=False)
    context = sa.Column(sa.Text, nullable=True)  # work | personal | formal
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), server_default=sa.func.now())
