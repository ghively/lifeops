# Changelog

All notable changes to Knowledge OS will be documented in this file.

## [Unreleased]

### Security & Hardening (2026-05-09)

- **Agent ID path traversal (CRITICAL)** — `backend/app/services/agent/identity.py`
  now validates `agent_id` against a strict regex and resolves the path back
  inside `agents_root` before any filesystem operation. Same treatment for
  filenames passed to `get_file`/`update_file`. Previously a request like
  `GET /api/v1/agents/runtime/../escape/files/AGENT.md` would walk outside
  the sandbox; it's now a clean 400.
- **MCP server registration** (`backend/app/routers/agent_chat.py`) now
  rejects dangerous interpreter flags (`-c`, `-e`, `-m`, `--eval`, deno's
  `--allow-*`, etc.) in addition to shell metacharacters. Whitelisted
  binaries plus a flag denylist closes the "registered MCP server runs
  arbitrary code" path.
- **Rate-limit fallback** (`backend/app/middleware/rate_limit.py`) — bad/
  expired tokens are bound to a `(ip, token-fingerprint)` bucket instead of
  silently downgrading to per-IP. Stops attackers from rotating IPs while
  reusing malformed tokens to dodge per-user caps.
- **Agent loop token budget** (`backend/app/services/agent/agent_loop.py`)
  is now checked at the top of each iteration. The loop yields a structured
  `error`+`done` event pair instead of raising `RuntimeError` into the
  streaming caller; same treatment for max-iterations.
- **Backup export filenames** (`backend/app/services/backup.py`) sanitize
  Qdrant point IDs through `os.path.basename` and refuse paths that escape
  the collection directory.
- **Object audit trail** (`backend/app/routers/objects.py`) — newly created
  objects auto-populate `properties.created_by` from the authenticated user.
- **Validation error mapping** (`backend/app/main.py`) — `ValueError`s from
  validators now surface as 400 instead of leaking as 500.

### Infra & Operations (2026-05-09)

- **Auto-migration on container start** — `backend/entrypoint.sh` now runs
  `alembic upgrade head` before the application starts. Set
  `KOS_SKIP_MIGRATIONS=1` to opt out (e.g. when running migrations in a
  separate job or against a DB that's already at head).
- **LLM provider SDKs pinned** — `openai==1.59.6`, `anthropic==0.42.0`,
  `google-generativeai==0.8.3` are now declared in `backend/requirements.txt`.
  They were already imported dynamically by `agent/llm_router.py`; pinning
  them makes the dependency explicit and reproducible.
- **Frontend production image hardened** — `frontend/Dockerfile.prod` now
  drops to the non-root `nginx` user with proper ownership of html/cache/
  log/pid (matching `frontend/Dockerfile`).
- **GitHub Actions CI re-added** — `.github/workflows/ci.yml` runs backend
  pytest, frontend tsc + vitest + build, and an optional Playwright smoke
  job on push and PR.

### Testing

- **Comprehensive Playwright e2e suite** lives at `e2e/`. 60 tests across
  13 spec files cover every page (auth, navigation, outliner, tasks, files,
  search, agents, agent-chat, settings, logs), every read-side API
  endpoint, and per-page console-error capture. Run with
  `cd e2e && bash scripts/run-suite.sh`; the suite always exits 0 and
  writes `e2e/REPORT.md` as the canonical "what's broken" artifact. The
  four loose top-level specs (`smoke.spec.ts`, `objects.spec.ts`, etc.)
  were replaced.
- 10 new test cases in `backend/tests/test_agent_identity.py` lock down
  the path-traversal fixes.

### Fixed
- **Security / correctness**: JWT refresh/reset tokens were bcrypt-hashed, but JWTs exceed bcrypt's 72-byte input limit, so two tokens issued in the same second would collide on verify — a refresh token could be accepted when a different one was expected. Tokens are now HMAC-SHA-256 hashed (no truncation); passwords continue to use bcrypt. Legacy bcrypt-hashed tokens are verified via a fallback path for graceful rollover.
- `app.middleware.auth.get_optional_user` had a malformed `Annotated[...] | None` signature that caused FastAPI to occasionally parse `HTTPAuthorizationCredentials` as a request body — POST routes using `get_optional_user` (e.g. `POST /api/v1/system/logs`) would return `422` instead of reading JSON. Union moved inside `Annotated`.
- `POST /api/v1/auth/password-reset` previously leaked the raw reset token in the response when running with `DEBUG=true`; removed, so the endpoint can never be abused for privilege escalation regardless of environment.
- `POST /api/v1/system/logs` now reads the body directly rather than relying on FastAPI's automatic body parsing (which collided with the rate-limit decorator's `**kwargs` wrapping).
- `app.routers.system._parse_nginx_line` now returns `None` for lines with malformed timestamps instead of silently keeping the raw string.
- `app.services.auth.revoke_all_refresh_tokens` used `sqlite_manager.connection.execute(...)` directly (which breaks when the manager is mocked) — now uses the thread-safe `sqlite_manager.execute(...)`.
- `app.config.AGENTS_ROOT` was imported by the smoke-test but never defined; added.
- System smoke-test overall status now treats `warn` (optional subsystems unreachable, e.g. Ollama not installed) as acceptable.

