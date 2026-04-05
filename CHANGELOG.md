# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **Auth enforcement** — All CRUD routes now require JWT authentication (C1 fix)
- **Rate limiting** — In-memory rate limiter: auth 5/min, write 30/min, read 60/min (C2 fix)
- **Pagination** — Fixed list_objects to use proper Qdrant scroll API instead of fetching 10K records (C3 fix)
- **JWT persistence** — JWT secret persisted to disk, survives container restarts (C4 fix)
- **WebSocket auth** — WebSocket connections require JWT via query param or header

### Fixed
- Build: Excluded test files from TypeScript compilation
- Build: Resolved duplicate `refreshToken` identifier in auth store
- Build: Fixed Axios interceptor type narrowing
- Build: Removed phantom `ypy`/`ypy-websocket` dependencies (never imported)
- Build: Regenerated `package-lock.json` for CRDT dependencies
- Fixed slowapi/Starlette compatibility by using vendor in-memory rate limiter

### Infrastructure
- Added `backend/app/vendor/slowapi_compat.py` — zero-dependency in-memory rate limiter
- Added `backend/app/data/` to `.gitignore` for runtime data
- Added JWT secret file persistence at `data/.jwt_secret`

### Removed
- `slowapi` external dependency (replaced by vendor fallback)

## [0.1.0] - 2026-04-04

### Added
- Initial MVP release with full-stack implementation
- Object-based note system with block-level editing
- Qdrant vector database integration (8 collections)
- OpenClaw agent integration with two-path task routing
- Real-time WebSocket updates
- File watching and semantic indexing
- Docker Compose setup for easy deployment
- Semantic search across all content
- Agent chat panel with persistent history
- Task assignment with intelligent context gathering
- Three backup strategies (snapshots, markdown, git)

## [0.1.0] - 2026-04-04

### Added
- **Frontend**
  - React + TypeScript + Vite application
  - Slate.js-based outliner editor
  - Block types: paragraph, heading, todo, bullet, numbered, quote, code
  - Agent chat panel with WebSocket
  - Task assignment dialog
  - Search interface (semantic and exact)
  - Settings management
  - Responsive sidebar navigation
  - shadcn/ui component library

- **Backend**
  - FastAPI application with async support
  - Qdrant service for vector operations
  - Context builder for agent tasks
  - File processor for PDF, code, images
  - OpenClaw gateway integration
  - WebSocket manager for real-time updates
  - Complete REST API for all operations

- **Infrastructure**
  - Docker Compose configuration
  - Multi-stage Dockerfiles for frontend and backend
  - Nginx reverse proxy configuration
  - File watcher service
  - GitHub Actions CI/CD pipelines
  - Dependabot configuration
  - Issue and PR templates

- **Documentation**
  - Comprehensive README
  - MVP summary document
  - Specification document
  - Contributing guidelines
  - This changelog

### Security
- Added security headers in nginx configuration
- Configured CORS for API endpoints
- Added input validation on all endpoints

[Unreleased]: https://github.com/ghively/knowledge-os/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ghively/knowledge-os/releases/tag/v0.1.0
