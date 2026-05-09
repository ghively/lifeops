# Architecture Guide

Complete technical overview of Knowledge OS system design, components, and data flow.

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Component Architecture](#component-architecture)
3. [Data Flow](#data-flow)
4. [Database Design](#database-design)
5. [API Design](#api-design)
6. [Agent Runtime](#agent-runtime)
7. [Real-Time Systems](#real-time-systems)
8. [Security Architecture](#security-architecture)

---

## System Overview

Knowledge OS is a **three-tier distributed system**:

```
┌─────────────────────────────────────────┐
│         Frontend Tier                    │
│  (React 18 + TypeScript + WebSocket)   │
└─────────────────────────────────────────┘
              ⬆️⬇️ HTTPS
┌─────────────────────────────────────────┐
│       Application Tier (FastAPI)         │
│  (Routers, Services, Business Logic)    │
└─────────────────────────────────────────┘
              ⬆️⬇️ Async I/O
┌─────────────────────────────────────────┐
│           Data Tier                      │
│  (SQLite, Qdrant, File System)         │
└─────────────────────────────────────────┘
```

---

## Component Architecture

### Frontend Layer

**Technology Stack:**
- React 18 for UI components and state management
- TypeScript for type safety
- Vite for fast development and builds
- Tailwind CSS + shadcn/ui for styling
- TanStack Query (React Query) for server state
- Zustand for client state (auth, theme, WebSocket)
- WebSocket for real-time updates

**Key Components:**
```
App
├─ Pages/
│  ├─ LoginPage          - Authentication
│  ├─ OutlinerPage       - Block editor
│  ├─ TasksPage          - Task management
│  ├─ FilesPage          - File browser
│  ├─ AgentsPage         - Agent management
│  ├─ AgentChatPage      - Chat interface
│  ├─ SettingsPage       - Configuration
│  ├─ SearchPage         - Semantic search
│  └─ LogsPage           - Log viewer
├─ Components/
│  ├─ Sidebar            - Navigation
│  ├─ MainLayout         - App shell
│  ├─ AgentChatPanel     - Chat UI
│  ├─ OutlinerEditor     - Block editor
│  └─ ... (24+ components)
├─ Hooks/
│  ├─ useAgentChat       - Chat logic
│  ├─ useWebSocket       - Connection
│  ├─ useMediaQuery      - Responsive
│  └─ ... (6+ hooks)
└─ Stores/
   ├─ auth               - Auth state
   ├─ websocket          - WS state
   ├─ theme              - Theme state
   └─ collaboration      - Presence state
```

**Data Flow:**
1. User interaction → React state update
2. State change → API call via `services/api.ts`
3. API response → Zustand store + React Query cache
4. Cache update → Component re-render
5. WebSocket message → Direct state update (for real-time)

### Backend Layer

**Technology Stack:**
- FastAPI for async web framework
- Pydantic for data validation
- asyncio for concurrency
- structlog for structured logging
- SQLAlchemy for ORM (SQLite)
- qdrant-client for vector DB

**Router Structure:**
```
app.main:FastAPI
├─ /auth              - Authentication endpoints
├─ /agents            - Agent management
├─ /agent-runtime     - Agent execution
├─ /agent-webhooks    - Webhook receivers
├─ /objects           - Object CRUD
├─ /blocks            - Block CRUD
├─ /tasks             - Task management
├─ /files             - File indexing
├─ /relations         - Relationship management
├─ /collaboration     - Real-time features
├─ /search            - Semantic search
├─ /settings          - User settings
├─ /system            - Status and logs
└─ /ws                - WebSocket connections
```

**Service Architecture:**
```
Services/
├─ Authentication
│  ├─ auth.py        - User auth, tokens, password reset
│  └─ middleware/auth.py - JWT validation
├─ Agent Runtime
│  ├─ runtime.py     - Central orchestrator
│  ├─ agent_loop.py  - ReAct execution
│  ├─ session.py     - Session persistence
│  ├─ memory.py      - Memory retrieval
│  ├─ tool_registry.py - Tool management
│  ├─ llm_router.py  - LLM provider routing
│  ├─ mcp_client.py  - MCP server integration
│  ├─ rate_limiter.py - Token budgeting
│  ├─ scheduler.py   - Cron task execution
│  ├─ webhooks.py    - Event triggering
│  ├─ audit.py       - Decision logging
│  └─ security.py    - Security checks
├─ Data & Search
│  ├─ embedding.py   - Text/image embeddings
│  ├─ context_builder.py - Context gathering
│  └─ search.py      - Semantic search
├─ File Management
│  ├─ file_watcher.py - Real-time watching
│  └─ files.py       - File CRUD
├─ Collaboration
│  ├─ websocket_manager.py - Event broadcasting
│  ├─ collaboration.py - Presence tracking
│  └─ relations.py   - Graph relationships
└─ Infrastructure
   ├─ backup.py      - Snapshots & exports
   └─ logging_config.py - Structured logging
```

**Middleware Stack:**
1. CORS - Cross-origin requests
2. Request Logging - structlog with request_id
3. Authentication - JWT validation
4. Rate Limiting - slowapi with custom limits
5. Error Handling - Global exception handling

### Data Layer

**SQLite (Relational Data)**
```
Tables:
├─ users              - User accounts and profiles
├─ user_sessions      - Refresh token storage
├─ agent_sessions     - Chat session persistence
├─ agent_messages     - Chat message history
├─ agent_audit        - Decision and action logs
├─ scheduled_tasks    - Cron task definitions
├─ webhooks           - Webhook definitions
└─ watched_folders    - Folder configuration
```

**Qdrant (Vector Data)**
```
Collections:
├─ objects (384-dim)   - Main content storage
├─ blocks (384-dim)    - Text blocks with hierarchy
├─ files (384-dim)     - Indexed file content
├─ code (384-dim)      - Code snippets + AST
├─ images (384-dim)    - Image content + CLIP vectors
├─ chat_logs (384-dim) - Conversation history
├─ memories (384-dim)  - Agent memory logs
└─ relations (384-dim) - Relationship metadata
```

**File System**
```
/agents/
├─ {agent_name}/
│  ├─ AGENT.md        - Identity definition
│  ├─ SOUL.md         - Personality & values
│  ├─ MEMORY.md       - Curated memories
│  └─ TOOLS.md        - Available tools
└─ ...

/data/
├─ knowledge_os.db    - SQLite database
└─ logs/
   └─ app.log         - Rotating JSON logs
```

---

## Data Flow

### Request Lifecycle

```
1. Client Request
   ├─ Frontend sends HTTP/WebSocket request
   └─ Includes JWT token in Authorization header

2. Middleware Pipeline
   ├─ CORS validation
   ├─ Request ID generation
   ├─ JWT token validation
   ├─ User extraction from token
   └─ Rate limit check

3. Router Handling
   ├─ Path routing to correct endpoint
   └─ Parameter parsing and validation

4. Service Processing
   ├─ Business logic execution
   ├─ Database queries
   ├─ Vector searches
   ├─ External API calls
   └─ Event publishing

5. Response
   ├─ Serialize response data
   ├─ Add logging context
   └─ Return HTTP response

6. Log Broadcasting
   ├─ Logs emitted during processing
   ├─ LogBroadcastHandler captures
   ├─ JSON formatted
   └─ Broadcast to WebSocket clients
```

### Agent Execution Flow

```
1. User sends message
   └─ POST /api/v1/agents/{name}/chat

2. Session Management
   ├─ Create new or retrieve existing session
   ├─ Load previous messages (for context)
   └─ Save message to history

3. Context Building
   ├─ Gather parent objects
   ├─ Search related objects
   ├─ Find relevant files
   ├─ Retrieve agent memories
   └─ Combine with user message

4. Agent Loop (max 10 iterations)
   ├─ 1. THINK
   │  └─ LLM generates response/tool_calls
   │
   ├─ 2. CHOOSE TOOLS
   │  ├─ Parse tool_calls from LLM
   │  ├─ Check rate limits
   │  └─ Request approval if needed
   │
   ├─ 3. EXECUTE TOOLS
   │  ├─ Get tool from registry
   │  ├─ Run in sandbox with restrictions
   │  ├─ Capture output
   │  └─ Handle errors gracefully
   │
   └─ 4. OBSERVE & LOOP
      ├─ Add tool results to message history
      ├─ Check stopping conditions
      └─ Decide to continue or stop

5. Response Streaming
   ├─ Stream events to client via SSE
   ├─ User sees real-time responses
   └─ Tool calls shown as they happen

6. Post-Processing
   ├─ Save final response
   ├─ Update session title (if new)
   ├─ Log audit events
   ├─ Update memory curation
   └─ Broadcast WebSocket event
```

### Search Flow

```
1. User enters search query
   └─ POST /api/v1/search?q=...&type=...

2. Query Preprocessing
   ├─ Clean and normalize text
   ├─ Apply stemming (optional)
   └─ Generate query embedding

3. Dual Search
   ├─ Semantic Search
   │  ├─ Generate 384-dim vector
   │  ├─ Query Qdrant with vector
   │  ├─ Get top-k results (default k=10)
   │  └─ Score by similarity
   │
   └─ Full-Text Search (if enabled)
      ├─ Search across JSON fields
      ├─ Match field weights
      └─ Combine scores

4. Result Ranking
   ├─ Combine semantic + text scores
   ├─ Apply filters if specified
   ├─ Sort by final score
   └─ Return top 50

5. Response to Client
   ├─ Format results with context
   ├─ Include object type and title
   ├─ Add relevance score
   └─ Return to frontend
```

---

## Database Design

### SQLite Schema

**users table**
```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

**agent_sessions table**
```sql
CREATE TABLE agent_sessions (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  title TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  message_count INTEGER DEFAULT 0,
  metadata TEXT,  -- JSON
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

**agent_messages table**
```sql
CREATE TABLE agent_messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,  -- 'user', 'assistant', 'system', 'tool'
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  metadata TEXT,  -- JSON (tokens, model, etc)
  FOREIGN KEY (session_id) REFERENCES agent_sessions(id)
);
```

**See DATABASE.md for complete schema**

### Qdrant Collections

All collections use **384-dimensional vectors** from `sentence-transformers/all-MiniLM-L6-v2`.

**objects collection**
```json
{
  "id": "uuid",
  "vector": [384-dim array],
  "payload": {
    "id": "uuid",
    "type": "object",  // object, task, file, agent, etc
    "title": "string",
    "content": "string",
    "properties": {
      "status": "todo|in-progress|done",
      "priority": "low|medium|high|urgent",
      // ... custom properties
    },
    "created_at": "ISO8601",
    "updated_at": "ISO8601"
  }
}
```

**See DATABASE.md for all collections**

---

## API Design

### RESTful Conventions

All APIs follow RESTful conventions:
- `GET /api/v1/resource` - List resources
- `GET /api/v1/resource/{id}` - Get single resource
- `POST /api/v1/resource` - Create resource
- `PUT /api/v1/resource/{id}` - Update resource
- `DELETE /api/v1/resource/{id}` - Delete resource

### Versioning

All APIs are versioned under `/api/v1/`:
```
/api/v1/auth/login
/api/v1/agents
/api/v1/agent-runtime/chat
/api/v1/objects
/api/v1/blocks
/api/v1/search
```

### Request/Response Format

**Request:**
```http
POST /api/v1/agents/researcher/chat
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "message": "What is the capital of France?",
  "session_id": "optional-session-id",
  "shared_context": {}
}
```

**Response:**
```http
200 OK
Content-Type: text/event-stream

event: text_delta
data: {"type":"text_delta","delta":" The"}

event: text_delta
data: {"type":"text_delta","delta":" capital"}

event: done
data: {"type":"done"}
```

### Error Responses

```json
{
  "detail": "Error message",
  "status_code": 400,
  "request_id": "req-12345"
}
```

**HTTP Status Codes:**
- 200 - OK
- 201 - Created
- 400 - Bad Request (validation error)
- 401 - Unauthorized (auth failed)
- 403 - Forbidden (permission denied)
- 404 - Not Found
- 429 - Too Many Requests (rate limit)
- 500 - Internal Server Error

### Rate Limiting Headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 42
X-RateLimit-Reset: 1682000000
```

For 429 responses:
```json
{
  "detail": "Rate limit exceeded",
  "retry_after_seconds": 60
}
```

---

## Agent Runtime

### Initialization Sequence

```
AgentRuntime.__init__()
├─ IdentityLoader          # Load agent definitions
├─ LLMRouter               # Initialize LLM routing
├─ MemoryManager           # Load Qdrant memory
├─ SessionManager          # Initialize SQLite sessions
├─ AuditLogger             # Setup logging
├─ SecurityManager         # Initialize security
├─ ToolRegistry            # Load tools and MCP
├─ CollaborationService    # Setup collaboration
├─ MemoryCurationService   # Setup memory curation
├─ AgentLoop               # Wire up execution
├─ Scheduler               # Initialize cron
└─ WebhookService          # Setup webhooks

async start()
├─ await tool_registry.mcp_manager.initialize()
└─ await scheduler.start()
```

### Tool Execution Sandbox

```
Tool Request
├─ Check approval required (rate limit, tool type)
│  └─ If yes: Send to user for approval
│
├─ Get tool from registry
├─ Prepare tool input (validate, sanitize)
├─ Execute in sandbox
│  ├─ Filesystem: Restricted to /tmp, /data
│  ├─ Network: Allowed (with timeout)
│  ├─ Timeout: 30 seconds max
│  ├─ Memory: Limited (process isolation)
│  └─ Capture: stdout, stderr, return value
│
└─ Process result
   ├─ Truncate if > 4KB
   ├─ Format for LLM
   └─ Add to message history
```

### LLM Router

```
Routes to:
├─ Ollama (local, default)
│  └─ http://localhost:11434
│
├─ OpenAI (API key required)
│  ├─ gpt-4-turbo
│  └─ gpt-4o
│
├─ Anthropic (API key required)
│  └─ Claude models
│
└─ Google (API key required)
   └─ Gemini models

Provider Selection:
1. Check LLM_PROVIDER env var
2. Try detected providers (in order: Ollama, OpenAI, Anthropic, Google)
3. Fallback to Ollama
```

---

## Real-Time Systems

### WebSocket Architecture

**Connection:**
```
Frontend              Backend
   |                    |
   |---- ws://... ------|
   |                    |
   |<--- { type, data }--
   |                    |
   |-- { type, data } --|
   |                    |
```

**Event Types:**
```
Frontend → Backend:
├─ agent.message          - Send message to agent
├─ collaboration.cursor   - Update cursor position
└─ approval.respond       - Respond to approval prompt

Backend → Frontend:
├─ agent.message          - New agent response
├─ agent.status_changed   - Agent status update
├─ object.updated         - Object changed
├─ block.updated          - Block changed
├─ presence.update        - User presence
├─ collaboration.cursor   - Cursor moved
├─ log.entry              - Structured log
└─ approval.required      - Tool needs approval
```

**WebSocket Paths:**
- `/api/v1/ws` - General events
- `/api/v1/ws/system` - System logs
- `/api/v1/ws/agents/{agent_id}` - Agent-specific events

### Logging Broadcast System

```
Logger.info()
    ↓
logging.Handler.emit()
    ↓
LogBroadcastHandler
    ├─ Format as JSON
    ├─ Parse to dict
    ├─ Create WebSocketEvent
    └─ websocket_manager.broadcast()
        ├─ Iterate all connections
        └─ Send to each client (async)

Client receives:
event: log.entry
data: {"level":"info","message":"...","timestamp":"..."}
```

---

## Security Architecture

### Authentication Flow

```
1. Register/Login
   ├─ POST /api/v1/auth/register or /api/v1/auth/login
   ├─ Validate credentials
   └─ Return { access_token, refresh_token }

2. Token Storage (Client)
   ├─ access_token → localStorage (short-lived, ~15min)
   └─ refresh_token → localStorage (long-lived, ~7 days)

3. API Requests
   ├─ Authorization: Bearer {access_token}
   ├─ Middleware validates via HMAC-SHA-256
   ├─ Extract user_id, email, scopes
   └─ Attach to request context

4. Token Refresh
   ├─ If access_token expired
   ├─ POST /api/v1/auth/refresh with refresh_token
   ├─ Get new access_token
   ├─ Update localStorage
   └─ Retry original request

5. Logout
   ├─ POST /api/v1/auth/logout
   ├─ Invalidate refresh_token in DB
   ├─ Delete tokens from localStorage
   └─ Redirect to login
```

### Token Structure

**Access Token (JWT):**
```
Header: { alg: "HS256", typ: "JWT" }
Payload: {
  sub: "user-id",
  email: "user@example.com",
  jti: "unique-token-id",  // Prevents collisions
  iat: 1682000000,
  exp: 1682003600
}
Signature: HMAC-SHA256(header.payload, JWT_SECRET_KEY)
```

**Token Hashing (in DB):**
- Access tokens: Hashed with HMAC-SHA-256 (no truncation)
- Refresh tokens: Hashed with HMAC-SHA-256
- Passwords: Hashed with bcrypt (cost=12)

### Authorization & Rate Limiting

**Per-Agent Limits:**
- 100,000 tokens/day
- 1,000 requests/day
- 10 requests/minute

**Enforced via:**
```
middleware/rate_limit.py
├─ Query current usage from SQLite
├─ Compare to limits
├─ If exceeded: 429 response
└─ If approaching: Warn client
```

### Audit Logging

**Logged:**
```
Agent decisions:
├─ Tool calls and results
├─ Sub-agent spawns
├─ Memory retrievals
├─ Approvals granted/denied
└─ Errors and timeouts

User actions:
├─ Object CRUD
├─ Collaboration events
├─ File operations
└─ Settings changes

All logged to:
├─ SQLite (queryable)
├─ JSON log file (rotating)
└─ WebSocket (real-time)
```

---

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| API Call | < 200ms | Most operations |
| Semantic Search | < 500ms | 10k objects |
| Object Create | < 100ms | With embedding |
| Session Create | < 50ms | SQLite write |
| Qdrant Query | < 100ms | 384-dim vectors |
| JSON Log Write | < 10ms | Async handler |
| WebSocket Broadcast | < 50ms | All active connections |

---

## Scalability Considerations

**Current Design:**
- Single-instance backend (can add load balancer)
- SQLite (suitable for < 1M users)
- In-memory WebSocket (add Redis for multiple instances)
- File-based logging (rotate and archive)

**Scaling Path:**
1. Load balancer (nginx)
2. PostgreSQL (instead of SQLite)
3. Redis for caching and pub/sub
4. Separate agent executor service
5. Distributed job queue (Celery)

---

**For more details, see:**
- [DATABASE.md](DATABASE.md) - Schema details
- [API.md](API.md) - Endpoint reference
- [AGENT_SYSTEM.md](AGENT_SYSTEM.md) - Agent guide