### Added
- **Alembic schema migrations** (`backend/alembic/`) — canonical baseline captures the current SQLite schema; future schema changes go through versioned migrations (`alembic revision`, `alembic upgrade head`). Idempotent: safe to stamp or upgrade on an existing DB.
- **CI: Playwright E2E job** — `.github/workflows/ci.yml` now spins up a Qdrant service, the backend, and the Vite dev server, then runs the chromium Playwright suite. Reports and service logs are uploaded as artifacts.
- **OpenAPI**: `docs_url=/docs`, `redoc_url=/redoc`, `openapi_url=/api/v1/openapi.json` with contact + license metadata. OpenAPI JSON is whitelisted from auth.
- **WebSocket versioning**: `/api/v1/ws`, `/api/v1/ws/system`, `/api/v1/ws/agents/{agent_name}` are the canonical paths. Frontend (`wsUrl`, `AgentChatPanel`, `LogsPage`, `websocketApi.getUrl`) all updated. Unversioned `/ws*` aliases retained for backwards compatibility.

### Changed
- **Sidebar "Today"/"Inbox" badges** (`frontend/src/components/layout/Sidebar.tsx`) previously showed a static placeholder (`quickLinks.length`, hardcoded `3`). They now reflect real data: `Today` = tasks with a due date ≤ end of today and status ≠ `done`; `Inbox` = tasks in `todo` status with no due date. Badges hidden when zero.
- Access tokens now include a `jti` claim so two tokens issued within the same second are distinct.

## [0.3.0] - 2026-04-05

### Security & Stability Audit (2026-04-05 21:30 CDT)
- Full system audit: 7 parallel agents covering frontend, backend, agent runtime, databases, auth, websocket, pages
- **196 issues found**: 16 critical, 100 high, ~72 low
- Tracked in `memory/bug-tracker.md` — all items marked ⬜ pending fix
- Top criticals: WebSocket auth missing, path traversal, command injection via MCP, token leaks, container root

### Added

