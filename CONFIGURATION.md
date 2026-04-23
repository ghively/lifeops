# Configuration Guide

All configuration options for Knowledge OS backend and frontend.

---

## Backend Configuration

Configuration via environment variables in `.env` file.

### Database

**DATABASE_URL** (Required)
```bash
# SQLite (development/small deployments)
DATABASE_URL=sqlite:///./knowledge_os.db

# PostgreSQL (production)
DATABASE_URL=postgresql://user:password@localhost:5432/knowledge_os
DATABASE_URL=postgresql://user:password@localhost:5432/knowledge_os?sslmode=require
```

### Logging

**LOG_LEVEL**
```bash
DEBUG      # Verbose, includes all messages
INFO       # Standard (default)
WARNING    # Only warnings and errors
ERROR      # Only errors
CRITICAL   # Only critical errors
```

**LOG_FILE**
```bash
# Default: ./logs/app.log
LOG_FILE=./logs/app.log

# Rotating handler: max 10MB, 5 backups
# Auto-archived to logs/app.log.1, .2, etc.
```

### Agent System

**AGENTS_ROOT** (Required)
```bash
# Path to agents directory
AGENTS_ROOT=./agents
```

**LLM_PROVIDER**
```bash
# Available: ollama, openai, anthropic, google
LLM_PROVIDER=ollama  # Default
```

**OLLAMA_BASE_URL**
```bash
# Ollama server endpoint
OLLAMA_BASE_URL=http://localhost:11434
```

**OPENAI_API_KEY**
```bash
# OpenAI API key (if using OpenAI)
OPENAI_API_KEY=sk-...
```

**ANTHROPIC_API_KEY**
```bash
# Anthropic API key (if using Claude)
ANTHROPIC_API_KEY=sk-ant-...
```

**GOOGLE_API_KEY**
```bash
# Google API key (if using Gemini)
GOOGLE_API_KEY=...
```

### Agent Limits

**DAILY_TOKEN_LIMIT**
```bash
# Tokens per agent per day (default: 100000)
DAILY_TOKEN_LIMIT=100000
```

**DAILY_REQUEST_LIMIT**
```bash
# Requests per agent per day (default: 1000)
DAILY_REQUEST_LIMIT=1000
```

**MINUTE_REQUEST_LIMIT**
```bash
# Requests per agent per minute (default: 10)
MINUTE_REQUEST_LIMIT=10
```

**MAX_EXECUTION_TIME**
```bash
# Max seconds per agent execution (default: 300)
MAX_EXECUTION_TIME=300
```

### Backup & Export

**SNAPSHOT_INTERVAL_HOURS**
```bash
# Qdrant snapshot frequency (default: 24)
SNAPSHOT_INTERVAL_HOURS=24

# Set to 0 to disable
SNAPSHOT_INTERVAL_HOURS=0
```

**MARKDOWN_EXPORT_ENABLED**
```bash
# Enable markdown export (default: true)
MARKDOWN_EXPORT_ENABLED=true
```

**GIT_BACKUP_ENABLED**
```bash
# Enable git sync (default: false)
GIT_BACKUP_ENABLED=false
```

**GIT_BACKUP_REPO**
```bash
# Git repository for backups (if enabled)
GIT_BACKUP_REPO=https://github.com/user/backup
```

### OpenClaw Integration

**OPENCLAW_GATEWAY_URL**
```bash
# OpenClaw gateway endpoint (optional)
OPENCLAW_GATEWAY_URL=http://localhost:18789
```

**OPENCLAW_TOKEN**
```bash
# OpenClaw authentication token (if required)
OPENCLAW_TOKEN=...
```

### Security

**SECRET_KEY** (Required for production)
```bash
# Minimum 32 characters for JWT signing
# Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
SECRET_KEY=your-secret-key-min-32-chars
```

**DEBUG**
```bash
# Development/debugging mode
DEBUG=false  # Default - always false in production

# Never set to true in production!
```

**ALLOWED_ORIGINS** (For CORS)
```bash
# Comma-separated origins allowed
ALLOWED_ORIGINS=http://localhost:5173,https://example.com
```

### Email (Optional)

**SMTP_HOST**
```bash
SMTP_HOST=smtp.gmail.com
```

**SMTP_PORT**
```bash
SMTP_PORT=587
```

**SMTP_USERNAME**
```bash
SMTP_USERNAME=your-email@gmail.com
```

**SMTP_PASSWORD**
```bash
SMTP_PASSWORD=your-app-password
```

**SMTP_FROM**
```bash
SMTP_FROM=noreply@knowledge-os.local
```

### Example .env File

```bash
# Database
DATABASE_URL=sqlite:///./knowledge_os.db

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/app.log

# Agents
AGENTS_ROOT=./agents
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434

# Agent Limits
DAILY_TOKEN_LIMIT=100000
DAILY_REQUEST_LIMIT=1000
MINUTE_REQUEST_LIMIT=10

# Backup
SNAPSHOT_INTERVAL_HOURS=24
MARKDOWN_EXPORT_ENABLED=true
GIT_BACKUP_ENABLED=false

# Security
SECRET_KEY=your-secret-key-here-min-32-chars
DEBUG=false
```

---

## Frontend Configuration

Configuration via environment variables in `.env.local` file.

### API Configuration

**VITE_API_URL** (Required)
```bash
# Backend API base URL
VITE_API_URL=http://localhost:8000
# In production:
VITE_API_URL=https://api.example.com
```

### Feature Flags

