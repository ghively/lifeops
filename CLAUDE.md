# Knowledge OS - Claude Code Context

Session context and project information for Claude Code development.

---

## ⚡ Read this first when the user asks "what's broken" / "what needs fixing"

The end-to-end suite at `e2e/` writes a fresh report to `e2e/REPORT.md`
every time it runs. **Whenever the user asks about e2e results, broken
features, what to fix, or what the most recent run found — read
`e2e/REPORT.md` before answering.** Do not re-run the suite, guess, or
synthesize from memory; the file is the source of truth.

If the user asks you to run the suite yourself, `cd e2e && bash
scripts/run-suite.sh` regenerates the report. The runner assumes the
backend (`http://localhost:8000`) and frontend (`http://localhost:5173`)
are already up; override with `E2E_BACKEND_URL` / `E2E_FRONTEND_URL` if
they're on different ports.

---

## Project Overview

**Knowledge OS** is a production-ready knowledge management system with an integrated AI agent runtime.

**Version:** v0.3.0  
**Status:** ✅ Production Ready  
**Last Updated:** April 2026  
**Repository:** https://github.com/ghively/knowledge-os

---

## Quick Facts

- **Language:** Python (backend), TypeScript (frontend)
- **Framework:** FastAPI + React 18
- **Databases:** SQLite + Qdrant (vector DB)
- **Agents:** ReAct-style with multi-provider LLM support
- **Real-time:** WebSocket for collaboration & events
- **Tests:** 33 backend test files (~320 test functions) + 21 frontend test files + 4 Playwright E2E specs
- **Documentation:** 17 comprehensive guides (~190 KB)
- **API Endpoints:** 86 documented endpoints

---

## Core Systems

### 1. Agent Runtime (4,400 lines across 21 files)
- ReAct execution loop (agent_loop.py)
- Session & memory management
- Tool registry & MCP client
- LLM routing (Ollama, OpenAI, Anthropic, Google)
- Rate limiting & audit logging
- Scheduler & webhooks
- Security sandbox with approval gates

### 2. Knowledge Management
- Object-based notes (Qdrant + SQLite)
- Block-based outliner editor
- Semantic search (384-dim embeddings)
- Real-time collaboration
- File indexing (PDF, Word, Code, Images)

### 3. Data Layer
- **SQLite:** Users, sessions, audit logs, schedules, webhooks
- **Qdrant:** Objects, blocks, files, code, images, memories, relations (8 collections, 384-dim)
- **File System:** Agent definitions, watched folders

### 4. API (86 endpoints)
- `/api/v1/auth/` — Authentication (7 endpoints)
- `/api/v1/agents/` — Agent management (5 endpoints)
- `/api/v1/agents/runtime/` — Agent execution (40+ endpoints; mounted via `agent_chat` router)
- `/api/v1/objects/` — Content management (7 endpoints)
- `/api/v1/blocks/` — Editor blocks (6 endpoints)
- `/api/v1/tasks/` — Task management (6 endpoints)
- `/api/v1/files/` — File indexing (5 endpoints)
- `/api/v1/search/` — Semantic search (3 endpoints)
- `/api/v1/system/` — Logs & status (6 endpoints)
- More: collaboration, relations, settings, webhooks, etc.

---

## Key Files & Locations

### Backend Architecture
```
backend/
├─ app/
│  ├─ main.py                      # FastAPI app entry
│  ├─ config.py                    # Configuration
│  ├─ routers/                     # 10+ API routers
│  ├─ services/
│  │  ├─ agent/                    # Agent runtime (21 files, 4,400 LOC)
│  │  ├─ auth.py                   # Authentication
│  │  ├─ embedding.py              # Embeddings
│  │  ├─ backup.py                 # Snapshots & exports
│  │  └─ ...
│  ├─ middleware/                  # Auth, rate limiting, logging
│  └─ database/
│     ├─ sqlite.py                 # SQLite client
│     └─ qdrant_client.py           # Qdrant client
├─ tests/                          # 23 test files
├─ alembic/                        # Database migrations
└─ requirements.txt                # Dependencies
```

### Frontend Architecture
```
frontend/
├─ src/
│  ├─ pages/                       # 9 pages
│  ├─ components/                  # 24+ components
│  ├─ hooks/                       # 6 custom hooks
│  ├─ stores/                      # 4 Zustand stores (auth, theme, etc)
│  ├─ services/api.ts              # 86 API endpoints
│  └─ lib/                         # Utilities
├─ tests/                          # 13 test files
└─ vite.config.ts                  # Vite config
```

---

## Common Tasks

### Running Locally

