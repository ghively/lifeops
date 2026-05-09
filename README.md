# Knowledge OS

[![Version](https://img.shields.io/badge/version-v0.3.0-blue)](#version-history)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-production%20ready-brightgreen)](#status)

A **production-ready knowledge management system** with an integrated AI agent runtime. Create objects, take notes, manage tasks, and chat with autonomous AI agents — compatible with any LLM provider.

**Latest:** v0.3.0 | **Updated:** May 2026 | **Status:** ✅ Production Ready

---

## 🌟 Key Features

### 📚 Knowledge Management
- **Object-Based Notes** — Everything is an object with type, properties, relationships
- **Outliner Editor** — Block-based editing with unlimited nesting, slash commands, block references
- **Semantic Search** — Find content by meaning using Qdrant vector DB (384-dim embeddings)
- **Real-Time Collaboration** — WebSocket-powered live presence, cursor tracking, concurrent editing
- **Wiki Links & Backlinks** — `[[Note Title]]` references with automatic backlink tracking
- **Flexible Tagging** — `#tags` and `@mentions` auto-parsed and stored as structured properties
- **File Management** — Real-time folder watching with automatic indexing

### 🤖 AI Agent System (v0.3.0)
- **Markdown-First Agent Identity** — AGENT.md, SOUL.md, MEMORY.md, TOOLS.md definitions
- **Multi-Provider LLM Routing** — Ollama (default), OpenAI, Anthropic, Google without code changes
- **ReAct Agent Loop** — Think → Tool → Observe execution pattern with max 10 iterations
- **Tool Sandboxing** — Secure execution with filesystem restrictions, timeouts, approval gates
- **MCP Integration** — Connect external tool servers (stdio and HTTP transports)
- **Memory Management** — Semantic memory retrieval, daily curation, MEMORY.md auto-update
- **Sub-Agent Spawning** — Parallel execution with depth limits
- **Streaming Responses** — Real-time SSE streaming with tool call indicators
- **Scheduled Tasks** — Cron-based autonomous background execution
- **Webhook Triggers** — External events trigger agent actions with HMAC verification
- **Agent Templates** — Pre-built: Researcher, Coder, Analyst, Writer, Personal Assistant
- **Tool Approval Flow** — Human-in-the-loop for destructive operations
- **Rate Limiting** — Per-agent (100k tokens/day), per-user (1000 req/day), per-minute (10 req)
- **Comprehensive Audit** — Every decision logged with 90-day retention

### 🎯 Smart Features
- **Automatic Context Gathering** — Includes parents, links, files, memories
- **File Format Support** — PDF (PyMuPDF), Word (docx), Code (AST), Images (CLIP)
- **Multiple Backup Strategies** — Qdrant snapshots, Markdown export, Git sync
- **Structured Logging** — JSON logs with request tracing, WebSocket broadcasting, retention
- **PWA Support** — Installable app, push notifications, mobile-responsive

---

## 🚀 Quick Start

### Prerequisites
- **Docker & Docker Compose** (recommended)
- **An LLM provider:** Ollama (local), OpenAI, Anthropic, or Google

### Setup in 3 Steps

**1. Install an LLM Provider**

```bash
# Option A: Ollama (local, free)
brew install ollama
ollama pull qwen2.5-coder:7b
ollama serve

# Option B: Use cloud provider (set API key in .env)
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
```

**2. Clone and Start Services**

```bash
git clone https://github.com/ghively/knowledge-os.git
cd knowledge-os
docker compose up -d --build
```

**3. Access the App**

- **App:** http://localhost:3010 (register/login)
- **API:** http://localhost:8010
- **Qdrant:** http://localhost:6335/dashboard

### First Steps

1. Create account at http://localhost:3010
2. Go to **Agents** → **Create Agent** → pick a template
3. Start chatting with an agent
4. Create notes with `[[wiki links]]`
5. Use semantic search to find content by meaning

---

## 📋 Architecture

```
┌──────────────────────────────────────────────────────┐
│              Knowledge OS v0.3.0                      │
├──────────────────────────────────────────────────────┤
│ Frontend (React 18 + TypeScript + Vite)              │
│ • Pages: Notes, Tasks, Agents, Search, Logs          │
│ • Real-time: WebSocket presence, cursors             │
│ • Auth: JWT with auto token refresh                  │
├──────────────────────────────────────────────────────┤
│ Backend (FastAPI + Python 3.11)                      │
│ • 86 REST endpoints organized in 13 routers          │
│ • Agent Runtime: ReAct loop + Memory + Scheduling    │
│ • Tool Sandboxing: Approval gates + Rate limits      │
│ • Structured JSON logging + WebSocket broadcast      │
├──────────────────────────────────────────────────────┤
│ Data Layer                                           │
│ • SQLite: Users, Sessions, Audit, Schedules, etc.   │
│ • Qdrant: 8 collections (objects, blocks, memories) │
│ • File System: Agent definitions, watched folders   │
└──────────────────────────────────────────────────────┘
```

**Agent Runtime Stack:**
- Identity: AGENT.md, SOUL.md, MEMORY.md, TOOLS.md
- LLM Router: Ollama/OpenAI/Anthropic/Google
- Tool System: Native + CLI agents + MCP servers
- Memory: Semantic retrieval + daily curation
- Audit: Every decision logged (90-day retention)

---

## ⚙️ Agent Configuration

Each agent directory contains 4 markdown files (`backend/agents/{name}/`):

**AGENT.md** — Identity & capabilities
```markdown
# Your Agent Name
You are a specialized assistant for [domain].

## Capabilities
- [capability 1]
- [capability 2]

## Instructions
1. [Instruction 1]
2. [Instruction 2]
```

**SOUL.md** — Personality & behavior
```markdown
## Personality
- [Trait 1]
- [Trait 2]

## Tone
- [Communication style]
```

**TOOLS.md** — LLM & MCP servers
```markdown
## LLM Provider
provider: ollama
model: qwen2.5-coder:7b
temperature: 0.2
max_tokens: 2048

## MCP Servers
- name: brave-search
  command: npx @anthropic/mcp-server-brave-search
```

**MEMORY.md** — Auto-curated long-term memory
```markdown
# Memory Log

## User Preferences
- [Preference 1]

## Learned Context
- [Context 1]
```

### Creating Custom Agents

**UI Method:**
1. **Agents** → **Create Agent** → pick template
2. Edit the 4 markdown files
3. Save and start chatting

**API Method:**
```bash
POST /api/v1/agents/runtime/create-from-template
PUT /api/v1/agents/runtime/{id}/files/AGENT.md
```

### Built-in Agent Templates

| Name | Purpose | Best LLM |
|------|---------|----------|
| **Researcher** | Web research, fact-checking | qwen2.5-coder:7b |
| **Coder** | Code generation, debugging | qwen2.5-coder:7b |
| **Analyst** | Data analysis, reporting | llama3.1:8b |
| **Writer** | Content creation, editing | llama3.1:8b |
| **Personal Assistant** | General tasks, scheduling | qwen2.5-coder:7b |

### Recommended Models

| Model | Provider | Use Case |
|-------|----------|----------|
| `qwen2.5-coder:7b` | Ollama | Tool calling, code, reasoning |
| `deepseek-r1:8b` | Ollama | Deep reasoning, analysis |
| `llama3.1:8b` | Ollama | General-purpose |
| `gpt-4o-mini` | OpenAI | Fast, cheap, capable |
| `claude-sonnet-4-20250514` | Anthropic | Best reasoning |

## 🔒 Security

- **JWT Authentication** — Required on all CRUD endpoints with bcrypt-hashed passwords
- **Rate Limiting** — Per-agent (100k tokens/day), per-user (1000 req/day), per-minute (10 req)
- **Tool Sandboxing** — Restricted filesystem, timeouts, output truncation, approval gates
- **Prompt Injection Defense** — Input sanitization, output validation
- **Tool Approval Flow** — Destructive operations require human confirmation
- **HMAC Webhooks** — Signature verification on incoming webhook events
- **Audit Logging** — Every agent decision logged with 90-day retention
- **Persistent Secrets** — JWT secret survives container restarts

---

## 📚 API & Documentation

**86 REST Endpoints** across 13 routers:
- **Authentication** — Register, login, refresh, logout, password reset
- **Objects & Blocks** — CRUD for notes, tasks, and structured content
- **Agents & Runtime** — Create, configure, and chat with agents
- **Scheduling & Webhooks** — Cron tasks and event triggers
- **Search** — Semantic search with vector embeddings
- **System** — Health checks, logs, settings

**Interactive Docs:**
- Swagger UI: `http://localhost:8010/docs`
- ReDoc: `http://localhost:8010/redoc`

**Full API Reference:**
See [API.md](API.md) for complete endpoint documentation with examples.

**WebSocket Endpoints:**
- `ws://localhost:8010/ws/system` — System updates, logs, events
- `ws://localhost:8010/ws/agents/{name}` — Agent-specific updates

## 🛠️ Development

### Quick Start (Docker)

```bash
docker compose up -d --build        # Start all services
docker compose logs -f backend      # View logs
docker compose down -v              # Stop & clean
```

### Manual Development

```bash
# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload

# Frontend (new terminal)
cd frontend && npm install && npm run dev

# Qdrant (new terminal)
docker run -p 6333:6333 qdrant/qdrant

# Ollama (new terminal)
ollama serve
```

### Testing

```bash
# Run tests
pytest backend/tests/

# Frontend tests
npm test

# With coverage
pytest --cov=app backend/
```

### End-to-End Testing

A comprehensive Playwright suite at [`e2e/`](e2e/) exercises every page,
every read-side API endpoint, and per-page browser-error capture (60
tests across 13 spec files). It is designed to run unattended — by an
agent or CI — against a live stack:

```bash
# With backend + frontend running (defaults: http://localhost:8000 and :5173)
cd e2e
bash scripts/run-suite.sh   # always exits 0
cat REPORT.md               # canonical "what is broken" artifact
```

`e2e/REPORT.md` is regenerated on every run and committed to the repo, so
the latest results are always visible. See [`e2e/README.md`](e2e/README.md)
for the full breakdown.

**See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed setup and contribution guidelines.**

---

## 💻 Tech Stack

| Component | Technology |
|-----------|-----------|
| **Frontend** | React 18, TypeScript, Vite, Tailwind, shadcn/ui |
| **Backend** | FastAPI, Python 3.11+, Pydantic v2 |
| **Vector DB** | Qdrant (384-dim embeddings) |
| **SQL Database** | SQLite with Alembic migrations |
| **LLM** | Ollama, OpenAI, Anthropic, Google |
| **Agent Runtime** | ReAct loop, MCP client, tool sandboxing |
| **Auth** | JWT + bcrypt, slowapi rate limiting |
| **Logging** | structlog JSON with file rotation |
| **Real-time** | WebSocket + Server-Sent Events |
| **PWA** | vite-plugin-pwa, Workbox offline support |

---

## 📖 Documentation

Complete documentation suite (top-level `.md` files):

- **[INSTALLATION.md](INSTALLATION.md)** — Setup guides (Docker, local)
- **[QUICKSTART.md](QUICKSTART.md)** — Five-minute walkthrough
- **[CONFIGURATION.md](CONFIGURATION.md)** — Environment variables
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — System design & component overview
- **[API.md](API.md)** — All 86 endpoints with examples
- **[AGENT_SYSTEM.md](AGENT_SYSTEM.md)** — Agent building guide
- **[AUTH.md](AUTH.md)** — Authentication & token model
- **[DATABASE.md](DATABASE.md)** — Schema reference
- **[DEVELOPMENT.md](DEVELOPMENT.md)** — Contributing & dev workflow
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — Production deployment
- **[SECURITY.md](SECURITY.md)** — Reporting issues & known limitations
- **[CHANGELOG.md](CHANGELOG.md)** — Release history
- **[e2e/REPORT.md](e2e/REPORT.md)** — Latest end-to-end test results (regenerated each run)

**Quick Links:**
- Project Context: [CLAUDE.md](CLAUDE.md)
- License: [MIT](LICENSE)
- Issues: [GitHub Issues](https://github.com/ghively/knowledge-os/issues)

---

## 📝 License

MIT License — See [LICENSE](LICENSE) file

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/description`)
3. Make changes and test thoroughly
4. Commit with clear messages (`git commit -m "feat: description"`)
5. Push to your branch (`git push origin feature/description`)
6. Open a Pull Request

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed contribution guidelines.
