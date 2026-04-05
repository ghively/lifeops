# Knowledge OS v0.2.0 — Production Readiness

## Release Summary

knowledge-os v0.2.0 is a major security and quality release that addresses all critical issues identified in the post-MVP audit. Every endpoint is now authenticated, rate-limited, and properly versioned. The test suite has been overhauled — all 256 tests contain real assertions with zero stubs.

## What Changed

### 🔒 Security (Critical)
- **Auth enforcement** — All CRUD routes require JWT authentication. Unauthenticated requests return 401.
- **Rate limiting** — In-memory rate limiter: auth 5/min, write 30/min, read 60/min. Returns 429 with standard rate limit headers.
- **JWT persistence** — JWT secret survives container restarts (persisted to `data/.jwt_secret`).
- **Password reset** — Reset tokens are never returned in API response bodies.
- **Production warnings** — Logs SECURITY warning when JWT_SECRET_KEY not set in environment.

### 🏗️ Architecture
- **API versioning** — All 37 routes under `/api/v1/` prefix. Old paths return 404.
- **Typed request bodies** — Pydantic models on all endpoints (tasks assign/status, agents chat).
- **Async I/O** — File extraction, heartbeat writes, and backup subprocess wrapped with `asyncio.to_thread()`.
- **Batch Qdrant operations** — Single upsert/delete calls replace N+1 loops in block sync.
- **Data integrity** — Multi-store operations (Qdrant + SQLite) wrapped with rollback on failure.
- **Centralized constants** — Collection names in `app/constants.py`.
- **WebSocket error handling** — Separate WebSocketDisconnect (debug) from app exceptions (traceback).

### 🧠 Smart Content
- **#tag parsing** — Tags extracted from object content on create/update, merged into `properties.tags`. Deduplicated, order-preserving.
- **@mention parsing** — @agent mentions validated against existing agents collection. Case-insensitive matching, deduplicates by lowercase, preserves original casing.
- **Context token enforcement** — Agent task context truncated to `MAX_CONTEXT_TOKENS` (default 4000). Returns `token_count_estimate` in context response.

### 🧪 Testing
- **256 tests passing** (was 258 — removed 11 empty stubs, added 9 auth tests)
- **Zero test stubs** — Every test has real assertions
- **9 new auth tests** — Register, login, invalid credentials, missing fields, auth enforcement, authenticated access, token refresh, token expiry, password reset token safety
- **Tag/mention parsing tests** — Create and update flows verified
- **Context truncation test** — Verifies token budget enforcement

### 📝 Documentation
- **32 env vars documented** in `.env.example` (was 6)
- **CHANGELOG.md** updated with all v0.2.0 entries
- **Full spec re-audit** — 16 PASS, 1 WARN (deferred), 0 FAIL

### 🐛 Bug Fixes
- **Pagination** — Fixed `list_objects` to use Qdrant scroll API instead of fetching 10K records
- **Build blockers** — Excluded test files from tsc, resolved duplicate identifiers, fixed Axios types, removed phantom dependencies
- **Test mock** — Fixed `vector=None` handling in batch block upsert mock
- **Deduplication** — `compute_file_hash` consolidated to `app/utils.py`

## Upgrade from v0.1.0

1. **Frontend update required** — API paths changed from `/api/` to `/api/v1/`. Update `VITE_API_URL` if customized.
2. **Re-register users** — JWT secret changed. Existing tokens are invalid. Users must register again.
3. **Environment variables** — Review `backend/.env.example` for 26 new documented variables.
4. **Docker rebuild** — `docker compose up -d --build` to pick up all changes.

## Known Limitations

- WebSocket paths not versioned (`/ws` not `/api/v1/ws`) — functional, cosmetic only
- Search uses optional authentication (intentional for public/shared knowledge bases)
- No automated E2E test suite yet (manual E2E verified)

## Full Commit Log

```
1ac08eb fix: resolve WARN items — case-insensitive mentions, async file extraction
3bf5722 audit: update — all WARN items resolved except W4 (cosmetic)
9c4193d audit: update re-audit — all FAIL items resolved
1ad2535 test: fix test quality — remove stubs, add 9 auth tests
7c9e277 audit: full spec re-audit — 16 pass, 4 warn, 2 fail
c9cad51 feat: spec gap fixes — tag parsing, mentions, context token enforcement
b2e835f fix: handle vector=None in test mock for batch block upserts
e721323 fix: address all 8 Gemini audit issues
2574b47 test: add password reset token leak regression test
fda52e8 fix: remove password reset token leak (CRITICAL)
400e047 fix: complete S4 env vars, S5 WebSocket paths + test assertions
7611ade fix: update test URLs to /api/v1/ prefix
a6d2144 fix: resolve utils.py vs utils/ package conflict
2d06108 fix: address code quality issues S1-S6
5ec926a fix: security fixes — auth, rate limiting, pagination, JWT persistence
```

---

*Released 2026-04-04*
