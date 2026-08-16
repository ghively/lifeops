# Knowledge OS - Full Specification

## Table of Contents
1. [Overview](#overview)
2. [Requirements Traceability](#requirements-traceability)
3. [Chat Transcript Summary](#chat-transcript-summary)
4. [Architecture](#architecture)
5. [Data Model](#data-model)
6. [API Specification](#api-specification)
7. [WebSocket Events](#websocket-events)
8. [OpenClaw Integration](#openclaw-integration)
9. [File Indexing](#file-indexing)
10. [Backup System](#backup-system)
11. [Frontend Components](#frontend-components)
12. [Configuration](#configuration)

---

## Overview

**Knowledge OS** is a Capacities-inspired knowledge management system with OpenClaw agent integration. It combines object-based note-taking, task management, file indexing, and AI agent collaboration in a unified platform.

### Key Features

| Feature | Description |
|---------|-------------|
| **Object-Based Notes** | Everything is an object with type, properties, and relationships |
| **Outliner Editor** | Block-based editing with unlimited nesting |
| **Agent Task Assignment** | Assign tasks to OpenClaw agents with full context |
| **Semantic Search** | Find content by meaning, not just keywords |
| **File Indexing** | Watch folders and index content automatically |
| **Real-Time Updates** | WebSocket for live collaboration |
| **Three Backup Strategies** | Snapshots, Markdown export, Git sync |

### Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, Python 3.11+ |
| Vector DB | Qdrant |
| Relational DB | SQLite |
| Embeddings | sentence-transformers, CLIP |
| Agents | OpenClaw Gateway |

---

## Requirements Traceability

This section maps every requirement from our conversation to the specification.

### Core Requirements

| Requirement | Source | Implementation | Status |
|-------------|--------|----------------|--------|
| **Object-based notes** (Capacities/Anytype style) | User request | `objects` collection with types, properties, layouts | ✅ |
| **Outliner editor** (Logseq/Roam style) | User request | `blocks` collection, unlimited nesting via `parent_id` | ✅ |
| **Block references** `((block-id))` | User request | `references` and `referenced_by` arrays in blocks | ✅ |
| **Backlinks** | User request | `relations` collection with `links_to` type | ✅ |
| **Wiki-links** `[[Note Title]]` | User request | Parsed from content, stored in relations | ✅ |
| **Tagging** `#tag` | User request | `properties.tags` array on objects | ✅ |
| **Agent tagging** `@agent-name` | User request | `assigned_to` property, agent mentions | ✅ |

### Task Management Requirements

| Requirement | Source | Implementation | Status |
|-------------|--------|----------------|--------|
| **Task assignment to agents** | User request | `POST /api/v1/tasks/{id}/assign` endpoint | ✅ |
| **Priority levels** (low, medium, high, urgent) | User request | `Priority` enum in models | ✅ |
| **Status values** (todo, in-progress, blocked, review, done) | User request | `TaskStatus` enum, can go backwards | ✅ |
| **Direct assignment** (medium/high/urgent) | User request | OpenClaw Gateway API call | ✅ |
| **HEARTBEAT assignment** (low priority) | User request | `write_to_heartbeat()` method | ✅ |
| **Status can go backwards** | User request | No restrictions on status transitions | ✅ |
| **Process in priority order** | User request | Tasks sorted by priority in list | ✅ |
| **Current action indicator** | User request | `current_action` property on tasks | ✅ |
| **Full agent output viewing** | User request | Chat panel with full history | ✅ |

### Agent Integration Requirements

| Requirement | Source | Implementation | Status |
|-------------|--------|----------------|--------|
| **OpenClaw integration** | User request | `OpenClawService` class | ✅ |
| **Custom skill with API calls** | User request | `skills/knowledge-os/SKILL.md` | ✅ |
| **Agent chat interface** | User request | `AgentsPage` with chat panel | ✅ |
| **Sidebar + embedded chat** | User request | Collapsible sidebar + slide-over chat | ✅ |
| **Chat without task** | User request | `POST /api/v1/agents/{name}/chat` | ✅ |
| **Chat logs in Qdrant** | User request | `chat_logs` collection | ✅ |
| **Agent status indicators** | User request | Status badges (active/idle/busy/offline) | ✅ |
| **Real-time agent updates** | User request | WebSocket events for agent activity | ✅ |
| **Gateway configurable** | User request | `OPENCLAW_GATEWAY_URL` env var | ✅ |
| **Optional on some machines** | User request | `OPENCLAW_ENABLED` flag | ✅ |

### Context & Intelligence Requirements

| Requirement | Source | Implementation | Status |
|-------------|--------|----------------|--------|
| **Include all relevant context** | User request | `ContextBuilderService` | ✅ |
| **Automatic context gathering** | User request | Parent, linked objects, files, memories | ✅ |
| **User can add context** | User request | `additional_context` parameter | ✅ |
| **Don't limit context** | User request | `MAX_CONTEXT_TOKENS=4000` | ✅ |
| **Qdrant pointers, not summaries** | User request | `qdrant_pointers` in context package | ✅ |
| **Semantic search for related files** | User request | `_find_related_files()` method | ✅ |
| **Agent memories included** | User request | `_find_relevant_memories()` method | ✅ |

### File Indexing Requirements

| Requirement | Source | Implementation | Status |
|-------------|--------|----------------|--------|
| **User picks folders to watch** | User request | Settings UI + `watched_folders` table | ✅ |
| **Files stored as objects** | User request | `file` object type, `files` collection | ✅ |
| **Full text extraction** (PDF, Word) | User request | PyMuPDF, python-docx | ✅ |
| **Image understanding** (CLIP) | User request | `images` collection, CLIP embeddings | ✅ |
| **Code semantic understanding** | User request | `code` collection, AST parsing | ✅ |
| **Real-time watching** | User request | `watchdog` library, `FileWatcherService` | ✅ |
| **Recursive watching** | User request | `recursive` flag per folder | ✅ |
| **Include/exclude patterns** | User request | Configurable patterns per folder | ✅ |

### UI/UX Requirements

| Requirement | Source | Implementation | Status |
|-------------|--------|----------------|--------|
| **Capacities-inspired UI** | User request | Object cards, properties panel | ✅ |
| **Collapsible sidebar** | User request | `Sidebar` component with collapse | ✅ |
| **Desktop-first** | User request | No mobile constraints in design | ✅ |
| **Real-time updates** | User request | WebSocket with auto-reconnect | ✅ |
| **Task priority visualization** | User request | Color-coded priority badges | ✅ |
| **Agent status in sidebar** | User request | Agent list with status dots | ✅ |
| **Watched folders in sidebar** | User request | Folder list in sidebar | ✅ |

### Backup Requirements

| Requirement | Source | Implementation | Status |
|-------------|--------|----------------|--------|
| **All 3 strategies** | User request | Snapshots + Markdown + Git | ✅ |
| **Configurable** | User request | All settings in env vars | ✅ |
| **Qdrant snapshots** | User request | `snapshot_interval_hours` | ✅ |
| **Markdown export** | User request | `markdown_export_enabled` | ✅ |
| **Git sync** | User request | `git_backup_enabled` | ✅ |

### Technical Requirements

| Requirement | Source | Implementation | Status |
|-------------|--------|----------------|--------|
| **WebSocket** (not SSE) | User request | `websocket_manager.py` | ✅ |
| **FastAPI backend** | User request | `main.py` with FastAPI | ✅ |
| **React frontend** | User request | Vite + React + TypeScript | ✅ |
| **Qdrant for vectors** | User request | 8 collections defined | ✅ |
| **SQLite for metadata** | User request | `sqlite.py` | ✅ |

---

## Chat Transcript Summary

### Initial Request (User)
> "I want to build a fully functional qdrant database to run at my home in a docker container for my AI agents to utilize I am new to qdrant and Im not sure how it works how to interact with it exactly what it can do even and even more all the ways I can use it. I want you to research and have an understanding of all of this and walk me through some use cases even maybe some unconventional ones."

### Key Decisions & Requirements from Chat

#### 1. Qdrant Understanding
- Qdrant is a vector database for semantic search
- Stores embeddings (vectors) from AI models
- Finds similar items by meaning, not keywords
- Supports filtering, quantization, multitenancy

#### 2. Initial Vision (User)
> "I want to build this database that my agents can use as memory and such as you see here but also.. I want it to be able to index my files and store metadata and such so my agents are aware of my files where they are and what they contain and I want to have a notion style interface for taking notes and managing my tasks as well as a visualizer for viewing and managing everything else the default dashboard has in it."

#### 3. Outliner + Task System Requirements
> "IT does, but.. I want to make sure it works like an outliner and being that the tasks system in it works in a way that I can assign it to various agents and then the agent will work the task and such updaing my notes and files as needed... if that makes sense. It would also be nice to be able to embed agent chat interfaces into it so I can interact with them spcidically openclaw agents if that makes sense"

**Key decisions:**
- Logseq/Roam style outliner
- Unlimited depth
- Block references `((block-id))`
- Backlinks critical
- Tagging for agents, files, notes
- Agent assignment via dropdown
- Agents can update notes/files
- Sidebar + embedded chat
- Chat without task

#### 4. Object Model (Capacities/Anytype style)
> "I would like each page or entry in the notes to be treated like an object if thats possible... similar to capacities https://capacities.io/ and anytype. Allowing relations ships between them and things"

**Key decisions:**
- Object-based (not just documents)
- Types: page, task, person, book, meeting, agent, file, etc.
- Relationships between objects
- Properties per type
- Layouts (default, profile, card, encyclopedia)

#### 5. Task Assignment Flow
> "Maybe since we are assigning them via our api the task can also intelligent include all relevant and relationalship context from qdrant when its assigned? giving the agent al the info it needs off the bat"

**Key decisions:**
- Store task in Qdrant
- Build context package automatically
- Include: parent object, linked objects, related files, agent memories, recent chat
- User can add more context
- Don't limit context (4000 tokens)
- Qdrant pointers, not summaries

#### 6. Priority-Based Assignment
> "Maybe heartbeat can be for the low or no priority tasks to fill time so its always productive and the assign is for tasks that need to be done now"

**Key decisions:**
- Direct API: urgent/high/medium
- HEARTBEAT: low priority
- Process in priority order

#### 7. Agent Experience
> "the indicator should jsut show researching, working, what ever stage or current action as a brief blurb thing but when clicking on an inprogress task it woudl be nice to see full agent output and chat log"

**Key decisions:**
- `current_action` property ("researching", "writing", etc.)
- Full chat history in Qdrant
- Click to view full output
- Real-time status updates

#### 8. File Indexing
> "I want all of that stored" (text, PDF, code, images)

**Key decisions:**
- User picks folders via UI
- Recursive watching
- Full text extraction
- CLIP for images
- Code semantic parsing
- Files stored as objects

#### 9. UI/UX
> "I will let you make best call on how the agent streams"
> "it shoudl be automatic and allow the user to add things they feel relevant"
> "no you should be able to collapse side bar"
> "yes start a chat without a task to just talk to an agent"
> "Yes exactly user picks fodler and then we watch"
> "all backups should be configurable"
> "Websocket is better"
> "dont limit the desktop app for mobile"

**Key decisions:**
- WebSocket for real-time
- Collapsible sidebar
- Agent streams via API calls
- User adds context
- Configurable backups
- Desktop-first

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                               │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  React + TypeScript Frontend                                      │   │
│  │  ├── Outliner Editor (Slate.js)                                   │   │
│  │  ├── Sidebar (Collapsible)                                        │   │
│  │  ├── Task Management                                              │   │
│  │  ├── Agent Chat Panel                                             │   │
│  │  └── File Browser                                                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                              │ HTTP/WebSocket                            │
└──────────────────────────────┼──────────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────────┐
│                              ▼ API LAYER                                 │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  FastAPI Backend                                                  │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐   │   │
│  │  │ REST API    │  │ WebSocket   │  │ Background Services     │   │   │
│  │  │ Routes      │  │ Manager     │  │                         │   │   │
│  │  │             │  │             │  │ • FileWatcherService    │   │   │
│  │  │ /objects    │  │ /ws         │  │ • EmbeddingService      │   │   │
│  │  │ /blocks     │  │             │  │ • BackupService         │   │   │
│  │  │ /tasks      │  │ Broadcasts  │  │ • OpenClawService       │   │   │
│  │  │ /search     │  │ updates     │  │ • ContextBuilder        │   │   │
│  │  │ /agents     │  │             │  │                         │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────────┐
│                              ▼ DATA LAYER                                │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────────────────┐   │
│  │    QDRANT     │  │   SQLITE      │  │      FILESYSTEM           │   │
│  │   (Vectors)   │  │  (Metadata)   │  │      WATCHER              │   │
│  │               │  │               │  │                           │   │
│  │ • objects     │  │ • settings    │  │ • User-selected folders   │   │
│  │ • blocks      │  │ • watched_folders│ • Real-time watching     │   │
│  │ • relations   │  │ • file_sync   │  │ • Content extraction      │   │
│  │ • files       │  │ • backup_log  │  │ • CLIP for images         │   │
│  │ • images      │  │               │  │                           │   │
│  │ • code        │  │               │  │                           │   │
│  │ • memories    │  │               │  │                           │   │
│  │ • chat_logs   │  │               │  │                           │   │
│  └───────────────┘  └───────────────┘  └───────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────────┐
│                              ▼ EXTERNAL                                  │
│  ┌───────────────┐  ┌───────────────┐                                   │
│  │  OPENCLAW     │  │   EMBEDDING   │                                   │
│  │   GATEWAY     │  │    MODELS     │                                   │
│  │               │  │               │                                   │
│  │ • Agent exec  │  │ • all-MiniLM  │                                   │
│  │ • HEARTBEAT   │  │ • CLIP        │                                   │
│  │ • Custom skill│  │               │                                   │
│  └───────────────┘  └───────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Model

### Qdrant Collections

#### 1. Objects Collection

```yaml
name: objects
vector_size: 384
distance: Cosine

payload_schema:
  id: uuid
  type: enum[page, task, person, book, meeting, agent, file, folder, image, code]
  title: string
  icon: string
  content: string  # For embedding
  properties:
    # Common
    tags: [string]
    created_at: datetime
    updated_at: datetime
    created_by: string
    
    # Task-specific
    status: enum[todo, in-progress, blocked, review, done]
    priority: enum[low, medium, high, urgent]
    due_date: datetime
    assigned_to: string
    completed_at: datetime
    context_included: [uuid]
    current_action: string
    
    # Person-specific
    email: string
    phone: string
    company: string
    role: string
    
    # Book-specific
    author: string
    rating: integer
    
    # File-specific
    file_path: string
    file_size: integer
    file_type: string
    checksum: string
    is_watched: boolean
    
    # Agent-specific
    agent_name: string
    capabilities: [string]
    agent_status: enum[active, idle, busy, offline]
    last_seen: datetime
  
  layout: enum[default, profile, card, encyclopedia]
```

#### 2. Blocks Collection

```yaml
name: blocks
vector_size: 384
distance: Cosine

payload_schema:
  id: uuid
  object_id: uuid
  content: string
  type: enum[paragraph, heading, todo, bullet, numbered, quote, code, divider, image, embed, callout]
  level: integer
  properties:
    checked: boolean
    language: string
    collapsed: boolean
    assigned_to: string
    due_date: datetime
    priority: string
  order: integer
  parent_id: uuid
  references: [uuid]
  referenced_by: [uuid]
```

#### 3. Relations Collection

```yaml
name: relations
vector_size: 384  # Small vectors for context
distance: Cosine

payload_schema:
  id: uuid
  source_id: uuid
  source_type: enum[object, block]
  target_id: uuid
  target_type: enum[object, block]
  relation_type: enum[links_to, assigned_to, parent_of, child_of, tagged_with, mentions, references, embedded_in]
  context: string
  created_at: datetime
```

#### 4. Files Collection

```yaml
name: files
vector_size: 384
distance: Cosine
on_disk_payload: true

payload_schema:
  id: uuid
  object_id: uuid
  path: string
  relative_path: string
  filename: string
  extension: string
  mime_type: string
  size_bytes: integer
  content_text: string
  content_preview: string
  checksum: string
  last_modified: datetime
  last_indexed: datetime
  index_status: enum[pending, processing, indexed, error]
  error_message: string
  metadata:
    title: string
    author: string
    pages: integer
    word_count: integer
```

#### 5. Images Collection

```yaml
name: images
vector_size: 512  # CLIP dimension
distance: Cosine
on_disk_payload: true

payload_schema:
  id: uuid
  object_id: uuid
  path: string
  filename: string
  description: string
  tags: [string]
  source_object: uuid
  source_file: uuid
```

#### 6. Code Collection

```yaml
name: code
vector_size: 384
distance: Cosine
on_disk_payload: true

payload_schema:
  id: uuid
  file_id: uuid
  object_id: uuid
  file_path: string
  language: string
  line_start: integer
  line_end: integer
  content: string
  docstring: string
  signature: string
  type: enum[function, class, method, variable]
  name: string
  class_name: string
```

#### 7. Agent Memories Collection

```yaml
name: agent_memories
vector_size: 384
distance: Cosine

payload_schema:
  id: uuid
  agent_name: string
  memory_type: enum[observation, action, reflection, fact]
  content: string
  importance: integer  # 1-10
  related_objects: [uuid]
  related_tasks: [uuid]
  session_id: string
  timestamp: datetime
```

#### 8. Chat Logs Collection

```yaml
name: chat_logs
vector_size: 384
distance: Cosine

payload_schema:
  id: uuid
  session_id: uuid
  agent_name: string
  message_type: enum[user, agent, system]
  content: string
  timestamp: datetime
  related_task: uuid
  metadata:
    agent_thoughts: string
    tools_used: [string]
    files_created: [string]
```

### SQLite Schema

```sql
-- Settings
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Watched folders
CREATE TABLE watched_folders (
    id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    recursive BOOLEAN DEFAULT 1,
    include_patterns TEXT DEFAULT '["*"]',
    exclude_patterns TEXT DEFAULT '[".git", "node_modules"]',
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- File sync status
CREATE TABLE file_sync_status (
    file_path TEXT PRIMARY KEY,
    checksum TEXT,
    last_modified TIMESTAMP,
    index_status TEXT DEFAULT 'pending',
    error_message TEXT,
    object_id TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Backup log
CREATE TABLE backup_log (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Agent sessions
CREATE TABLE agent_sessions (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    task_id TEXT,
    status TEXT DEFAULT 'active',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    summary TEXT,
    messages_count INTEGER DEFAULT 0
);
```

---

## API Specification

### Objects API

#### List Objects
```http
GET /api/v1/objects
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| type | string | Filter by object type |
| limit | integer | Max results (1-1000, default 50) |
| offset | integer | Pagination offset |

**Response:**
```json
{
  "objects": [
    {
      "id": "uuid",
      "type": "task",
      "title": "Research vector databases",
      "icon": "✅",
      "content": "Research vector databases for our project",
      "properties": {
        "status": "in-progress",
        "priority": "urgent",
        "assigned_to": "researcher",
        "tags": ["research", "databases"]
      },
      "layout": "default"
    }
  ],
  "total": 42
}
```

#### Get Object
```http
GET /api/v1/objects/{id}
```

**Response:**
```json
{
  "id": "uuid",
  "type": "task",
  "title": "Research vector databases",
  "icon": "✅",
  "content": "Research vector databases for our project",
  "properties": { ... },
  "layout": "default"
}
```

#### Create Object
```http
POST /api/v1/objects
```

**Request Body:**
```json
{
  "type": "task",
  "title": "Research vector databases",
  "icon": "✅",
  "content": "Research vector databases for our project",
  "properties": {
    "status": "todo",
    "priority": "high",
    "tags": ["research"]
  },
  "layout": "default"
}
```

**Response:**
```json
{
  "id": "uuid",
  "type": "task",
  "title": "Research vector databases",
  ...
}
```

#### Update Object
```http
PUT /api/v1/objects/{id}
```

**Request Body:**
```json
{
  "title": "Updated title",
  "properties": {
    "status": "in-progress"
  }
}
```

#### Delete Object
```http
DELETE /api/v1/objects/{id}
```

**Response:**
```json
{
  "message": "Object deleted",
  "id": "uuid"
}
```

### Blocks API

#### Get Object Blocks
```http
GET /api/v1/blocks/object/{object_id}
```

**Response:**
```json
{
  "blocks": [
    {
      "id": "uuid",
      "object_id": "uuid",
      "content": "Meeting notes",
      "type": "heading",
      "level": 1,
      "order": 0
    },
    {
      "id": "uuid",
      "object_id": "uuid",
      "content": "Research vector databases",
      "type": "todo",
      "properties": {
        "checked": false,
        "assigned_to": "researcher"
      },
      "order": 1
    }
  ]
}
```

#### Create Block
```http
POST /api/v1/blocks?object_id={object_id}
```

**Request Body:**
```json
{
  "content": "New block content",
  "type": "paragraph",
  "level": 0,
  "parent_id": null
}
```

#### Update Block
```http
PUT /api/v1/blocks/{id}
```

**Request Body:**
```json
{
  "content": "Updated content",
  "properties": {
    "checked": true
  }
}
```

#### Batch Update Blocks
```http
POST /api/v1/blocks/batch-update
```

**Request Body:**
```json
{
  "blocks": [
    {"id": "uuid", "order": 0, "parent_id": null},
    {"id": "uuid", "order": 1, "parent_id": null}
  ]
}
```

### Tasks API

#### List Tasks
```http
GET /api/v1/tasks
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| status | string | Filter by status |
| priority | string | Filter by priority |
| assigned_to | string | Filter by assigned agent |

**Response:**
```json
{
  "tasks": [...],
  "total": 10,
  "by_status": {
    "todo": 3,
    "in-progress": 5,
    "done": 2
  },
  "by_priority": {
    "urgent": 1,
    "high": 3,
    "medium": 4,
    "low": 2
  }
}
```

#### Assign Task
```http
POST /api/v1/tasks/{id}/assign
```

**Request Body:**
```json
{
  "task_id": "uuid",
  "agent_name": "researcher",
  "priority": "urgent",
  "include_context": true,
  "additional_context": ["uuid1", "uuid2"]
}
```

**Response:**
```json
{
  "message": "Task assigned",
  "task_id": "uuid",
  "agent_name": "researcher",
  "assignment_type": "direct"
}
```

#### Update Task Status
```http
POST /api/v1/tasks/{id}/status
```

**Request Body:**
```json
{
  "task_id": "uuid",
  "agent_name": "researcher",
  "status": "in-progress",
  "current_action": "researching",
  "notes": "Found 3 relevant papers"
}
```

#### Get Task Context
```http
GET /api/v1/tasks/{id}/context
```

**Response:**
```json
{
  "task_id": "uuid",
  "task_title": "Research vector databases",
  "task_content": "Research vector databases for our project",
  "priority": "urgent",
  "parent_object": {
    "id": "uuid",
    "title": "Project Alpha",
    "type": "page"
  },
  "linked_objects": [...],
  "related_files": [...],
  "relevant_memories": [...],
  "recent_chat": [...],
  "qdrant_pointers": {
    "task_object_id": "uuid",
    "parent_object_id": "uuid"
  }
}
```

### Agents API

#### List Agents
```http
GET /api/v1/agents
```

**Response:**
```json
{
  "agents": [
    {
      "id": "uuid",
      "type": "agent",
      "title": "Researcher",
      "properties": {
        "agent_name": "researcher",
        "capabilities": ["Research", "Analysis"],
        "agent_status": "active"
      }
    }
  ]
}
```

#### Chat with Agent
```http
POST /api/v1/agents/{name}/chat
```

**Request Body:**
```json
{
  "content": "Can you research Qdrant vs Pinecone?",
  "session_id": "main"
}
```

#### Get Chat History
```http
GET /api/v1/agents/{name}/chat?session_id={session_id}
```

### Search API

#### Semantic Search
```http
GET /api/v1/search?q={query}&limit=10
```

**Response:**
```json
{
  "query": "vector databases",
  "results": [
    {
      "id": "uuid",
      "collection": "objects",
      "title": "Research vector databases",
      "score": 0.89
    }
  ],
  "total": 25
}
```

#### Find Similar
```http
GET /api/v1/search/similar/{object_id}?limit=5
```

---

## WebSocket Events

### Connection

Connect to: `ws://localhost:8000/ws`

### Client → Server

| Event | Description |
|-------|-------------|
| `ping` | Keep connection alive |
| `subscribe` | Subscribe to a channel |

### Server → Client

#### Object Events

```json
{
  "type": "object.created",
  "data": {
    "object_id": "uuid",
    "type": "task",
    "title": "New Task"
  }
}
```

```json
{
  "type": "object.updated",
  "data": {
    "object_id": "uuid",
    "changes": ["title", "properties"]
  }
}
```

```json
{
  "type": "object.deleted",
  "data": {
    "object_id": "uuid"
  }
}
```

#### Task Events

```json
{
  "type": "task.assigned",
  "data": {
    "task_id": "uuid",
    "agent_name": "researcher",
    "priority": "urgent",
    "assignment_type": "direct"
  }
}
```

```json
{
  "type": "task.status_changed",
  "data": {
    "task_id": "uuid",
    "old_status": "todo",
    "new_status": "in-progress",
    "agent_name": "researcher",
    "current_action": "researching"
  }
}
```

```json
{
  "type": "task.progress_update",
  "data": {
    "task_id": "uuid",
    "agent_name": "researcher",
    "update": "Found 3 relevant papers",
    "timestamp": "2024-04-04T12:00:00Z"
  }
}
```

```json
{
  "type": "task.completed",
  "data": {
    "task_id": "uuid",
    "agent_name": "researcher",
    "notes": "Completed research",
    "artifacts_created": ["uuid1", "uuid2"]
  }
}
```

#### Agent Events

```json
{
  "type": "agent.status_changed",
  "data": {
    "agent_name": "researcher",
    "old_status": "idle",
    "new_status": "busy"
  }
}
```

```json
{
  "type": "agent.current_action",
  "data": {
    "agent_name": "researcher",
    "action": "researching vector databases",
    "task_id": "uuid"
  }
}
```

#### Chat Events

```json
{
  "type": "chat.message",
  "data": {
    "session_id": "main",
    "agent_name": "researcher",
    "message_type": "agent",
    "content": "I found some interesting results...",
    "timestamp": "2024-04-04T12:00:00Z"
  }
}
```

#### File Events

```json
{
  "type": "file.indexed",
  "data": {
    "file_id": "uuid",
    "file_path": "/home/user/doc.pdf",
    "object_id": "uuid"
  }
}
```

---

## OpenClaw Integration

### Gateway API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/sessions/main/messages` | POST | Send message to agent |
| `/api/v1/sessions/{id}/history` | GET | Get session history |
| `/api/v1/agents/{name}/status` | GET | Get agent status |

### Task Assignment Flow

```
1. User creates task in UI
   ↓
2. User assigns to @agent-name
   ↓
3. Backend builds context package:
   • Task itself
   • Parent object
   • Linked objects
   • Related files (semantic search)
   • Agent memories
   • Recent chat
   ↓
4. Backend calls OpenClaw Gateway
   POST /api/v1/sessions/main/messages
   ↓
5. Agent receives task + context
   ↓
6. Agent works on task
   ↓
7. Agent updates via skill API
   ↓
8. UI receives real-time updates
```

### Priority-Based Assignment

| Priority | Assignment Method |
|----------|-------------------|
| `urgent`, `high`, `medium` | Direct assignment via Gateway API |
| `low` | Write to HEARTBEAT.md for background processing |

### Knowledge OS Skill

```yaml
name: knowledge-os
description: Integrate with Knowledge OS to update tasks, create notes, and log progress

tools:
  update_task_status:
    args:
      task_id: string
      status: enum[todo, in-progress, blocked, review, done]
      current_action: string
      notes: string
  
  add_progress_update:
    args:
      task_id: string
      update: string
  
  create_note:
    args:
      title: string
      content: string
      tags: [string]
      related_task_id: string
  
  add_chat_message:
    args:
      session_id: string
      content: string
      message_type: enum[agent, system]
      metadata: object
  
  search_knowledge:
    args:
      query: string
      limit: integer
  
  get_object:
    args:
      object_id: string
```

---

## File Indexing

### Supported File Types

| Type | Extensions | Extraction Method |
|------|------------|-------------------|
| Text | .md, .txt | Direct read |
| PDF | .pdf | PyMuPDF |
| Word | .docx, .doc | python-docx |
| Code | .py, .js, .ts, etc. | AST parsing |
| Images | .jpg, .png, .gif | CLIP embeddings |

### Watch Configuration

```python
{
  "path": "/home/user/Documents",
  "recursive": true,
  "include_patterns": ["*.md", "*.txt", "*.pdf"],
  "exclude_patterns": [".git", "node_modules"]
}
```

### Indexing Process

```
1. File watcher detects change
   ↓
2. Calculate checksum
   ↓
3. Check if already indexed
   ↓
4. Extract content
   ↓
5. Generate embedding
   ↓
6. Store in Qdrant
   ↓
7. Create/update object
   ↓
8. Broadcast file.indexed event
```

---

## Backup System

### Strategy 1: Qdrant Snapshots

- **Frequency**: Daily (configurable)
- **Retention**: 7 snapshots
- **Trigger**: Scheduled + before major operations
- **Storage**: Qdrant snapshots directory

### Strategy 2: Markdown Export

- **Frequency**: Weekly (configurable)
- **Format**: Obsidian-compatible
- **Includes**:
  - All objects as markdown files
  - Wiki-links for relations
  - Frontmatter for properties
- **Storage**: Configurable path

### Strategy 3: Git Sync

- **Frequency**: Every 30 minutes (configurable)
- **Optional remote**: GitHub, GitLab, etc.
- **Commit message**: Auto-generated with timestamp

---

## Frontend Components

### Layout Components

| Component | Description |
|-----------|-------------|
| `MainLayout` | Main app layout with sidebar and content area |
| `Sidebar` | Collapsible sidebar with spaces, agents, folders |
| `Header` | Top bar with search and actions |

### Page Components

| Component | Route | Description |
|-----------|-------|-------------|
| `OutlinerPage` | `/`, `/object/:id` | Object editor with blocks |
| `TasksPage` | `/tasks` | Task management |
| `FilesPage` | `/files` | File browser |
| `AgentsPage` | `/agents` | Agent list and chat |
| `SettingsPage` | `/settings` | Configuration |

### UI Components (shadcn/ui)

| Component | Usage |
|-----------|-------|
| `Button` | Actions |
| `ScrollArea` | Scrollable content |
| `Collapsible` | Expandable sections |
| `Separator` | Visual dividers |

### State Management

| Store | Purpose |
|-------|---------|
| `useWebSocketStore` | WebSocket connection and messages |
| React Query | Server state (objects, tasks, etc.) |
| Zustand | Client state (UI, selections) |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | 0.0.0.0 | Server bind address |
| `PORT` | 8000 | Server port |
| `DEBUG` | false | Debug mode |
| `QDRANT_HOST` | localhost | Qdrant host |
| `QDRANT_PORT` | 6333 | Qdrant port |
| `QDRANT_API_KEY` | - | Qdrant API key |
| `OPENCLAW_GATEWAY_URL` | http://localhost:18789 | OpenClaw URL |
| `OPENCLAW_TOKEN` | - | OpenClaw token (alias: `OPENCLAW_GATEWAY_TOKEN`) |
| `OPENCLAW_ENABLED` | true | Enable OpenClaw |
| `EMBEDDING_MODEL` | all-MiniLM-L6-v2 | Text embedding model |
| `CLIP_MODEL` | openai/clip-vit-base-patch32 | Image embedding model |
| `MAX_FILE_SIZE_MB` | 50 | Max file size to index |
| `BACKUP_ENABLED` | true | Enable backups |
| `SNAPSHOT_INTERVAL_HOURS` | 24 | Snapshot frequency |
| `MARKDOWN_EXPORT_ENABLED` | true | Enable markdown export |
| `MARKDOWN_EXPORT_PATH` | ./backups/markdown | Export path |
| `GIT_BACKUP_ENABLED` | false | Enable Git sync |
| `MAX_CONTEXT_TOKENS` | 4000 | Max context for agents |

### Default Exclude Patterns

```python
[
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".pytest_cache", "*.tmp", "*.log", ".DS_Store", "Thumbs.db",
    ".idea", ".vscode", "dist", "build", ".next"
]
```

### Default Include Patterns

```python
[
    "*.md", "*.txt", "*.pdf", "*.docx", "*.doc",
    "*.py", "*.js", "*.ts", "*.jsx", "*.tsx",
    "*.html", "*.css", "*.scss", "*.json", "*.yaml", "*.yml",
    "*.rs", "*.go", "*.java", "*.cpp", "*.c", "*.h",
    "*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp", "*.svg"
]
```

---

## Performance Considerations

### Vector Dimensions

| Collection | Dimension | Model |
|------------|-----------|-------|
| objects | 384 | all-MiniLM-L6-v2 |
| blocks | 384 | all-MiniLM-L6-v2 |
| files | 384 | all-MiniLM-L6-v2 |
| images | 512 | CLIP |
| code | 384 | all-MiniLM-L6-v2 |

### Memory Usage Estimates

| Data Size | RAM (No Quantization) | RAM (Scalar Quantization) |
|-----------|----------------------|---------------------------|
| 100K vectors | ~150 MB | ~40 MB |
| 1M vectors | ~1.5 GB | ~400 MB |
| 10M vectors | ~15 GB | ~4 GB |

### Optimization Tips

1. Enable `on_disk_payload` for large collections (files, images)
2. Use scalar quantization for large datasets
3. Index payload fields used in filters
4. Batch upserts instead of individual calls
5. Use gRPC for high-throughput operations

---

## Security Considerations

1. **API Key**: Set `QDRANT_API_KEY` for production
2. **OpenClaw Token**: Secure your gateway token
3. **CORS**: Configure allowed origins
4. **File Access**: Only index user-selected folders
5. **Agent Permissions**: Agents can only access what the skill allows

---

## Future Enhancements

- [ ] Mobile-responsive design
- [ ] Offline mode with sync
- [ ] Collaborative editing
- [ ] Plugin system
- [ ] Advanced graph visualization
- [ ] AI-powered suggestions
- [ ] Voice input
- [ ] Calendar integration
