# Installation Guide

Complete setup instructions for Knowledge OS.

---

## Quick Start (5 minutes)

### Option 1: Docker Compose (Recommended)

```bash
git clone https://github.com/ghively/knowledge-os.git
cd knowledge-os
docker-compose up
```

Then open http://localhost:5173 and login with demo/demo123.

### Option 2: Local Development

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///knowledge_os.db
python -m uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev

# Qdrant (new terminal)
docker run -p 6333:6333 qdrant/qdrant

# Ollama (optional, new terminal)
ollama run mistral
```

Open http://localhost:5173 → Register account → Start using!

---

## System Requirements

### Minimum
- Python 3.11+
- Node.js 18+
- 4GB RAM
- 2GB disk space
- SQLite (included)

### Recommended
- Python 3.12
- Node.js 20+
- 8GB+ RAM
- 10GB+ SSD
- Qdrant 1.7+
- Docker & Docker Compose

---

## Detailed Setup

### 1. Clone Repository

```bash
git clone https://github.com/ghively/knowledge-os.git
cd knowledge-os
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# (Optional) Install specific versions
npm ci  # Strict dependency versions
```

### 4. Database Setup

#### Qdrant (Vector DB)

**Option A: Docker (Recommended)**
```bash
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -v qdrant_storage:/qdrant/storage \
  qdrant/qdrant:latest
```

**Option B: Local Installation**
```bash
# Download from https://qdrant.tech/documentation/quick-start/
# Or via package managers
brew install qdrant  # macOS
```

**Verify:**
```bash
curl http://localhost:6333/health
# Response: {"status":"ok"}
```

#### SQLite (Relational DB)

Create with first run:
```bash
# SQLite database auto-created at:
./knowledge_os.db
```

Or initialize manually:
```bash
cd backend
sqlite3 knowledge_os.db < sql/schema.sql  # if schema file exists
```

### 5. Environment Configuration

Create `backend/.env`:

```bash
# Database
DATABASE_URL=sqlite:///./knowledge_os.db

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/app.log

# Agents
AGENTS_ROOT=./agents

# LLM Provider (one of: ollama, openai, anthropic, google)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434

# (Optional) OpenAI
# OPENAI_API_KEY=sk-...

# (Optional) Anthropic
# ANTHROPIC_API_KEY=sk-ant-...

# (Optional) Google
# GOOGLE_API_KEY=...

# (Optional) OpenClaw
# OPENCLAW_GATEWAY_URL=http://localhost:18789
# OPENCLAW_TOKEN=...

# Features
SNAPSHOT_INTERVAL_HOURS=24
MARKDOWN_EXPORT_ENABLED=true
GIT_BACKUP_ENABLED=false

# Security
SECRET_KEY=your-secret-key-here-min-32-chars
DEBUG=false
```

### 6. LLM Setup

#### Option A: Ollama (Default, Free, Local)

```bash
# Install from https://ollama.ai

# Run Ollama (starts server on port 11434)
ollama serve

# In another terminal, pull a model
ollama pull mistral  # Fast (7B params)
ollama pull neural-chat  # High quality (13B params)

# Verify
curl http://localhost:11434/api/tags
```

#### Option B: OpenAI

```bash
# Get API key from https://platform.openai.com/api-keys
export OPENAI_API_KEY=sk-...
export LLM_PROVIDER=openai
```

#### Option C: Anthropic

```bash
# Get API key from https://console.anthropic.com
export ANTHROPIC_API_KEY=sk-ant-...
export LLM_PROVIDER=anthropic
```

#### Option D: Google Gemini

```bash
# Get API key from https://makersuite.google.com/app/apikey
export GOOGLE_API_KEY=...
export LLM_PROVIDER=google
```

### 7. Running the Application

#### Terminal 1: Backend

```bash
cd backend
source venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

#### Terminal 2: Frontend

```bash
cd frontend
npm run dev
```

Expected output:
```
  VITE v4.x.x  ready in xxx ms
  ➜  Local:   http://localhost:5173/
```

#### Terminal 3: Qdrant (if not using Docker)

```bash
docker run -p 6333:6333 qdrant/qdrant:latest
```

### 8. Verify Installation

**Backend API:**
```bash
curl http://localhost:8000/health
# Or visit http://localhost:8000/docs
```

**Frontend:**
- Open http://localhost:5173 in browser
- Should see login page

**Qdrant:**
```bash
curl http://localhost:6333/health
```

**LLM Provider:**
```bash
# If using Ollama
curl http://localhost:11434/api/tags

# If using API key, just proceed to app
```

---

## Docker Compose Setup

Use the provided `docker-compose.yml`:

```bash
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Stop
docker-compose down
```

Services started:
- **Frontend** → http://localhost:5173
- **Backend** → http://localhost:8000
- **Qdrant** → http://localhost:6333
- **Postgres** (optional) → localhost:5432

---

## First Run

### 1. Create Admin User

```bash
# Via frontend:
# 1. Go to http://localhost:5173
# 2. Click "Register"
# 3. Enter email and password
# 4. Click "Create Account"
```

Or via CLI (if implemented):
```bash
cd backend
python scripts/create_user.py --email admin@localhost --password admin123 --admin
```

### 2. Verify Everything Works

```bash
# 1. Login to frontend
# 2. Create a note (type in Notes page)
# 3. Search for it (Search page)
# 4. Chat with agent (Agents page)
# 5. View logs (Logs page)
```

### 3. Configure Agents

Agents are auto-loaded from `./agents/` directory. Default agents (researcher, writer) are pre-configured.

To add custom agent:
```bash
mkdir -p agents/my-agent
cd agents/my-agent

cat > AGENT.md << 'EOF'
# My Custom Agent
A helpful agent for...

## Capabilities
- capability1
- capability2
EOF

cat > SOUL.md << 'EOF'
# Personality
You are...
EOF

cat > TOOLS.md << 'EOF'
# Available Tools
You can use...
EOF
```

---

## Troubleshooting

### Port Already in Use

```bash
# Find process on port 8000
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill process or use different port
python -m uvicorn app.main:app --port 8001
```

### Qdrant Connection Error

```bash
# Check if running
curl http://localhost:6333/health

# If not running:
docker run -p 6333:6333 qdrant/qdrant:latest

# Or restart
docker restart qdrant
```

### SQLite Lock Error

```bash
# Another process is using database
# Solution: Use only one backend process
# Or increase timeout:
# DATABASE_URL=sqlite:///./knowledge_os.db?timeout=10
```

### LLM Provider Not Responding

```bash
# Check Ollama
curl http://localhost:11434/api/tags

# Restart if needed
pkill ollama
ollama serve
```

### Dependency Conflict

```bash
# Clear cache and reinstall
rm -rf backend/venv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt --no-cache-dir
```

### Frontend Build Error

```bash
# Clear node_modules
cd frontend
rm -rf node_modules package-lock.json
npm install
npm run dev
```

---

## Upgrading

### Backend

```bash
cd backend
git pull origin main
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Run migrations
cd backend
python -m alembic upgrade head
```

### Frontend

```bash
cd frontend
git pull origin main
npm install
npm run build  # Verify build works
npm run dev    # Development
```

---

## Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for production setup instructions.

---

## Getting Help

- **API Docs:** http://localhost:8000/docs
- **Issues:** GitHub Issues
- **Discussions:** GitHub Discussions
- **Email:** support@knowledge-os.local

---

**Ready to go!** Start creating notes at http://localhost:5173
