# Database Schema Reference

Complete database schema for SQLite and Qdrant.

---

## SQLite Schema

SQLite stores relational data: users, sessions, audit logs, configuration, and scheduling.

### users table

```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,      -- bcrypt hash (cost=12)
  display_name TEXT,
  created_at TEXT NOT NULL,         -- ISO8601
  updated_at TEXT NOT NULL
);
```

**Indexes:**
```sql
CREATE UNIQUE INDEX idx_users_email ON users(email);
CREATE UNIQUE INDEX idx_users_username ON users(username);
```

### user_sessions table

```sql
CREATE TABLE user_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  refresh_token_hash TEXT UNIQUE NOT NULL,  -- HMAC-SHA256
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### agent_sessions table

```sql
CREATE TABLE agent_sessions (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  title TEXT,                       -- Auto-generated from first messages
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  message_count INTEGER DEFAULT 0,
  metadata TEXT,                    -- JSON: {title_generated: bool, ...}
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

**Indexes:**
```sql
CREATE INDEX idx_agent_sessions_agent_id ON agent_sessions(agent_id);
CREATE INDEX idx_agent_sessions_user_id ON agent_sessions(user_id);
CREATE INDEX idx_agent_sessions_created ON agent_sessions(created_at DESC);
```

### agent_messages table

```sql
CREATE TABLE agent_messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,               -- 'user', 'assistant', 'system', 'tool'
  content TEXT NOT NULL,            -- Message text
  created_at TEXT NOT NULL,
  metadata TEXT,                    -- JSON: {tokens_in, tokens_out, model, ...}
  FOREIGN KEY (session_id) REFERENCES agent_sessions(id)
);
```

**Indexes:**
```sql
CREATE INDEX idx_agent_messages_session ON agent_messages(session_id);
CREATE INDEX idx_agent_messages_created ON agent_messages(created_at DESC);
```

### agent_audit table

```sql
CREATE TABLE agent_audit (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  session_id TEXT,
  user_id TEXT,
  event_type TEXT NOT NULL,         -- 'tool_call', 'approval', 'error', 'spawn', ...
  details TEXT NOT NULL,            -- JSON: {tool_name, arguments, result, ...}
  created_at TEXT NOT NULL,         -- ISO8601
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

**Indexes:**
```sql
CREATE INDEX idx_audit_agent_id ON agent_audit(agent_id);
CREATE INDEX idx_audit_event_type ON agent_audit(event_type);
CREATE INDEX idx_audit_created ON agent_audit(created_at DESC);
```

**Retention:** Data automatically deleted after 90 days.

### scheduled_tasks table

```sql
CREATE TABLE scheduled_tasks (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  name TEXT NOT NULL,
  cron_expression TEXT NOT NULL,    -- e.g., "0 9 * * MON"
  task_type TEXT NOT NULL,          -- 'periodic_research', 'memory_curation', ...
  config TEXT NOT NULL,             -- JSON: {param1: value1, ...}
  enabled BOOLEAN DEFAULT true,
  last_run TEXT,                    -- ISO8601
  next_run TEXT,                    -- ISO8601
  created_at TEXT NOT NULL
);
```

**Indexes:**
```sql
CREATE INDEX idx_scheduled_agent ON scheduled_tasks(agent_id);
CREATE INDEX idx_scheduled_enabled ON scheduled_tasks(enabled);
```

### webhooks table

```sql
CREATE TABLE webhooks (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  name TEXT NOT NULL,
  url_path TEXT UNIQUE NOT NULL,    -- /webhooks/incoming/{id}
  secret TEXT NOT NULL,             -- HMAC secret
  event_type TEXT NOT NULL,         -- Event trigger
  enabled BOOLEAN DEFAULT true,
  created_at TEXT NOT NULL
);
```

**Indexes:**
```sql
CREATE UNIQUE INDEX idx_webhook_path ON webhooks(url_path);
CREATE INDEX idx_webhook_agent ON webhooks(agent_id);
```

### watched_folders table

```sql
CREATE TABLE watched_folders (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  path TEXT NOT NULL,
  recursive BOOLEAN DEFAULT true,
  patterns TEXT,                    -- JSON: {include: [...], exclude: [...]}
  created_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## Qdrant Vector Collections

All collections use **384-dimensional vectors** from `sentence-transformers/all-MiniLM-L6-v2`.

### objects collection

Stores main content objects (notes, tasks, files, etc).

```json
{
  "name": "objects",
  "vectors": {
    "size": 384,
    "distance": "Cosine"
  },
  "payload_schema": {
    "id": {
      "type": "keyword"
    },
    "type": {
      "type": "keyword"
    },
    "title": {
      "type": "text"
    },
    "created_at": {
      "type": "datetime"
    }
  }
}
```

**Point Structure:**
```json
{
  "id": "uuid",
  "vector": [384-dimensional array],
  "payload": {
    "id": "uuid",
    "type": "object",
    "title": "My Note",
    "content": "Full text content",
    "icon": "📝",
    "layout": "default",
    "properties": {
      "status": "active",
      "tags": ["important", "work"],
      "due_date": "2026-05-01"
    },
    "created_at": "2026-04-23T10:00:00Z",
    "updated_at": "2026-04-23T10:30:00Z"
  }
}
```

### blocks collection

Text blocks with hierarchy information.

```json
{
  "id": "block-id",
  "vector": [384-dim],
  "payload": {
    "id": "block-id",
    "object_id": "parent-object-id",
    "type": "text",
    "content": "Block text content",
    "level": 0,
    "order": 0,
    "parent_id": null,
    "references": ["ref-id-1", "ref-id-2"],
    "created_at": "2026-04-23T10:00:00Z"
  }
}
```

### files collection

Indexed file content with metadata.

```json
{
  "id": "file-id",
  "vector": [384-dim],
  "payload": {
    "id": "file-id",
    "path": "/data/folder/document.pdf",
    "filename": "document.pdf",
    "size": 1024000,
    "format": "pdf",
    "content": "Extracted text from file",
    "pages": 10,
    "created_at": "2026-04-23T10:00:00Z",
    "indexed_at": "2026-04-23T10:05:00Z"
  }
}
```

**Supported Formats:**
- PDF (PyMuPDF)
- Word (python-docx)
- Markdown
- Code (Python, JavaScript, Java, etc)
- Text

### code collection

Code snippets with semantic information.

```json
{
  "id": "code-id",
  "vector": [384-dim],
  "payload": {
    "id": "code-id",
    "language": "python",
    "content": "def hello(): print('world')",
    "functions": ["hello"],
    "classes": [],
    "imports": [],
    "description": "Simple hello function",
    "file": "/path/to/file.py",
    "line_start": 1,
    "line_end": 2
  }
}
```

### images collection

Image embeddings using CLIP.

```json
{
  "id": "image-id",
  "vector": [384-dim from CLIP],
  "payload": {
    "id": "image-id",
    "path": "/data/folder/image.jpg",
    "filename": "image.jpg",
    "size": 512000,
    "width": 1920,
    "height": 1080,
    "description": "Alt text or generated description",
    "created_at": "2026-04-23T10:00:00Z"
  }
}
```

### chat_logs collection

Conversation history for context retrieval.

```json
{
  "id": "log-id",
  "vector": [384-dim],
  "payload": {
    "id": "log-id",
    "session_id": "session-id",
    "agent_id": "agent-id",
    "role": "user",
    "content": "User message",
    "timestamp": "2026-04-23T10:00:00Z"
  }
}
```

### memories collection

Agent daily memory logs for semantic retrieval.

```json
{
  "id": "memory-id",
  "vector": [384-dim],
  "payload": {
    "id": "memory-id",
    "agent_id": "agent-id",
    "date": "2026-04-23",
    "content": "Summary of events that happened",
    "events": ["event1", "event2"],
    "created_at": "2026-04-23T23:59:00Z"
  }
}
```

### relations collection

Relationship metadata.

```json
{
  "id": "relation-id",
  "vector": [384-dim],
  "payload": {
    "id": "relation-id",
    "source_id": "object-id",
    "target_id": "object-id",
    "type": "links_to",
    "context": "Optional explanation",
    "created_at": "2026-04-23T10:00:00Z"
  }
}
```

**Relation Types:**
- `links_to` — Wiki-style link
- `relates_to` — General relationship
- `references` — Block references
- `parent_of` — Object hierarchy
- `mentions` — Tags/mentions
- `depends_on` — Task dependency
- `assigned_to` — Task assignment

---

## Database Operations

### Create Tables (Migration)

```python
# Uses Alembic for schema versioning
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

### Backup

**SQLite:**
```bash
# Binary copy
cp knowledge_os.db knowledge_os.db.backup

# SQL dump
sqlite3 knowledge_os.db .dump > backup.sql
```

**Qdrant:**
```bash
# Snapshot
curl -X POST http://localhost:6333/snapshots

# Or via Python
client.create_snapshot("snapshot-name")
```

### Query Examples

**Get user sessions:**
```python
from app.database.sqlite import sqlite_manager

sessions = sqlite_manager.execute("""
  SELECT * FROM agent_sessions 
  WHERE user_id = ? 
  ORDER BY created_at DESC
""", (user_id,)).fetchall()
```

**Search objects:**
```python
from app.database.qdrant_client import qdrant_manager

client = qdrant_manager.get_client()
results = client.search(
  collection_name="objects",
  query_vector=query_embedding,
  limit=10,
  score_threshold=0.7
)
```

**Get agent audit log:**
```python
audit = sqlite_manager.execute("""
  SELECT * FROM agent_audit 
  WHERE agent_id = ? AND created_at > ?
  ORDER BY created_at DESC
""", (agent_id, 90_days_ago)).fetchall()
```

---

## Performance Tips

### Indexing
- Always index foreign keys
- Index frequently queried columns
- Use UNIQUE for uniqueness constraints

### Qdrant
- Batch point insertions (100+ points at once)
- Use appropriate distance metric (Cosine for embeddings)
- Archive old memories regularly

### SQLite
- Use PRAGMA journal_mode=WAL for concurrency
- Increase timeout for busy database
- Regular VACUUM to defragment

---

## Data Retention

**Automatic Cleanup:**
- Audit logs: 90 days (configurable)
- User sessions: On logout
- Temporary files: 7 days
- Memory logs: Configurable (default: 30 days)

**Manual Cleanup:**
```sql
-- Delete old audit records
DELETE FROM agent_audit 
WHERE created_at < datetime('now', '-90 days');

-- Delete old messages
DELETE FROM agent_messages 
WHERE created_at < datetime('now', '-1 year');

-- Optimize database
VACUUM;
```

---

## Alembic Migrations

New migrations for schema changes:

```bash
# Create migration
alembic revision --autogenerate -m "Add new table"

# View migration
cat alembic/versions/0002_add_new_table.py

# Apply upgrade
alembic upgrade head

# Downgrade
alembic downgrade -1
```

Migration example:
```python
def upgrade():
    op.create_table(
        'new_table',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('new_table')
```

---

**For schema details and examples, see code:**
- SQLite: `backend/app/database/sqlite.py`
- Qdrant: `backend/app/database/qdrant_client.py`
- Alembic: `backend/alembic/versions/`
