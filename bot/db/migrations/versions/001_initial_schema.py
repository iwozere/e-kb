"""Initial schema with pgvector

Revision ID: 001
Revises:
Create Date: 2026-05-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          BIGINT PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            created_at  TIMESTAMPTZ DEFAULT now(),
            is_active   BOOLEAN NOT NULL DEFAULT true
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id                  SERIAL PRIMARY KEY,
            user_id             BIGINT NOT NULL REFERENCES users(id),
            status              TEXT NOT NULL,
            stripe_customer_id  TEXT,
            stripe_sub_id       TEXT,
            valid_until         TIMESTAMPTZ,
            created_at          TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     BIGINT NOT NULL REFERENCES users(id),
            text        TEXT NOT NULL,
            source      TEXT NOT NULL,
            duration_s  INTEGER,
            embedding   vector(1536),
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute(
        "CREATE INDEX IF NOT EXISTS entries_user_created ON entries(user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS entries_embedding_hnsw "
        "ON entries USING hnsw (embedding vector_cosine_ops) "
        "WHERE embedding IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS entries")
    op.execute("DROP TABLE IF EXISTS subscriptions")
    op.execute("DROP TABLE IF EXISTS users")
