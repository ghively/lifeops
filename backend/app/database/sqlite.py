"""SQLite Database Manager"""
import os
import json
import logging
from typing import Any, Iterable, Optional
import aiosqlite

from app.config import settings

logger = logging.getLogger(__name__)


class SQLiteManager:
    """Manages SQLite database connection"""
    
    def __init__(self):
        self.db_path: str = settings.database_url.replace("sqlite:///", "")
        self.connection: Optional[aiosqlite.Connection] = None
    
    async def initialize(self):
        """Initialize SQLite database"""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Open connection with proper settings
        self.connection = await aiosqlite.connect(
            self.db_path,
            check_same_thread=False  # Allow use across threads
        )
        
        # Enable foreign keys
        await self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.row_factory = aiosqlite.Row
        
        # Create tables
        await self._create_tables()
        
        logger.info(f"SQLite initialized: {self.db_path}")
    
    async def _create_tables(self):
        """Create database tables"""
        # Settings table
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Watched folders table
        await self.connection.execute("""
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
        """)

        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS file_sync_status (
                file_path TEXT PRIMARY KEY,
                checksum TEXT,
                last_modified TIMESTAMP,
                index_status TEXT DEFAULT 'pending',
                error_message TEXT,
                object_id TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS backup_log (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        await self.connection.execute("""
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
        """)

        await self.connection.execute("""
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
        """)

        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS agent_audit_log (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                session_id TEXT,
                user_id TEXT,
                event_type TEXT NOT NULL,
                details_json TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await self.connection.execute("""
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
        """)

        await self.connection.execute("""
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
        """)

        await self.connection.execute("""
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
        """)

        await self.connection.execute("""
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
        """)

        await self._ensure_columns(
            "agent_sessions",
            {
                "agent_id": "TEXT",
                "title": "TEXT",
                "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "message_count": "INTEGER DEFAULT 0",
                "metadata": "TEXT",
            },
        )

        await self._ensure_columns(
            "agent_messages",
            {
                "name": "TEXT",
                "metadata": "TEXT",
            },
        )

        await self._ensure_columns(
            "mcp_server_configs",
            {
                "headers": "TEXT DEFAULT '{}'",
                "timeout_seconds": "INTEGER DEFAULT 30",
                "enabled": "INTEGER DEFAULT 1",
                "auto_connect": "INTEGER DEFAULT 1",
                "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
                "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            },
        )

        # Users table
        await self.connection.execute("""
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
        """)

        # Refresh tokens table
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Password reset tokens table
        await self.connection.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        await self.connection.commit()

    async def _ensure_columns(self, table_name: str, columns: dict[str, str]):
        """Add missing columns for existing tables."""
        async with self.connection.execute(f"PRAGMA table_info({table_name})") as cursor:
            existing_rows = await cursor.fetchall()
        existing = {row[1] for row in existing_rows}
        for column_name, column_type in columns.items():
            if column_name in existing:
                continue
            await self.connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )
    
    async def execute(self, query: str, parameters: tuple = ()):
        """Execute a query"""
        if not self.connection:
            raise RuntimeError("Database not initialized")
        
        async with self.connection.execute(query, parameters) as cursor:
            await self.connection.commit()
            return cursor

    async def executemany(self, query: str, parameters: Iterable[tuple]):
        """Execute many rows for a query"""
        if not self.connection:
            raise RuntimeError("Database not initialized")

        await self.connection.executemany(query, parameters)
        await self.connection.commit()
    
    async def fetchone(self, query: str, parameters: tuple = ()):
        """Fetch a single row"""
        if not self.connection:
            raise RuntimeError("Database not initialized")
        
        async with self.connection.execute(query, parameters) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row is not None else None
    
    async def fetchall(self, query: str, parameters: tuple = ()):
        """Fetch all rows"""
        if not self.connection:
            raise RuntimeError("Database not initialized")
        
        async with self.connection.execute(query, parameters) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def upsert_setting(self, key: str, value: Any):
        """Store a JSON-serializable setting value."""
        await self.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, json.dumps(value)),
        )

    async def get_setting(self, key: str, default: Any = None):
        """Load a setting value."""
        row = await self.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        if not row or row.get("value") is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    async def list_mcp_server_configs(self):
        """Fetch all persisted MCP server configs."""
        rows = await self.fetchall(
            """
            SELECT name, transport, command, args, env, url, headers, timeout_seconds, enabled, auto_connect
            FROM mcp_server_configs
            ORDER BY name
            """
        )
        configs = []
        for row in rows:
            configs.append(
                {
                    "name": row["name"],
                    "transport": row["transport"],
                    "command": row.get("command"),
                    "args": json.loads(row.get("args") or "[]"),
                    "env": json.loads(row.get("env") or "{}"),
                    "url": row.get("url"),
                    "headers": json.loads(row.get("headers") or "{}"),
                    "timeout_seconds": int(row.get("timeout_seconds") or 30),
                    "enabled": bool(row.get("enabled", 1)),
                    "auto_connect": bool(row.get("auto_connect", 1)),
                }
            )
        return configs

    async def upsert_mcp_server_config(self, config: dict[str, Any]):
        """Insert or update an MCP server config."""
        await self.execute(
            """
            INSERT INTO mcp_server_configs (
                name, transport, command, args, env, url, headers, timeout_seconds, enabled, auto_connect, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                transport = excluded.transport,
                command = excluded.command,
                args = excluded.args,
                env = excluded.env,
                url = excluded.url,
                headers = excluded.headers,
                timeout_seconds = excluded.timeout_seconds,
                enabled = excluded.enabled,
                auto_connect = excluded.auto_connect,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                config["name"],
                config["transport"],
                config.get("command"),
                json.dumps(config.get("args", [])),
                json.dumps(config.get("env", {})),
                config.get("url"),
                json.dumps(config.get("headers", {})),
                int(config.get("timeout_seconds", 30)),
                1 if config.get("enabled", True) else 0,
                1 if config.get("auto_connect", True) else 0,
            ),
        )

    async def delete_mcp_server_config(self, name: str):
        """Delete an MCP server config by name."""
        await self.execute("DELETE FROM mcp_server_configs WHERE name = ?", (name,))

    async def create_agent_scheduled_task(self, payload: dict[str, Any]):
        await self.execute(
            """
            INSERT INTO agent_scheduled_tasks (
                id, agent_id, name, cron_expression, task_type, config, enabled, last_run, next_run, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """,
            (
                payload["id"],
                payload["agent_id"],
                payload["name"],
                payload["cron_expression"],
                payload["task_type"],
                json.dumps(payload.get("config", {})),
                1 if payload.get("enabled", True) else 0,
                payload.get("last_run"),
                payload.get("next_run"),
                payload.get("created_at"),
            ),
        )

    async def list_agent_scheduled_tasks(self, agent_id: Optional[str] = None):
        query = "SELECT * FROM agent_scheduled_tasks"
        parameters: tuple[Any, ...] = ()
        if agent_id:
            query += " WHERE agent_id = ?"
            parameters = (agent_id,)
        query += " ORDER BY created_at DESC, name ASC"
        rows = await self.fetchall(query, parameters)
        return [self._decode_agent_scheduled_task(row) for row in rows]

    async def get_agent_scheduled_task(self, task_id: str):
        row = await self.fetchone("SELECT * FROM agent_scheduled_tasks WHERE id = ?", (task_id,))
        return self._decode_agent_scheduled_task(row) if row else None

    async def update_agent_scheduled_task_run(self, task_id: str, *, last_run: Optional[str], next_run: Optional[str]):
        await self.execute(
            "UPDATE agent_scheduled_tasks SET last_run = ?, next_run = ? WHERE id = ?",
            (last_run, next_run, task_id),
        )

    async def delete_agent_scheduled_task(self, task_id: str):
        await self.execute("DELETE FROM agent_scheduled_tasks WHERE id = ?", (task_id,))

    async def create_agent_webhook(self, payload: dict[str, Any]):
        await self.execute(
            """
            INSERT INTO agent_webhooks (
                id, agent_id, name, url_path, secret, event_type, enabled, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """,
            (
                payload["id"],
                payload["agent_id"],
                payload["name"],
                payload["url_path"],
                payload["secret"],
                payload["event_type"],
                1 if payload.get("enabled", True) else 0,
                payload.get("created_at"),
            ),
        )

    async def list_agent_webhooks(self, agent_id: Optional[str] = None):
        query = "SELECT * FROM agent_webhooks"
        parameters: tuple[Any, ...] = ()
        if agent_id:
            query += " WHERE agent_id = ?"
            parameters = (agent_id,)
        query += " ORDER BY created_at DESC, name ASC"
        rows = await self.fetchall(query, parameters)
        return [self._decode_agent_webhook(row) for row in rows]

    async def get_agent_webhook(self, webhook_id: str):
        row = await self.fetchone("SELECT * FROM agent_webhooks WHERE id = ?", (webhook_id,))
        return self._decode_agent_webhook(row) if row else None

    async def get_agent_webhook_by_path(self, url_path: str):
        row = await self.fetchone("SELECT * FROM agent_webhooks WHERE url_path = ?", (url_path,))
        return self._decode_agent_webhook(row) if row else None

    async def delete_agent_webhook(self, webhook_id: str):
        await self.execute("DELETE FROM agent_webhooks WHERE id = ?", (webhook_id,))

    async def upsert_agent_token_usage(self, payload: dict[str, Any]):
        await self.execute(
            """
            INSERT INTO agent_token_usage (
                id, agent_id, user_id, date, total_tokens, total_requests, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            ON CONFLICT(agent_id, user_id, date) DO UPDATE SET
                total_tokens = excluded.total_tokens,
                total_requests = excluded.total_requests
            """,
            (
                payload["id"],
                payload["agent_id"],
                payload["user_id"],
                payload["date"],
                int(payload.get("total_tokens", 0)),
                int(payload.get("total_requests", 0)),
                payload.get("created_at"),
            ),
        )

    async def get_agent_token_usage(self, agent_id: str, user_id: str, date: str):
        return await self.fetchone(
            "SELECT * FROM agent_token_usage WHERE agent_id = ? AND user_id = ? AND date = ?",
            (agent_id, user_id, date),
        )

    async def list_agent_token_usage(self, agent_id: str, user_id: Optional[str] = None, limit: int = 30):
        query = "SELECT * FROM agent_token_usage WHERE agent_id = ?"
        parameters: list[Any] = [agent_id]
        if user_id:
            query += " AND user_id = ?"
            parameters.append(user_id)
        query += " ORDER BY date DESC LIMIT ?"
        parameters.append(limit)
        return await self.fetchall(query, tuple(parameters))

    async def create_agent_audit_event(self, payload: dict[str, Any]):
        await self.execute(
            """
            INSERT INTO agent_audit_log (
                id, agent_id, session_id, user_id, event_type, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """,
            (
                payload["id"],
                payload["agent_id"],
                payload.get("session_id"),
                payload.get("user_id"),
                payload["event_type"],
                json.dumps(payload.get("details", {})),
                payload.get("created_at"),
            ),
        )

    async def list_agent_audit_events(self, agent_id: str, page: int = 1, page_size: int = 50):
        offset = max(page - 1, 0) * page_size
        rows = await self.fetchall(
            """
            SELECT * FROM agent_audit_log
            WHERE agent_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (agent_id, page_size, offset),
        )
        total = await self.fetchone(
            "SELECT COUNT(*) AS count FROM agent_audit_log WHERE agent_id = ?",
            (agent_id,),
        )
        return {
            "items": [
                {
                    "id": row["id"],
                    "agent_id": row["agent_id"],
                    "session_id": row.get("session_id"),
                    "user_id": row.get("user_id"),
                    "event_type": row["event_type"],
                    "details": json.loads(row.get("details_json") or "{}"),
                    "created_at": row.get("created_at"),
                }
                for row in rows
            ],
            "total": int((total or {}).get("count") or 0),
        }

    async def purge_agent_audit_events(self, cutoff_timestamp: str):
        await self.execute(
            "DELETE FROM agent_audit_log WHERE created_at < ?",
            (cutoff_timestamp,),
        )

    def _decode_agent_scheduled_task(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "agent_id": row["agent_id"],
            "name": row["name"],
            "cron_expression": row["cron_expression"],
            "task_type": row["task_type"],
            "config": json.loads(row.get("config") or "{}"),
            "enabled": bool(row.get("enabled", 1)),
            "last_run": row.get("last_run"),
            "next_run": row.get("next_run"),
            "created_at": row.get("created_at"),
        }

    def _decode_agent_webhook(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "agent_id": row["agent_id"],
            "name": row["name"],
            "url_path": row["url_path"],
            "secret": row["secret"],
            "event_type": row["event_type"],
            "enabled": bool(row.get("enabled", 1)),
            "created_at": row.get("created_at"),
        }
    
    async def close(self):
        """Close database connection"""
        if self.connection:
            await self.connection.close()
            logger.info("SQLite connection closed")


# Global instance
sqlite_manager = SQLiteManager()