**VITE_ENABLE_AGENTS**
```bash
# Enable agent features (default: true)
VITE_ENABLE_AGENTS=true
```

**VITE_ENABLE_COLLABORATION**
```bash
# Enable real-time collaboration (default: true)
VITE_ENABLE_COLLABORATION=true
```

**VITE_ENABLE_SEARCH**
```bash
# Enable semantic search (default: true)
VITE_ENABLE_SEARCH=true
```

**VITE_ENABLE_FILE_UPLOAD**
```bash
# Enable file uploads (default: true)
VITE_ENABLE_FILE_UPLOAD=true
```

### UI Configuration

**VITE_THEME**
```bash
# Theme: light, dark, auto (default: auto)
VITE_THEME=auto
```

**VITE_MAX_BLOCK_DEPTH**
```bash
# Maximum nesting level for blocks (default: 10)
VITE_MAX_BLOCK_DEPTH=10
```

**VITE_PAGE_SIZE**
```bash
# Default page size for lists (default: 50)
VITE_PAGE_SIZE=50
```

### Analytics (Optional)

**VITE_ANALYTICS_ID**
```bash
# Google Analytics ID
VITE_ANALYTICS_ID=G-XXXXXXXXXX
```

### Example .env.local File

```bash
# API
VITE_API_URL=http://localhost:8000

# Features
VITE_ENABLE_AGENTS=true
VITE_ENABLE_COLLABORATION=true
VITE_ENABLE_SEARCH=true

# UI
VITE_THEME=auto
VITE_MAX_BLOCK_DEPTH=10
```

---

## Docker Compose Configuration

Environment variables for docker-compose.yml:

```yaml
services:
  backend:
    environment:
      - DATABASE_URL=postgresql://knowledge:password@postgres:5432/knowledge_os
      - LOG_LEVEL=INFO
      - AGENTS_ROOT=/app/agents
      - LLM_PROVIDER=ollama
      - SECRET_KEY=your-secret-key-here
      - DEBUG=false

  frontend:
    environment:
      - VITE_API_URL=http://backend:8000

  postgres:
    environment:
      - POSTGRES_DB=knowledge_os
      - POSTGRES_USER=knowledge
      - POSTGRES_PASSWORD=password

  qdrant:
    # No environment variables needed
    ports:
      - "6333:6333"

  ollama:
    # Models loaded at runtime
    ports:
      - "11434:11434"
```

---

## Production Configuration

Recommended settings for production deployment:

```bash
# Database: Use PostgreSQL
DATABASE_URL=postgresql://user:pass@host:5432/knowledge_os?sslmode=require

# Logging: Higher level
LOG_LEVEL=WARNING

# LLM: Use API-based provider
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Security
DEBUG=false
SECRET_KEY=<strong-random-32-chars>
ALLOWED_ORIGINS=https://example.com,https://www.example.com

# Backup: Enable
SNAPSHOT_INTERVAL_HOURS=12
MARKDOWN_EXPORT_ENABLED=true
GIT_BACKUP_ENABLED=true
GIT_BACKUP_REPO=https://github.com/user/backup

# Agent Limits: Adjust for your usage
DAILY_TOKEN_LIMIT=50000
DAILY_REQUEST_LIMIT=500
```

---

## Advanced Configuration

### Database Connection Pooling

For PostgreSQL with multiple workers:

```bash
# Set connection pool size (default: 5)
DATABASE_URL=postgresql://...?pool_size=10
```

### Qdrant Configuration

Custom Qdrant settings in `qdrant/config.yaml`:

```yaml
storage:
  snapshots_path: ./snapshots

service:
  api_key: optional-api-key
  max_request_size_mb: 200
```

### Rate Limiting Customization

Modify in `backend/app/middleware/rate_limit.py`:

```python
RATE_LIMITS = {
    "default": "100/hour",
    "agent_chat": "10/minute",
    "search": "30/minute"
}
```

---

## Configuration Validation

Verify configuration on startup:

```bash
# Backend logs on startup:
INFO: Database: sqlite://./knowledge_os.db
INFO: LLM Provider: ollama (http://localhost:11434)
INFO: Log Level: INFO
INFO: Agents Root: ./agents

# If configuration is invalid:
ERROR: SECRET_KEY must be at least 32 characters
```

---

## Troubleshooting Configuration

### Port Already in Use

```bash
# Change port
uvicorn app.main:app --port 8001

# Or in docker-compose.yml
ports:
  - "8001:8000"
```

### Database Connection Failed

```bash
# Check connection string
DATABASE_URL=postgresql://user:password@host:5432/db

# Common issues:
# - Wrong password
# - Host not reachable
# - Database not created
# - SSL mode mismatch
```

### LLM Provider Not Found

```bash
# Verify provider is running
curl http://localhost:11434/api/tags  # Ollama
curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Memory Issues

If running out of memory:

```bash
# Reduce Qdrant batch size
# Reduce page sizes
# Limit concurrent sessions
```

---

## Environment-Specific Files

Use multiple .env files:

```bash
# Development
.env.development
VITE_API_URL=http://localhost:8000
DEBUG=true

# Staging
.env.staging
VITE_API_URL=https://api-staging.example.com
DEBUG=false

# Production
.env.production
VITE_API_URL=https://api.example.com
DEBUG=false
```

Load with:
```bash
export $(cat .env.production | xargs)
python -m uvicorn app.main:app
```

---

**See also:**
- [INSTALLATION.md](INSTALLATION.md) - Setup instructions
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment
- [Architecture](ARCHITECTURE.md) - Technical details
