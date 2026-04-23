# Documentation Index

Complete documentation for Knowledge OS.

## Quick Links

- **[README](../README.md)** - Project overview and quick start
- **[Architecture](../ARCHITECTURE.md)** - System design and components
- **[Installation](../INSTALLATION.md)** - Setup instructions
- **[API Reference](../API.md)** - REST API endpoints
- **[Database Schema](../DATABASE.md)** - SQLite and Qdrant schemas
- **[Agent System](../AGENT_SYSTEM.md)** - Building and using agents
- **[Configuration](../CONFIGURATION.md)** - All configuration options
- **[Development](../DEVELOPMENT.md)** - Development workflow
- **[Deployment](../DEPLOYMENT.md)** - Production deployment
- **[Security](../SECURITY.md)** - Security practices
- **[Changelog](../CHANGELOG.md)** - Version history

## Documentation by Topic

### Getting Started
1. Read [README](../README.md) for overview
2. Follow [Installation](../INSTALLATION.md) to set up locally
3. Check [Quick Start](#quick-start) section below

### Development
1. Clone repo and follow [Installation](../INSTALLATION.md)
2. Read [Development](../DEVELOPMENT.md) for workflow
3. Check [Architecture](../ARCHITECTURE.md) to understand design

### API Integration
1. Review [API Reference](../API.md) for endpoints
2. Check [Authentication](#authentication) section in API.md
3. See examples in [Development](../DEVELOPMENT.md)

### Agent Building
1. Read [Agent System](../AGENT_SYSTEM.md) overview
2. Follow steps to create custom agent
3. Use [API Reference](../API.md) for endpoints

### Production Deployment
1. Review [Deployment](../DEPLOYMENT.md) guide
2. Prepare infrastructure (AWS/Kubernetes/Docker)
3. Configure from [Configuration](../CONFIGURATION.md)
4. Monitor with tools mentioned in Deployment

### Database
1. Review schema in [Database](../DATABASE.md)
2. Run migrations as per [Installation](../INSTALLATION.md)
3. Configure backups in [Deployment](../DEPLOYMENT.md)

### Security
1. Read [Security](../SECURITY.md) guide
2. Enable HTTPS (see [Deployment](../DEPLOYMENT.md))
3. Configure rate limiting (see [Configuration](../CONFIGURATION.md))

## Quick Start

```bash
# 1. Clone
git clone https://github.com/ghively/knowledge-os.git
cd knowledge-os

# 2. Install (see Installation.md for details)
docker-compose up

# 3. Open browser
# http://localhost:5173

# 4. Start using!
# Create notes, chat with agents, search semantically
```

## File Organization

```
/
├─ README.md                 # Project overview
├─ INSTALLATION.md           # Setup guide
├─ ARCHITECTURE.md           # Technical design
├─ API.md                    # API reference
├─ DATABASE.md               # Schema details
├─ AGENT_SYSTEM.md           # Agent guide
├─ CONFIGURATION.md          # Config options
├─ DEVELOPMENT.md            # Dev workflow
├─ DEPLOYMENT.md             # Production
├─ SECURITY.md               # Security guide
├─ CHANGELOG.md              # Version history
├─ QUICKSTART.md             # Quick reference
├─ AUTH.md                   # Auth details
├─ SPECIFICATION.md          # Full spec
├─ ROADMAP.md                # Future plans
├─ CONTRIBUTING.md           # Contribute
└─ docs/
   └─ README.md              # This file
```

## Document Sizes & Details

| Document | Size | Purpose |
|----------|------|---------|
| README.md | ~6KB | Overview + quick start |
| ARCHITECTURE.md | ~15KB | System design + data flow |
| INSTALLATION.md | ~8KB | Setup instructions |
| API.md | ~18KB | Complete API reference |
| DATABASE.md | ~12KB | Schema + examples |
| AGENT_SYSTEM.md | ~14KB | Agent building guide |
| CONFIGURATION.md | ~9KB | All config options |
| DEVELOPMENT.md | ~12KB | Dev workflow |
| DEPLOYMENT.md | ~15KB | Production guide |
| SECURITY.md | ~3KB | Security practices |

## Contributing Documentation

When adding docs:
1. Follow markdown style from existing files
2. Add table of contents for long docs
3. Include code examples
4. Link to related docs
5. Keep current and up-to-date

---

**Last Updated:** April 2026  
**Version:** v0.3.0  
**Status:** Production Ready
