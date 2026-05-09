# Documentation Index

Complete documentation for Knowledge OS. The actual `.md` files live at the
repository root (one level up from this file); links below are relative.

## Quick Links

- **[README](../README.md)** — Project overview and quick start
- **[QUICKSTART](../QUICKSTART.md)** — Five-minute walkthrough
- **[ARCHITECTURE](../ARCHITECTURE.md)** — System design and components
- **[INSTALLATION](../INSTALLATION.md)** — Local & Docker setup
- **[CONFIGURATION](../CONFIGURATION.md)** — All environment variables
- **[API](../API.md)** — REST API reference (86 endpoints)
- **[AUTH](../AUTH.md)** — Authentication, tokens, rate limiting
- **[DATABASE](../DATABASE.md)** — SQLite + Qdrant schemas, migrations
- **[AGENT_SYSTEM](../AGENT_SYSTEM.md)** — Building and using agents
- **[DEVELOPMENT](../DEVELOPMENT.md)** — Development workflow + e2e suite
- **[DEPLOYMENT](../DEPLOYMENT.md)** — Production deployment
- **[SECURITY](../SECURITY.md)** — Security model + known limitations
- **[CHANGELOG](../CHANGELOG.md)** — Version history
- **[ROADMAP](../ROADMAP.md)** — What's planned next
- **[CONTRIBUTING](../CONTRIBUTING.md)** — How to contribute
- **[SPECIFICATION](../SPECIFICATION.md)** — Original product spec
- **[e2e/REPORT](../e2e/REPORT.md)** — Latest e2e test results (regenerated each run)

## Documentation by Topic

### Getting Started
1. [README](../README.md) for the overview.
2. [INSTALLATION](../INSTALLATION.md) or [QUICKSTART](../QUICKSTART.md) to set up locally.
3. The [Quick start](#quick-start) section below for the 30-second `docker-compose up`.

### Development
1. [INSTALLATION](../INSTALLATION.md) to clone and configure.
2. [DEVELOPMENT](../DEVELOPMENT.md) for the workflow (tests, e2e suite, lint).
3. [ARCHITECTURE](../ARCHITECTURE.md) to understand component layout.

### API Integration
1. [API](../API.md) for endpoints.
2. [AUTH](../AUTH.md) for the JWT flow and the `Bearer` header you must attach.
3. Examples in [QUICKSTART](../QUICKSTART.md) and [DEVELOPMENT](../DEVELOPMENT.md).

### Agent Building
1. [AGENT_SYSTEM](../AGENT_SYSTEM.md) for the file layout and ID rules.
2. Use [API](../API.md) `/api/v1/agents/runtime/*` for chat & lifecycle.
3. See `agents/` and `backend/app/services/agent/` for the runtime code.

### Production Deployment
1. [DEPLOYMENT](../DEPLOYMENT.md) for the production walkthrough (auto-migration, hardened images, CI).
2. [CONFIGURATION](../CONFIGURATION.md) for environment variables.
3. [SECURITY](../SECURITY.md) for known limitations to factor into your threat model.

### Database
1. [DATABASE](../DATABASE.md) for the schema reference.
2. The Docker entrypoint runs `alembic upgrade head` automatically; opt out with `KOS_SKIP_MIGRATIONS=1`.
3. Backups: see [DEPLOYMENT](../DEPLOYMENT.md) and [CONFIGURATION](../CONFIGURATION.md).

### Security
1. [SECURITY](../SECURITY.md) — reporting + known limitations (single-tenant model, per-process rate limiter, MCP creation as admin-equivalent).
2. [AUTH](../AUTH.md) for the token model, expiry, and rate-limit keying.
3. [CONFIGURATION](../CONFIGURATION.md) for production-required env vars (`JWT_SECRET_KEY`, `CORS_ORIGINS`).

## Quick Start

```bash
git clone https://github.com/ghively/knowledge-os.git
cd knowledge-os
docker compose up -d
# Wait for migrations (entrypoint runs `alembic upgrade head` automatically),
# then open http://localhost:3010 (or whatever FRONTEND_PORT is set to).
```

## File Organization

```
/
├─ README.md                 # Project overview
├─ QUICKSTART.md             # Five-minute walkthrough
├─ INSTALLATION.md           # Local + Docker setup
├─ ARCHITECTURE.md           # Technical design
├─ API.md                    # API reference (86 endpoints)
├─ AUTH.md                   # Auth, tokens, rate limiting
├─ DATABASE.md               # Schema details
├─ AGENT_SYSTEM.md           # Agent guide
├─ CONFIGURATION.md          # Config options
├─ DEVELOPMENT.md            # Dev workflow + e2e suite
├─ DEPLOYMENT.md             # Production
├─ SECURITY.md               # Reporting + known limitations
├─ CHANGELOG.md              # Version history
├─ ROADMAP.md                # Future plans
├─ CONTRIBUTING.md           # How to contribute
├─ SPECIFICATION.md          # Original product spec
├─ CLAUDE.md                 # Context for the Claude assistant
├─ e2e/
│  ├─ README.md              # E2E suite docs
│  └─ REPORT.md              # Latest e2e results (regenerated each run)
└─ docs/
   └─ README.md              # This file
```

## Document Sizes

| Document | Approx. size |
|---|---|
| ARCHITECTURE.md | ~20 KB |
| SPECIFICATION.md | ~40 KB |
| DEPLOYMENT.md | ~14 KB |
| AGENT_SYSTEM.md | ~14 KB |
| API.md | ~11 KB |
| DATABASE.md | ~11 KB |
| DEVELOPMENT.md | ~11 KB |
| README.md | ~12 KB |
| CONFIGURATION.md | ~9 KB |
| AUTH.md | ~9 KB |
| CHANGELOG.md | ~10 KB |
| INSTALLATION.md | ~8 KB |
| QUICKSTART.md | ~6 KB |
| CONTRIBUTING.md | ~5 KB |
| SECURITY.md | ~4 KB |
| ROADMAP.md | ~3 KB |

## Contributing Documentation

1. Follow markdown style from existing files.
2. Add a table of contents for long docs.
3. Include code examples when introducing new APIs / env vars.
4. Cross-link to related docs (use repo-relative paths, no `docs/` prefix).
5. Add a CHANGELOG entry for any user-facing change.
