# Knowledge OS

[![Tests](https://img.shields.io/badge/tests-289%20passing-brightgreen)](https://github.com/ghively/knowledge-os)
[![Version](https://img.shields.io/badge/version-v0.3.0-blue)](https://github.com/ghively/knowledge-os/releases)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A **knowledge management system** with a built-in AI agent runtime. Create objects, take notes, manage tasks, and chat with AI agents — works with any LLM provider.

## Features

### Knowledge Management
- **Object-based notes** — Everything is an object (page, task, person, book, meeting, agent, file, folder, image, code)
- **Block-based outliner editor** — Logseq/Roam-style with unlimited nesting depth, slash commands, and block references
- **Semantic search** — Find content by meaning, not just keywords (Qdrant vector DB)
- **Real-time updates** — WebSocket-powered live collaboration
- **#tags and @mentions** — Auto-parsed from content, stored as structured properties
- **File management** — Auto-index from watched folders, PDF/markdown/code/image support

### AI Agent System (v0.3.0)
- **Markdown-first agent identity** — Define agents with AGENT.md, SOUL.md, MEMORY.md, TOOLS.md (like OpenClaw)
- **Multi-provider LLM routing** — Ollama (default), OpenAI, Anthropic, Google — swap without changing agent code
- **ReAct agent loop** — Agents think, use tools, observe, and loop until done
- **CLI agent delegation** — Agents delegate to Codex, Claude Code, Kimi CLI, or Gemini CLI as tools
- **MCP server support** — Connect external tool servers (Brave Search, filesystem, etc.)
- **Auto-memory** — Daily logs, Qdrant semantic retrieval, periodic MEMORY.md curation
- **Sub-agent spawning** — Parallel sub-agent execution with depth limits
- **Streaming responses** — Real-time SSE streaming with tool call indicators
- **Scheduled tasks** — Autonomous background execution (cron-like scheduling)
- **Webhook triggers** — External events can trigger agent actions
- **Agent templates** — Pre-built configs: Researcher, Coder, Analyst, Writer, Personal Assistant
- **Tool approval flow** — Destructive operations require human confirmation
- **Rate limiting & budgets** — Per-agent token limits and usage tracking
- **Comprehensive audit logging** — Every agent decision logged and queryable

### PWA Support
- **Installable** — Add to home screen on mobile/desktop
- **Push notifications** — Browser notification support
- **Responsive design** — Mobile-friendly UI with touch controls

### Logging & Monitoring
- **Structured JSON logging** — structlog with request tracing (X-Request-ID)
- **Log viewer UI** — Filter, search, auto-refresh, WebSocket streaming, JSON export
- **System status endpoint** — Version, uptime, request counts, WebSocket connections

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│    Backend      │────▶│     Qdrant      │
│  React/Vite     │     │   FastAPI       │     │  Vector DB      │
│   Port: 3010    │◄────│   Port: 8010    │◄────│   Port: 6335    │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
               ┌─────────┐ ┌────────┐ ┌──────────┐
               │  LLM    │ │ SQLite │ │  CLI     │
               │(external│ │ (DB)   │ │  Agents  │
               │ Ollama, │ │         │ │ Codex,   │
               │ OpenAI) │ │         │ │ Claude,  │
               └─────────┘ └────────┘ │ Kimi,    │
                                     │ Gemini   │
                                     └──────────┘
```

### Agent Runtime Components

```
Agent Orchestrator
├── IdentityLoader — parse AGENT.md, SOUL.md, MEMORY.md, TOOLS.md
├── LLMRouter — Ollama/OpenAI/Anthropic/Google with streaming
├── ToolRegistry
│   ├── Native tools (create_object, search, manage_tasks, etc.)
│   ├── CLI Agent tools (codex, claude_code, kimi, gemini, opencode)
│   └── MCP Client (external tool servers via stdio/HTTP)
├── AgentLoop — ReAct pattern with sub-agent support
├── MemoryManager — daily logs, Qdrant retrieval, MEMORY.md curation
├── SessionManager — SQLite conversation persistence
├── Scheduler — autonomous background task execution
├── Webhooks — external event triggers
└── AuditLogger — comprehensive decision logging
```

### Qdrant Collections
1. `objects` — Main objects (pages, tasks, people, etc.)
2. `blocks` — Block-level content for outliner
3. `relations` — Object relationships and backlinks
4. `files` — File metadata and content
5. `images` — Image embeddings (CLIP)
6. `code` — Code file embeddings
7. `agent_memories` — Agent conversation history
8. `chat_logs` — User-agent chat sessions
9. `tags` — Tag index
10. `sessions` — Session metadata

## Quick Start

### Prerequisites
- **Docker & Docker Compose**
- **An LLM provider** — Ollama (local), OpenAI, Anthropic, or Google

### 1. Set Up an LLM Provider

The agent runtime works with any OpenAI-compatible LLM. **Ollama** (recommended for local, free inference) is the default but must be running separately — it's not part of the Docker stack.

**Option A: Ollama (local, free)**
```bash
# Install Ollama
brew install ollama  # macOS
# Or: curl -fsSL https://ollama.ai/install.sh | sh  # Linux

# Pull a model
ollama pull qwen2.5-coder:7b

# Start Ollama (if not running)
ollama serve
```

**Option B: Cloud provider (OpenAI, Anthropic, Google)**
```bash
# Set API key in .env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-xxx
```

**Recommended models:**
| Model | Provider | Size | Best For |
|-------|----------|------|----------|
| `qwen2.5-coder:7b` | Ollama (local) | 4.7GB | Tool calling, code, reasoning |
| `deepseek-r1:8b` | Ollama (local) | 5.2GB | Deep reasoning |
| `llama3.1:8b` | Ollama (local) | 4.9GB | General-purpose |
| `gpt-4o-mini` | OpenAI | API | Fast, cheap, capable |
| `claude-sonnet-4-20250514` | Anthropic | API | Best reasoning |

### 2. Clone and Start

```bash
git clone https://github.com/ghively/knowledge-os.git
cd knowledge-os

# Start all services
docker compose up -d --build
```

### 3. Access the Application

- **App**: http://localhost:3010
- **Backend API**: http://localhost:8010
- **Qdrant Dashboard**: http://localhost:6335/dashboard

### 4. Register and Create an Agent

1. Go to http://localhost:3010/register and create an account
2. Navigate to **Agents** → **Create Agent** → pick a template
3. Edit the agent's TOOLS.md to customize model, tools, and MCP servers
4. Start chatting!

## Configuration

### Environment Variables

```env
# Ports
FRONTEND_PORT=3010
BACKEND_PORT=8010
QDRANT_HTTP_PORT=6335
QDRANT_GRPC_PORT=6336

# LLM Provider (default: Ollama; set LLM_BASE_URL for custom endpoints)
# Override per-agent in TOOLS.md
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5-coder:7b
LLM_BASE_URL=
LLM_API_KEY=

# OpenClaw Integration (optional)
OPENCLAW_URL=http://host.docker.internal:18789
OPENCLAW_TOKEN=

# Embeddings
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### Agent Configuration

Each agent is defined by 4 markdown files in their directory (`backend/agents/{agent_name}/`). You can edit these through the UI or directly.

#### AGENT.md — Identity & Capabilities

```markdown
---
name: Researcher
model: qwen2.5-coder:7b
capabilities:
  - web_research
  - summarization
  - fact_checking
constraints:
  - Always cite sources
  - Never fabricate information
---

You are a research assistant. Your job is to find accurate information,
summarize findings, and provide sourced answers.

## Instructions
1. When given a question, break it into sub-questions
2. Use available tools to gather information
3. Cross-reference multiple sources
4. Provide concise, well-structured answers
```

#### SOUL.md — Personality & Behavior

```markdown
## Personality
- Curious and thorough
- Prefers precision over speed
- Honest about uncertainty

## Tone
- Professional but approachable
- Avoid jargon unless the user uses it
- Use bullet points for structured information

## Decision Making
- Always verify claims before presenting them
- If uncertain, say so explicitly
- Prefer primary sources over secondary
```

#### TOOLS.md — LLM, CLI Agents & MCP Servers

```markdown
## LLM Provider
provider: ollama
model: qwen2.5-coder:7b
temperature: 0.2
max_tokens: 2048
fallback_model: llama3.1:8b

## CLI Agents Available
- codex: coding, git, file operations
- claude_code: coding, analysis, file operations
- kimi: research, web search, coding (256K context)
- gemini: analysis, research, documentation (free tier)
- opencode: coding assistant

## MCP Servers
- name: brave-search
  transport: stdio
  command: npx
  args: ["-y", "@anthropic/mcp-server-brave-search"]
  env:
    BRAVE_API_KEY: sk-xxx

- name: filesystem
  transport: stdio
  command: npx
  args: ["-y", "@anthropic/mcp-server-filesystem", "/app/data"]
```

#### MEMORY.md — Long-Term Memory (auto-curated)

```markdown
# Auto-curated by the agent during memory curation tasks.

## User Preferences
- Prefers concise summaries over detailed reports
- Works in software engineering domain
- Timezone: America/Chicago

## Learned Context
- Project uses FastAPI + React stack
- Qdrant for vector storage
- Ollama for local LLM inference
```

#### memory/YYYY-MM-DD.md — Daily Logs (auto-written)

```markdown
# 2026-04-05

## Session 1
- User asked about microservices patterns
- Found 3 relevant articles via search
- Summarized key differences between monolith and microservices
```

### Creating Agents

**From the UI:**
1. Go to **Agents** → **Create Agent**
2. Pick a template (Researcher, Coder, Analyst, Writer, Personal Assistant)
3. Edit the identity files as needed
4. Start chatting

**Via API:**
```bash
# Create from template
curl -X POST http://localhost:8010/api/v1/agents/runtime/create-from-template \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"template": "researcher", "name": "my-researcher"}'

# Edit a file
curl -X PUT http://localhost:8010/api/v1/agents/runtime/my-researcher/files/TOOLS.md \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: text/markdown" \
  -d '## LLM Provider\nprovider: ollama\nmodel: deepseek-r1:8b'
```

### Agent Templates

| Template | Purpose | Best LLM |
|----------|---------|----------|
| **Researcher** | Web research, fact-checking | qwen2.5-coder:7b |
| **Coder** | Code generation, debugging | qwen2.5-coder:7b |
| **Analyst** | Data analysis, reports | llama3.1:8b |
| **Writer** | Content creation, editing | llama3.1:8b |
| **Personal Assistant** | General tasks, scheduling | qwen2.5-coder:7b |

### Switching LLM Providers

Change the provider and model in TOOLS.md:

```markdown
## LLM Provider
provider: openai           # ollama | openai | anthropic | google
model: gpt-4o-mini
base_url:                  # auto-detected for ollama; set for others
api_key: sk-xxx            # not needed for ollama
```

**Provider base URLs (auto-detected for Ollama):**
- Ollama: `http://host.docker.internal:11434/v1` (automatic)
- OpenAI: `https://api.openai.com/v1`
- Anthropic: `https://api.anthropic.com/v1`
- Google: `https://generativelanguage.googleapis.com/v1beta`

## Security

- **JWT authentication** — Required on all CRUD endpoints
- **Rate limiting** — Auth: 5/min, Write: 30/min, Read: 60/min, Per-agent limits
- **Persistent JWT secret** — Survives container restarts
- **Tool sandboxing** — Filesystem restrictions, timeouts, output truncation
- **Prompt injection defense** — Input/output sanitization
- **Tool approval flow** — Destructive operations require human confirmation
- **HMAC webhooks** — Signature verification on incoming webhooks
- **Audit logging** — Every agent decision logged

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` — Create account
- `POST /api/v1/auth/login` — Login → access_token + refresh_token
- `POST /api/v1/auth/refresh` — Refresh token
- `POST /api/v1/auth/logout` — Logout

### Objects
- `GET/POST /api/v1/objects` — List/Create
- `GET/PUT/DELETE /api/v1/objects/{id}` — CRUD

### Blocks
- `GET /api/v1/blocks/object/{object_id}` — Get blocks
- `POST /api/v1/blocks` — Create block
- `PUT /api/v1/blocks/{id}` — Update block
- `POST /api/v1/blocks/batch-update` — Batch update

### Tasks
- `GET /api/v1/tasks` — List tasks
- `POST /api/v1/tasks/{id}/assign` — Assign to agent
- `POST /api/v1/tasks/{id}/status` — Update status

### Agent Runtime
- `POST /api/v1/agents/runtime/chat` — Chat with agent (SSE stream)
- `GET /api/v1/agents/runtime/cli-status` — CLI agent availability
- `GET/POST/DELETE /api/v1/agents/runtime/sessions` — Session management
- `GET/PUT /api/v1/agents/runtime/{id}/files/{name}` — Edit agent markdown files
- `POST /api/v1/agents/runtime/{id}/curate-memory` — Trigger memory curation
- `GET /api/v1/agents/runtime/templates` — List agent templates
- `POST /api/v1/agents/runtime/create-from-template` — Create from template
- `GET/POST/DELETE /api/v1/agents/runtime/schedule` — Scheduled tasks
- `GET/POST/DELETE /api/v1/agents/runtime/webhooks` — Webhook management
- `GET /api/v1/agents/runtime/{id}/audit` — Audit log
- `GET /api/v1/agents/runtime/{id}/usage` — Token usage stats

### MCP Server Management
- `GET /api/v1/agents/runtime/mcp/servers` — List MCP servers
- `POST /api/v1/agents/runtime/mcp/servers` — Add server
- `DELETE /api/v1/agents/runtime/mcp/servers/{name}` — Remove server
- `POST /api/v1/agents/runtime/mcp/servers/{name}/connect` — Connect
- `POST /api/v1/agents/runtime/mcp/test` — Test connection

### Search (optional auth)
- `GET /api/v1/search?q={query}` — Semantic search
- `GET /api/v1/search/similar/{id}` — Find similar

### System
- `GET /api/v1/system/status` — System health
- `GET /api/v1/system/logs` — Structured logs
- `GET /api/v1/settings` — Settings
- `PUT /api/v1/settings` — Update settings

### WebSockets
- `ws://localhost:8010/ws/system` — System updates
- `ws://localhost:8010/ws/agents/{name}` — Agent-specific updates

## Development

### Docker Compose

```bash
docker compose up -d --build      # Start all services
docker compose down -v             # Stop and remove volumes (fresh start)
docker compose logs -f backend     # Backend logs
docker compose exec backend python -m pytest --tb=short  # Run tests
```

### Frontend Development

```bash
cd frontend
npm install
VITE_API_URL=http://127.0.0.1:8010 npm run dev
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, Python 3.11+, Pydantic v2 |
| Vector DB | Qdrant (8 collections) |
| Database | SQLite (aiosqlite) |
| LLM | Ollama (default), OpenAI, Anthropic, Google |
| Agent Runtime | ReAct loop, MCP client, CLI delegation |
| Auth | JWT + bcrypt, rate limiting via slowapi |
| Logging | structlog (JSON), rotating file handler |
| PWA | vite-plugin-pwa, Workbox |
| Real-time | WebSocket + SSE streaming |

## License

MIT License — See LICENSE file

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
