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

    subscriptions = relationship("Subscription", back_populates="user")
    entries = relationship("Entry", back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"), nullable=False)
    status = sa.Column(sa.Text, nullable=False)  # 'trial' | 'active' | 'expired'
    stripe_customer_id = sa.Column(sa.Text, nullable=True)
    stripe_sub_id = sa.Column(sa.Text, nullable=True)
    valid_until = sa.Column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), server_default=sa.func.now())

    user = relationship("User", back_populates="subscriptions")


class Entry(Base):
    __tablename__ = "entries"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"), nullable=False)
    text = sa.Column(sa.Text, nullable=False)
    source = sa.Column(sa.Text, nullable=False)  # 'voice' | 'text'
    duration_s = sa.Column(sa.Integer, nullable=True)
    embedding = sa.Column(Vector(1536), nullable=True)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), server_default=sa.func.now())

    user = relationship("User", back_populates="entries")
