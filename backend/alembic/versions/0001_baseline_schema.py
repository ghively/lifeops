"""baseline — captures the schema created by SQLiteManager._create_tables

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-23

This migration is the canonical starting point for Alembic-managed schema changes.

On a fresh deployment, running ``alembic upgrade head`` will create the full schema.
On an existing deployment already bootstrapped via ``SQLiteManager._create_tables``,
all statements are idempotent (``CREATE TABLE IF NOT EXISTS`` / ``CREATE INDEX IF NOT EXISTS``)
so stamping or upgrading has no destructive effect — you can run either:

    alembic stamp 0001_baseline    # mark existing DB as migrated
    alembic upgrade head           # apply (safe on existing schemas)
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


TABLES = [
    # (name, create_sql)
    (
        "settings",
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        "watched_folders",
        """
        CREATE TABLE IF NOT EXISTS watched_folders (
            id TEXT PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            recursive INTEGER DEFAULT 1,
            include_patterns TEXT DEFAULT '["*"]',
            exclude_patterns TEXT DEFAULT '[".git", "node_modules"]',
            enabled INTEGER DEFAULT 1,
            file_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        "file_sync_status",
        """
        CREATE TABLE IF NOT EXISTS file_sync_status (
            file_path TEXT PRIMARY KEY,
            checksum TEXT,
            last_modified TIMESTAMP,
            index_status TEXT DEFAULT 'pending',
            error_message TEXT,
            object_id TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        "backup_log",
        """
        CREATE TABLE IF NOT EXISTS backup_log (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            status TEXT NOT NULL,
            details TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        )
        """,
    ),
    (
        "agent_sessions",
        """
        CREATE TABLE IF NOT EXISTS agent_sessions (
            id TEXT PRIMARY KEY,
            agent_id TEXT,
            agent_name TEXT NOT NULL,
            task_id TEXT,
            status TEXT DEFAULT 'active',
            title TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            summary TEXT,
            message_count INTEGER DEFAULT 0,
            messages_count INTEGER DEFAULT 0,
            metadata TEXT
        )
        """,
    ),
    (
        "agent_messages",
        """
        CREATE TABLE IF NOT EXISTS agent_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            name TEXT,
            content TEXT NOT NULL,
            tool_calls TEXT,
            tool_results TEXT,
            tokens_in INTEGER,
            tokens_out INTEGER,
            created_at TIMESTAMP NOT NULL,
            metadata TEXT,
            FOREIGN KEY (session_id) REFERENCES agent_sessions(id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "agent_audit_log",
        """
        CREATE TABLE IF NOT EXISTS agent_audit_log (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            session_id TEXT,
            user_id TEXT,
            event_type TEXT NOT NULL,
            details_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        "agent_token_usage",
        """
        CREATE TABLE IF NOT EXISTS agent_token_usage (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            date TEXT NOT NULL,
            total_tokens INTEGER DEFAULT 0,
            total_requests INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(agent_id, user_id, date)
        )
        """,
    ),
    (
        "mcp_server_configs",
        """
        CREATE TABLE IF NOT EXISTS mcp_server_configs (
            name TEXT PRIMARY KEY,
            transport TEXT NOT NULL,
            command TEXT,
            args TEXT DEFAULT '[]',
            env TEXT DEFAULT '{}',
            url TEXT,
            headers TEXT DEFAULT '{}',
            timeout_seconds INTEGER DEFAULT 30,
            enabled INTEGER DEFAULT 1,
            auto_connect INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        "agent_scheduled_tasks",
        """
        CREATE TABLE IF NOT EXISTS agent_scheduled_tasks (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            name TEXT NOT NULL,
            cron_expression TEXT NOT NULL,
            task_type TEXT NOT NULL,
            config TEXT DEFAULT '{}',
            enabled INTEGER DEFAULT 1,
            last_run TIMESTAMP,
            next_run TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        "agent_webhooks",
        """
        CREATE TABLE IF NOT EXISTS agent_webhooks (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            name TEXT NOT NULL,
            url_path TEXT UNIQUE NOT NULL,
            secret TEXT NOT NULL,
            event_type TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        "users",
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT,
            hashed_password TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        "refresh_tokens",
        """
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "password_reset_tokens",
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """,
    ),
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key)",
    "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
    "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_sessions_agent_id ON agent_sessions(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_messages_session_id ON agent_messages(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_scheduled_tasks_agent_id ON agent_scheduled_tasks(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_webhooks_url_path ON agent_webhooks(url_path)",
]


def upgrade() -> None:
    for _, sql in TABLES:
        op.execute(sql.strip())
    for sql in INDEXES:
        op.execute(sql)


def downgrade() -> None:
    # Drop in reverse dependency order (children first).
    for name, _ in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {name}")
