"""user_preferences — per-user arbitrary key/value bag

Revision ID: 0002_user_preferences
Revises: 0001_baseline
Create Date: 2026-05-16

Adds the `user_preferences` table for storing arbitrary user-scoped
preferences (distinct from the typed system `settings` table).
"""

from __future__ import annotations

from alembic import op


revision = "0002_user_preferences"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id "
        "ON user_preferences(user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_preferences_user_id")
    op.execute("DROP TABLE IF EXISTS user_preferences")