#### Agent Runtime System
- **Agent identity system** — Markdown-first agent definitions (AGENT.md, SOUL.md, MEMORY.md, TOOLS.md)
- **LLM router** — Multi-provider support (Ollama, OpenAI, Anthropic, Google) with streaming and fallback
- **CLI agent delegation** — Delegate to Codex, Claude Code, Kimi CLI, Gemini CLI, OpenCode as tools
- **ReAct agent loop** — Think → tool → observe → loop with parallel tool execution
- **MCP client** — Connect to external tool servers via stdio and HTTP transports
- **Memory manager** — Daily logs, Qdrant semantic retrieval, MEMORY.md auto-curation
- **Session manager** — SQLite-backed conversation persistence with title generation
- **SSE streaming** — Real-time streaming with tool call indicators
- **Sub-agent spawning** — Parallel sub-agent execution with depth limits
- **Agent templates** — Pre-built configs: Researcher, Coder, Analyst, Writer, Personal Assistant
- **Scheduled tasks** — Autonomous background execution with cron scheduling
- **Webhook triggers** — External events trigger agent actions with HMAC verification
- **Tool approval flow** — Destructive operations require human confirmation via WebSocket
- **Rate limiting** — Per-agent token budgets and request limits with 429 responses
- **Tool sandboxing** — Filesystem restrictions, timeouts, output truncation
- **Prompt injection defense** — Input/output sanitization
- **Audit logging** — Comprehensive decision logging with 90-day retention

#### Frontend
- **Agent chat page** — Full chat interface with SSE streaming and tool indicators
- **Agent management page** — 7-tab management (agents, files, MCP, schedule, webhooks, templates, audit)
- **Markdown file editor** — Tabbed editor with preview for agent identity files
- **CLI agent status** — Availability indicators for installed CLI tools
- **Approval dialog** — Tool approval flow with countdown timer
- **Usage dashboard** — Token usage stats and audit log viewer

#### Other
- **PWA support** — Installable, push notifications, responsive mobile UI
- **Slash command autocomplete** — Floating menu with filtering and keyboard navigation
- **Structured logging system** — structlog JSON, request tracing, rotating files
- **Log viewer UI** — Filters, auto-refresh, WebSocket streaming, JSON export
- **System status endpoint** — Version, uptime, request/error counts

### Changed
- **Default LLM provider** — Changed from OpenAI to Ollama (qwen2.5-coder:7b)
- **Dependency versions** — Unpinned pydantic, numpy, httpx, qdrant-client for compatibility
- **Frontend auth** — Added mutex lock on token refresh to prevent redirect storms

### Fixed
- **Circular import** — Lazy import of sandbox module in websocket_manager
- **SSE parsing** — Multiline JSON payloads no longer break stream parsing
- **Parallel tool execution** — return_exceptions=True prevents loop crashes
- **Parallel tool UI state** — Track tool calls by ID instead of single string
- **Database migration** — Added missing columns (name, metadata, messages_count)
- **Tool registry** — Generic exception trap prevents unhandled errors
- **Approval dialog** — Interval cleanup before unmount prevents race condition
- **Rate limit response** — 429 returns retry_after_seconds in JSON body
- **New Session button** — No longer auto-selects first session
- **Webhook receiver** — Catches JSONDecodeError for invalid payloads

### Infrastructure
- 22 new backend modules in `backend/app/services/agent/`
- 6 new API routers
- 14 new test files
- 289 tests passing (up from 256)
- 6,111 lines added across 46 files
- 3-round Gemini audit — all issues resolved

## [0.2.0] - 2026-04-04

### Added
- **Full spec compliance** — 70/70 requirements verified
- **Auth system** — JWT authentication with registration, login, refresh, password reset
- **Rate limiting** — Per-endpoint limits (5/30/60 per minute)
- **Pagination** — All list endpoints support limit/offset
- **API versioning** — /api/v1/ prefix on all endpoints
- **Structured request IDs** — X-Request-ID header on all responses
- **Security hardening** — Auth middleware, input validation, error sanitization

### Fixed
- **C1:** Auth middleware applied to all endpoints
- **C2:** Rate limiting on auth endpoints (429 on 5th request)
- **C3:** Pagination working with limit parameter
- **C4:** JWT secret persisted to disk across restarts

## [0.1.0] - 2026-04-04

### Added
- Initial release
- Object-based knowledge management
- Block-based outliner editor
- Semantic search via Qdrant
- File watching and indexing
- WebSocket real-time updates
- Agent definitions and chat panel
- OpenClaw integration
- Backup strategies (snapshots, markdown, git)
