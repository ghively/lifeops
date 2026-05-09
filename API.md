# API Reference

Complete REST API documentation for Knowledge OS.

---

## Quick Reference

**Base URL:** `http://localhost:8000/api/v1`  
**Authentication:** Bearer token in `Authorization` header  
**Format:** JSON request/response  
**Streaming:** Server-Sent Events (SSE) or WebSocket

---

## Authentication Endpoints

### Register User

```http
POST /auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "username": "johndoe",
  "password": "secure-password-min-8-chars",
  "display_name": "John Doe"
}
```

**Response (201):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### Login

```http
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password"
}
```

**Response (200):** Same as register

### Refresh Token

```http
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response (200):** New access token

### Get Current User

```http
GET /auth/me
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "id": "user-id",
  "email": "user@example.com",
  "username": "johndoe",
  "display_name": "John Doe",
  "created_at": "2026-04-23T10:00:00Z"
}
```

### Logout

```http
POST /auth/logout
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response (200):** `{"status": "ok"}`

### Password Reset

```http
POST /auth/password-reset
Content-Type: application/json

{
  "email": "user@example.com"
}
```

**Response (200):** Confirmation email sent (no token in response)

---

## Objects Endpoints

### List Objects

```http
GET /objects?limit=50&offset=0&type=task
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `limit` (1-1000, default: 50)
- `offset` (default: 0)
- `type` (optional: object, task, file, agent, etc)
- `sort` (optional: created, updated, title)

**Response (200):**
```json
{
  "objects": [
    {
      "id": "uuid",
      "type": "task",
      "title": "Buy groceries",
      "content": "Milk, eggs, bread",
      "properties": {
        "status": "todo",
        "priority": "high",
        "due_date": "2026-04-30"
      },
      "created_at": "2026-04-23T10:00:00Z",
      "updated_at": "2026-04-23T10:30:00Z"
    }
  ],
  "total": 150,
  "has_more": true
}
```

### Get Object

```http
GET /objects/{id}
Authorization: Bearer {access_token}
```

**Response (200):** Object details

### Create Object

```http
POST /objects
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "type": "task",
  "title": "New task",
  "content": "Description",
  "properties": {
    "status": "todo",
    "priority": "medium"
  }
}
```

**Response (201):** Created object with ID

### Update Object

```http
PUT /objects/{id}
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "title": "Updated title",
  "content": "Updated content",
  "properties": {
    "status": "in-progress"
  }
}
```

**Response (200):** Updated object

### Delete Object

```http
DELETE /objects/{id}
Authorization: Bearer {access_token}
```

**Response (204):** No content

---

## Blocks Endpoints

### Get Blocks for Object

```http
GET /blocks/object/{object_id}
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "blocks": [
    {
      "id": "block-id",
      "object_id": "object-id",
      "type": "text",
      "content": "Block content",
      "level": 0,
      "order": 0,
      "parent_id": null
    }
  ]
}
```

### Create Block

```http
POST /blocks
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "object_id": "object-id",
  "type": "text",
  "content": "New block content",
  "level": 0,
  "parent_id": null
}
```

### Update Block

```http
PUT /blocks/{block_id}
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "content": "Updated content",
  "level": 1
}
```

### Delete Block

```http
DELETE /blocks/{block_id}
Authorization: Bearer {access_token}
```

---

## Agents Endpoints

### List Agents

```http
GET /agents
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "agents": [
    {
      "id": "agent-id",
      "name": "researcher",
      "description": "Research and analysis agent",
      "status": "idle",
      "capabilities": ["search", "analyze", "summarize"],
      "current_action": null,
      "last_seen": "2026-04-23T10:00:00Z"
    }
  ]
}
```

### Get Agent Details

```http
GET /agents/{name}
Authorization: Bearer {access_token}
```

### Chat with Agent

```http
POST /agents/{name}/chat
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "content": "What's the capital of France?",
  "session_id": "session-id (optional)"
}
```

**Response:** Server-Sent Events (SSE) stream:

```
event: text_delta
data: {"type":"text_delta","delta":" The"}

event: tool_start
data: {"type":"tool_start","tool_name":"search"}

event: tool_result
data: {"type":"tool_result","result":"..."}

