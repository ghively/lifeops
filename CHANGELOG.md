# Changelog

All notable changes to Knowledge OS will be documented in this file.

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