```bash
# Terminal 1: Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm install && npm run dev

# Terminal 3: Qdrant (Docker)
docker run -p 6333:6333 qdrant/qdrant

# Terminal 4: Ollama (optional)
ollama serve
```

Then open http://localhost:5173

### Testing

```bash
# Backend
cd backend && pytest -v

# Frontend
cd frontend && npm test

# E2E
cd e2e && npm test
```

### Making API Changes

1. Add endpoint in `routers/{feature}.py`
2. Register in `main.py`
3. Add tests in `tests/test_{feature}.py`
4. Document in [API.md](API.md)
5. Update frontend client in `services/api.ts`

### Adding Agent Features

1. Modify `services/agent/agent_loop.py` (execution)
2. Update tools in `services/agent/tool_registry.py`
3. Add audit logging in `services/agent/audit.py`
4. Test with `tests/test_agent_loop.py`
5. Document in [AGENT_SYSTEM.md](AGENT_SYSTEM.md)

### Database Changes

1. Create migration: `alembic revision --autogenerate -m "description"`
2. Review: `cat alembic/versions/XXXX_description.py`
3. Apply: `alembic upgrade head`
4. Update schema docs in [DATABASE.md](DATABASE.md)

---

## Important Constraints

### Performance
- Max 10 agent iterations per message (prevents infinite loops)
- Max 300 seconds execution time per agent message
- 384-dim vectors (sentence-transformers/all-MiniLM-L6-v2)
- Rotating log handler (10MB max per file, 5 backups)

### Security
- JWT tokens with HMAC-SHA-256 (not bcrypt)
- Per-agent rate limiting: 100k tokens/day, 1000 req/day, 10 req/min
- Tool execution in sandbox (filesystem, network, timeout restrictions)
- All agent decisions audited and logged
- Tool approval required for destructive operations

### Compatibility
- Python 3.11+ (type hints required)
- Node.js 18+ (TypeScript strict mode)
- React 18+ (hooks only)
- FastAPI 0.100+ (async/await)
- Qdrant 1.7+ (384-dim vectors)

---

## Development Standards

### Python
- PEP 8 style (use `black`)
- Type hints on all functions
- Async/await for I/O
- Docstrings for public functions
- Imports: sorted with `isort`

### TypeScript
- Strict mode enabled
- No `any` types
- Proper error handling
- Component composition (no class components)
- Zustand for state management

### Testing
- Unit tests for business logic
- Integration tests for APIs
- E2E tests for user flows
- Minimum 80% coverage for critical paths

---

## Documentation

**All documentation is current and comprehensive:**

| Document | Purpose | Size |
|----------|---------|------|
| [README.md](README.md) | Overview & quick start | 19KB |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design | 20KB |
| [INSTALLATION.md](INSTALLATION.md) | Setup guide | 8KB |
| [API.md](API.md) | API reference | 11KB |
| [DATABASE.md](DATABASE.md) | Schema & migrations | 11KB |
| [AGENT_SYSTEM.md](AGENT_SYSTEM.md) | Agent guide | 14KB |
| [CONFIGURATION.md](CONFIGURATION.md) | Config options | 9KB |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Dev workflow | 11KB |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Production guide | 14KB |

**Quick Start:** README.md → INSTALLATION.md → Start coding!

---

## Recent Changes (April 2026)

✅ Complete documentation rewrite (108 KB)
✅ Full code review (9.3/10 score)
✅ All systems production-ready
✅ Comprehensive API reference (86 endpoints)
✅ Agent system fully functional
✅ Logging system unified (backend + frontend + nginx)
✅ Security audit passed
✅ 289 tests passing

---

## Known Limitations

- Single-instance backend (can add load balancer)
- SQLite (use PostgreSQL for production)
- In-memory WebSocket (add Redis for multiple instances)
- Ollama default (requires API key for production providers)

---

## Next Steps for Contributors

1. **Read:** [DEVELOPMENT.md](DEVELOPMENT.md) for workflow
2. **Setup:** Follow [INSTALLATION.md](INSTALLATION.md)
3. **Understand:** Review [ARCHITECTURE.md](ARCHITECTURE.md)
4. **Code:** Make changes following standards
5. **Test:** Run full test suite
6. **Document:** Update [API.md](API.md) if needed
7. **Push:** Create PR against `main`

---

## Support

- **Issues:** GitHub Issues
- **Discussions:** GitHub Discussions
- **Docs:** See documentation section above
- **Architecture Questions:** See [ARCHITECTURE.md](ARCHITECTURE.md)
- **API Questions:** See [API.md](API.md)

---

**Version:** v0.3.0 | **Status:** Production Ready ✅  
**Last Updated:** April 23, 2026