event: done
data: {"type":"done"}
```

### Get Chat History

```http
GET /agents/{name}/chat?session_id=...&limit=50
Authorization: Bearer {access_token}
```

---

## Agent Runtime Endpoints

### Chat with Agent Runtime

```http
POST /agent-runtime/chat
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "agent_id": "agent-id",
  "message": "Hello agent",
  "session_id": "optional",
  "shared_context": {}
}
```

### List Sessions

```http
GET /agent-runtime/sessions
Authorization: Bearer {access_token}
```

### Get Session Messages

```http
GET /agent-runtime/sessions/{session_id}/messages
Authorization: Bearer {access_token}
```

### Delete Session

```http
DELETE /agent-runtime/sessions/{session_id}
Authorization: Bearer {access_token}
```

### Get Agent Usage

```http
GET /agent-runtime/{agent_id}/usage
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "current": {
    "agent_id": "agent-id",
    "minute_requests": 5,
    "minute_limit": 10,
    "daily_tokens": 50000,
    "daily_token_limit": 100000,
    "retry_after_seconds": 0
  },
  "history": [
    {
      "date": "2026-04-23",
      "total_tokens": 25000,
      "total_requests": 100
    }
  ]
}
```

### Get Audit Log

```http
GET /agent-runtime/{agent_id}/audit
Authorization: Bearer {access_token}
```

---

## Search Endpoints

### Semantic Search

```http
GET /search?q=What+are+the+benefits+of+exercise&limit=10
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "results": [
    {
      "id": "object-id",
      "type": "object",
      "title": "Health and Fitness",
      "content": "...",
      "score": 0.95,
      "relevance": "high"
    }
  ],
  "total": 42
}
```

---

## System Endpoints

### Get Status

```http
GET /system/status
Authorization: Bearer {access_token}
```

**Response (200):**
```json
{
  "version": "v0.3.0",
  "uptime_seconds": 3600,
  "request_counts": {
    "total": 1000
  },
  "error_counts": {
    "total": 5
  },
  "active_websocket_connections": {
    "system": 5,
    "collaboration": 3,
    "total": 8
  }
}
```

### Get Logs

```http
GET /system/logs?level=info&limit=50&search=error&source=backend
Authorization: Bearer {access_token}
```

**Query Parameters:**
- `level`: all, debug, info, warn, error
- `source`: all, backend, frontend, nginx
- `search`: full-text search
- `limit`: 1-500

**Response (200):**
```json
{
  "logs": [
    {
      "timestamp": "2026-04-23T10:00:00Z",
      "level": "info",
      "source": "backend",
      "message": "User logged in",
      "logger": "app.routers.auth",
      "request_id": "req-123"
    }
  ],
  "count": 50
}
```

### Get Unified Logs

```http
GET /system/logs/unified?level=warn
Authorization: Bearer {access_token}
```

Combines backend logs + nginx access logs (4xx/5xx only).

### Ingest Frontend Logs

```http
POST /system/logs
Authorization: Bearer {access_token} (optional)
Content-Type: application/json

{
  "level": "error",
  "component": "OutlinerEditor",
  "message": "Failed to save block",
  "timestamp": "2026-04-23T10:00:00Z",
  "url": "http://localhost:5173/objects/123",
  "extra": {"blockId": "xyz"}
}
```

Or batch:
```json
{
  "batch": [
    {"level": "warn", "component": "..."},
    {"level": "error", "component": "..."}
  ]
}
```

### Smoke Test

```http
GET /system/smoke-test
Authorization: Bearer {access_token}
```

Verifies all subsystems (SQLite, Qdrant, LLM, etc).

---

## Tasks Endpoints

### List Tasks

```http
GET /tasks?status=todo&priority=high
Authorization: Bearer {access_token}
```

### Create Task

```http
POST /tasks
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "title": "Task title",
  "content": "Description",
  "priority": "high",
  "due_date": "2026-05-01",
  "assigned_to": "agent-id (optional)"
}
```

### Assign Task to Agent

```http
POST /tasks/{task_id}/assign
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "agent_id": "agent-id"
}
```

---

## Files Endpoints

### List Files

```http
GET /files
Authorization: Bearer {access_token}
```

### Get File

```http
GET /files/{file_id}
Authorization: Bearer {access_token}
```

### Reindex File

```http
POST /files/{file_id}/reindex
Authorization: Bearer {access_token}
```

### File Watcher Notification

```http
POST /files/notify
Content-Type: application/json

{
  "event": "created",
  "path": "/data/folder/file.pdf",
  "size": 1024000
}
```

---

## WebSocket Endpoints

### General WebSocket

```
ws://localhost:8000/api/v1/ws?token={access_token}
```

**Send:**
```json
{
  "type": "agent.message",
  "data": {"message": "Hello"}
}
```

**Receive:**
```json
{
  "type": "agent.message",
  "data": {"response": "Hi there"}
}
```

### System WebSocket (Logs)

```
ws://localhost:8000/api/v1/ws/system?token={access_token}
```

Receives all log entries in real-time.

---

## Error Responses

### 400 Bad Request

```json
{
  "detail": "Invalid request body",
  "status_code": 400,
  "request_id": "req-123"
}
```

### 401 Unauthorized

```json
{
  "detail": "Invalid or missing token",
  "status_code": 401,
  "request_id": "req-123"
}
```

### 429 Rate Limited

```json
{
  "detail": "Rate limit exceeded",
  "status_code": 429,
  "retry_after_seconds": 60,
  "request_id": "req-123"
}
```

### 500 Internal Error

```json
{
  "detail": "Internal server error",
  "status_code": 500,
  "request_id": "req-123"
}
```

---

## Rate Limiting

**Headers in Response:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 42
X-RateLimit-Reset: 1682000000
```

**Limits:**
- Per-agent: 100,000 tokens/day
- Per-user: 1,000 requests/day
- Per-minute: 10 requests/minute

---

## Interactive API Docs

Visit `http://localhost:8000/docs` for Swagger UI with try-it-out functionality.

Or `http://localhost:8000/redoc` for ReDoc alternative.

---

**Last Updated:** May 2026
