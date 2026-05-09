# Knowledge OS Roadmap

This document outlines the planned development roadmap for Knowledge OS.

## Version History

### v0.3.0 (Current) ✅ Production-ready

- [x] Object-based note system (Qdrant + SQLite)
- [x] Block-based outliner editor (Slate.js)
- [x] Qdrant vector database integration (8 collections, 384-dim embeddings)
- [x] Multi-provider LLM agents (Ollama, OpenAI, Anthropic, Google)
- [x] Task assignment with priority routing
- [x] Agent chat panel with WebSocket streaming
- [x] File watching and semantic indexing (PDF, Word, Markdown, Code, Images)
- [x] Semantic search across all collections
- [x] Real-time collaborative editing (WebSocket)
- [x] PWA support
- [x] Docker Compose stack
- [x] User authentication (JWT access + refresh, password reset)
- [x] Protected API routes
- [x] Per-user rate limiting
- [x] OpenAPI / Swagger UI at `/docs`
- [x] Alembic migrations (auto-applied on container start)
- [x] Backup & export (Qdrant snapshots, markdown export, optional git sync)
- [x] CI/CD pipeline (GitHub Actions: backend pytest, frontend vitest+tsc+build, Playwright smoke)
- [x] Comprehensive Playwright e2e suite with auto-generated `e2e/REPORT.md`
- [x] Security hardening (agent path-traversal, MCP flag denylist, rate-limit fingerprinting,
      backup filename sanitization, hardened production Docker images)

### v0.2.0 — Production Readiness ✅ (shipped 2026-04)

- [x] User authentication system (JWT)
- [x] Protected API routes
- [x] Session management with refresh tokens
- [x] Password reset flow
- [x] Unit & integration tests (~320 backend test functions, 246 frontend)
- [x] E2E tests with Playwright
- [x] CI/CD test integration
- [x] Pagination on list endpoints
- [x] OpenAPI / Swagger
- [x] Full documentation suite

### v0.1.0 — MVP ✅ (shipped 2026-Q1)

- [x] Object-based notes
- [x] Outliner editor
- [x] Qdrant integration
- [x] Agent runtime with OpenClaw
- [x] Real-time updates

## Upcoming

### v0.4.0 — Multi-Tenancy & Mobile 📱

**Target: 2026-Q3**

#### True multi-tenant isolation
- [ ] `user_id` filtering on every Qdrant query (objects, blocks, files, tasks)
- [ ] Backfill migration for existing single-tenant data
- [ ] Workspace abstraction (multiple users sharing a workspace)
- [ ] Workspace invites and per-workspace permissions

#### Mobile-first
- [ ] Responsive editor for narrow viewports
- [ ] Offline-first sync (service worker queueing writes)
- [ ] Push notifications

#### Import/Export
- [ ] Notion / Obsidian / Roam import
- [ ] Bulk markdown export
- [ ] JSON API export

### v0.5.0 — AI Enhancements 🤖

**Target: 2026-Q4**

- [ ] Auto-tagging suggestions
- [ ] Content summarization
- [ ] Smart linking
- [ ] Multi-agent orchestration (one agent calls another)
- [ ] Agent workflows / scheduled chains
- [ ] Agent marketplace / shareable agent definitions

### v1.0.0 — Stable Release 🎉

**Target: 2027-Q1**

- [ ] Stable, versioned API contract
- [ ] Plugin system (custom block types, custom tools, custom themes)
- [ ] Advanced permission model (roles, scoped capabilities)
- [ ] Distributed rate limiter (Redis-backed)
- [ ] Performance benchmarks & published SLOs
- [ ] Third-party security audit

## Future Ideas

### Plugins & Extensions
- Custom block types
- Third-party integrations
- Custom themes
- Workflow automation

### Enterprise
- SSO / SAML
- Advanced analytics
- Compliance reporting (SOC 2, ISO 27001)
- On-premise deployment kits

### Advanced AI
- Knowledge graph visualization
- Semantic clustering
- Automated insights
- Natural language queries against structured data

## Contributing

1. Open an issue with your feature request.
2. Join discussions on existing issues.
3. Submit PRs for roadmap items.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.
