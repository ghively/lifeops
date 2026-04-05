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
                content TEXT NOT NULL,
                tool_calls TEXT,
                tool_results TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (session_id) REFERENCES agent_sessions(id) ON DELETE CASCADE
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
    
    async def close(self):
        """Close database connection"""
        if self.connection:
            await self.connection.close()
            logger.info("SQLite connection closed")


# Global instance
sqlite_manager = SQLiteManager()
