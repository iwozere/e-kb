"""v2 schema: entry_type/title/chroma_synced on entries, new structured tables

Revision ID: 002
Revises: 001
Create Date: 2026-05-24
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Extend entries table ──────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE entries ADD COLUMN IF NOT EXISTS entry_type TEXT NOT NULL DEFAULT 'note'"
    )
    op.execute("ALTER TABLE entries ADD COLUMN IF NOT EXISTS title TEXT")
    op.execute(
        "ALTER TABLE entries ADD COLUMN IF NOT EXISTS chroma_synced BOOLEAN DEFAULT true"
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS entries_user_type ON entries(user_id, entry_type)"
    )

    # ── User profiles ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id      BIGINT PRIMARY KEY REFERENCES users(id),
            about        TEXT,
            style_prompt TEXT,
            updated_at   TIMESTAMPTZ DEFAULT now()
        )
    """)

    # ── Books ─────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       BIGINT REFERENCES users(id),
            entry_id      UUID REFERENCES entries(id) ON DELETE CASCADE,
            title         TEXT NOT NULL,
            author        TEXT,
            status        TEXT DEFAULT 'reading',
            rating        INTEGER CHECK (rating BETWEEN 1 AND 10),
            notes         TEXT,
            date_finished DATE
        )
    """)

    # ── Health metrics ────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS health_metrics (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     BIGINT REFERENCES users(id),
            entry_id    UUID REFERENCES entries(id) ON DELETE CASCADE,
            date        DATE NOT NULL DEFAULT CURRENT_DATE,
            metric_type TEXT NOT NULL,
            value       NUMERIC,
            unit        TEXT,
            notes       TEXT
        )
    """)

    # ── Sport logs ────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS sport_logs (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      BIGINT REFERENCES users(id),
            entry_id     UUID REFERENCES entries(id) ON DELETE CASCADE,
            date         DATE NOT NULL DEFAULT CURRENT_DATE,
            activity     TEXT NOT NULL,
            duration_min INTEGER,
            intensity    TEXT,
            distance_km  NUMERIC,
            notes        TEXT
        )
    """)

    # ── Email examples ────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_examples (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    BIGINT REFERENCES users(id),
            incoming   TEXT NOT NULL,
            outgoing   TEXT NOT NULL,
            context    TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_examples")
    op.execute("DROP TABLE IF EXISTS sport_logs")
    op.execute("DROP TABLE IF EXISTS health_metrics")
    op.execute("DROP TABLE IF EXISTS books")
    op.execute("DROP TABLE IF EXISTS user_profiles")
    op.execute("DROP INDEX IF EXISTS entries_user_type")
    op.execute("ALTER TABLE entries DROP COLUMN IF EXISTS chroma_synced")
    op.execute("ALTER TABLE entries DROP COLUMN IF EXISTS title")
    op.execute("ALTER TABLE entries DROP COLUMN IF EXISTS entry_type")
