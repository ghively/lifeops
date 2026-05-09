# Knowledge OS - Quick Start Guide

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- OpenClaw Gateway (optional, for agent integration)

## Installation

### 1. Clone/Extract the Project

```bash
tar -xzf knowledge-os.tar.gz
cd knowledge-os
```

### 2. Start Qdrant

```bash
cd qdrant
docker-compose up -d
cd ..
```

Verify Qdrant is running:
```bash
curl http://localhost:6333/healthz
```

### 3. Setup Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your settings
```

### 4. Start Backend

```bash
python -m app.main
```

Backend will be available at `http://localhost:8000`

### 5. Setup Frontend

```bash
cd frontend

# Install dependencies
npm install

# Note: You may need to install tailwindcss-animate
npm install tailwindcss-animate
```

### 6. Start Frontend

```bash
npm run dev
```

Frontend will be available at `http://localhost:5173`

## Configuration

### OpenClaw Integration (Optional)

Edit `backend/.env`:

```env
OPENCLAW_GATEWAY_URL=http://localhost:18789
OPENCLAW_TOKEN=your-token-here
OPENCLAW_ENABLED=true
```

### Add Watched Folders

Via Settings page or API:

```bash
curl -X POST http://localhost:8000/api/v1/settings/watched-folders \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/home/username/Documents",
    "recursive": true,
    "include_patterns": ["*.md", "*.txt", "*.pdf"],
    "exclude_patterns": [".git", "node_modules"]
  }'
```

### Configure Backups

Edit settings in the Settings page:

- **Qdrant Snapshots**: Daily automatic backups
- **Markdown Export**: Weekly export to `~/KnowledgeOS_Export`
- **Git Sync**: Optional push to remote repository

## Usage

### Creating Objects

1. Navigate to a space (Notes, Tasks, etc.)
2. Click "New" or use the outliner
3. Enter title and content
4. Add properties (tags, status, etc.)

### Assigning Tasks to Agents

1. Create a task object
2. Set priority (urgent, high, medium, low)
3. Click "Assign" button
4. Select agent from dropdown
5. Optionally add additional context objects

### Chatting with Agents

1. Go to Agents page
2. Click on an agent
3. Chat panel opens on the right
4. Type messages and send

### Searching

1. Use the search bar in the header
2. Type natural language queries
3. Results appear from all indexed content

### File Management

1. Go to Files page
2. See all indexed files
3. Click to view or open
4. Files are automatically indexed when added to watched folders

## API Examples

> **All `/api/v1/*` endpoints require authentication.** Get a token by
> registering or logging in, then pass it as a `Bearer` header on every
> subsequent call.

### Get an Access Token

```bash
# Register (one-time)
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","username":"you","password":"pass1234","full_name":"You"}'

# Login (any time)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"pass1234"}' | jq -r .access_token)
```

The `$TOKEN` variable below assumes you ran the snippet above.

### Create a Task

```bash
curl -X POST http://localhost:8000/api/v1/objects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "task",
    "title": "Research vector databases",
    "content": "Research vector databases for our project",
    "properties": {
      "status": "todo",
      "priority": "high",
      "tags": ["research", "databases"]
    }
  }'
```

### Assign Task to Agent

```bash
curl -X POST http://localhost:8000/api/v1/tasks/{task_id}/assign \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "{task_id}",
    "agent_name": "researcher",
    "priority": "urgent",
    "include_context": true
  }'
```

### Search

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/search?q=vector%20databases&limit=10"
```

## Troubleshooting

### Backend won't start

- Check Qdrant is running: `curl http://localhost:6333/healthz`
- Check Python version: `python --version` (need 3.11+)
- Check dependencies: `pip list | grep qdrant`

### Frontend won't start

- Check Node.js version: `node --version` (need 18+)
- Clear node_modules: `rm -rf node_modules && npm install`
- Check for port conflicts: `lsof -i :5173`

### OpenClaw not connecting

- Verify gateway URL in `.env`
- Check gateway is running: `curl http://localhost:18789/health`
- Verify token is correct

### Files not indexing

- Check folder path exists
- Verify include/exclude patterns
- Check file size < MAX_FILE_SIZE_MB
- Check file permissions

## Development

### Backend Hot Reload

```bash
cd backend
python -m app.main --reload
```

### Frontend Hot Reload

```bash
cd frontend
npm run dev
```

### Running Tests

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
npm test
```

## Project Structure

```
knowledge-os/
├── backend/              # FastAPI backend
│   ├── app/
│   │   ├── database/     # Qdrant & SQLite clients
│   │   ├── models/       # Pydantic models
│   │   ├── routers/      # API routes
│   │   ├── services/     # Business logic
│   │   └── skills/       # OpenClaw skills
│   ├── requirements.txt
│   └── .env.example
├── frontend/             # React frontend
│   ├── src/
│   │   ├── components/   # UI components
│   │   ├── pages/        # Page components
│   │   ├── stores/       # State management
│   │   └── services/     # API clients
│   ├── package.json
│   └── vite.config.ts
├── qdrant/               # Qdrant Docker setup
│   ├── docker-compose.yml
│   └── config/
├── README.md
├── SPECIFICATION.md      # Full spec
└── QUICKSTART.md         # This file
```

## Next Steps

1. Read the full [SPECIFICATION.md](SPECIFICATION.md)
2. Explore the API at `http://localhost:8000/docs`
3. Customize the UI in `frontend/src`
4. Add custom object types in `backend/app/models/objects.py`
5. Extend OpenClaw skill in `backend/app/skills/knowledge-os/`

## Support

For issues and questions:
- Check the [SPECIFICATION.md](SPECIFICATION.md)
- Review API docs at `http://localhost:8000/docs`
- Check logs in backend terminal
