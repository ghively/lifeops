# Knowledge OS

[![Tests](https://img.shields.io/badge/tests-256%20passing-brightgreen)](https://github.com/ghively/knowledge-os)
[![Version](https://img.shields.io/badge/version-v0.2.0-blue)](https://github.com/ghively/knowledge-os)

A **Capacities/Anytype-inspired knowledge management system** with **OpenClaw agent integration**. Built on **Qdrant** for semantic search and vector storage.

## Features

### Core Knowledge Management
- **Object-based notes** - Everything is an object (page, task, person, book, meeting, agent, file, folder, image, code)
- **Block-based outliner editor** - Logseq/Roam-style with unlimited nesting depth
- **Block references & backlinks** - Link between any blocks, not just pages
- **Semantic search** - Find content by meaning, not just keywords
- **Real-time updates** - WebSocket-powered live collaboration

### Smart Content
- **#tag parsing** - Tags are extracted from content and stored in `properties.tags`
- **@mention parsing** - `@agent` mentions are validated against the agents collection, case-insensitive, and stored in `properties.mentions`
- **Context token enforcement** - Agent task context is truncated to `MAX_CONTEXT_TOKENS` (default `4000`)

### AI Agent Integration
- **OpenClaw integration** - Direct API connection to your agent system
- **Task assignment** - Assign tasks to agents with intelligent context gathering
- **Two-path routing**:
  - **Direct API**: urgent/high/medium priority tasks
  - **HEARTBEAT.md**: low priority tasks for batch processing
- **Agent chat panel** - Real-time conversation with agents
- **Agent memory** - Persistent context across sessions

### File Management
- **File watching** - Auto-index files from watched folders
- **Multi-format support** - PDF, markdown, code, images
- **Semantic file search** - Find files by content meaning
- **Metadata extraction** - Automatic content type detection

### Backup & Export
- **Qdrant snapshots** - Daily automatic vector database backups
- **Markdown export** - Weekly export to markdown files
- **Git sync** - Version control integration

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│    Backend      │────▶│     Qdrant      │
│  (React/Vite)   │     │   (FastAPI)     │     │  (Vector DB)    │
│   Port: 3010    │◄────│   Port: 8010    │◄────│   Port: 6335    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │  File Watcher   │
                        │  (Optional)     │
                        └─────────────────┘
```

### Qdrant Collections
1. `objects` - Main objects (pages, tasks, people, etc.)
2. `blocks` - Block-level content for outliner
3. `relations` - Object relationships and backlinks
4. `files` - File metadata and content
5. `images` - Image embeddings (CLIP)
6. `code` - Code file embeddings
7. `agent_memories` - Agent conversation history
8. `chat_logs` - User-agent chat sessions

## Quick Start

### Prerequisites
- Docker & Docker Compose
- (Optional) OpenClaw gateway running

### 1. Clone and Configure

```bash
git clone https://github.com/ghively/knowledge-os.git
cd knowledge-os

# Copy environment template
cp .env.example .env

# Edit .env with your settings
vim .env
```

### 2. Start Services

```bash
# Start all services
cp .env.example .env
docker-compose up --build -d

# Or with file watcher
docker-compose --profile with-watcher up --build -d
```

### 3. Access the Application

- **Frontend**: http://localhost:3010
- **Backend API**: http://localhost:8010
- **Qdrant Dashboard**: http://localhost:6335/dashboard

## Configuration

### Environment Variables

Create a `.env` file:

```env
FRONTEND_PORT=3010
BACKEND_PORT=8010
QDRANT_HTTP_PORT=6335
QDRANT_GRPC_PORT=6336
OPENCLAW_URL=http://host.docker.internal:18789
OPENCLAW_TOKEN=
```

### Watched Folders

Add folders to watch via Settings → Watched Folders:
- `~/Documents` - Your documents
- `~/Projects` - Code projects
- Any other path accessible to Docker

## Security

- **JWT authentication** - Required on all CRUD endpoints; search endpoints can be accessed without JWT when configured to allow optional auth
- **Rate limiting** - Auth endpoints: `5/min`, write endpoints: `30/min`, read endpoints: `60/min`
- **Password reset safety** - Password reset tokens are never returned in API responses
- **Persistent JWT secret** - The JWT signing secret persists across container restarts
- **Rate limit headers** - Responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`

## Usage

### Creating Notes
1. Click "New Page" or use `/` command
2. Use the outliner editor with `/` for block types
3. Reference blocks with `((block-id))`
4. Link objects with `[[object-title]]`

### Assigning Tasks to Agents
1. Create a task object
2. Click "Assign to Agent"
3. Select agent and priority
4. Add context objects if needed
5. Submit

### Chatting with Agents
1. Click an agent in the sidebar
2. Or go to Agents page and click chat
3. Type messages and get real-time responses

### Searching
1. Use the search bar (Ctrl+K)
2. Choose semantic or exact search
3. Results ranked by relevance

### API Endpoints

> **JWT authentication is required on all CRUD endpoints.** Register/login to obtain a token, then include it as `Authorization: Bearer <token>`. Search endpoints support optional authentication.

#### Authentication
- `POST /api/v1/auth/register` - Create account (username, email, password, display_name)
- `POST /api/v1/auth/login` - Login (email, password) → returns access_token + refresh_token
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/logout` - Logout (invalidate refresh token)
- `POST /api/v1/auth/forgot-password` - Request password reset
- `POST /api/v1/auth/reset-password` - Reset password with token

#### Objects (requires auth)
- `GET /api/v1/objects?limit=10&offset=0` - List objects (paginated)
- `POST /api/v1/objects` - Create object
- `GET /api/v1/objects/{id}` - Get object
- `PUT /api/v1/objects/{id}` - Update object
- `DELETE /api/v1/objects/{id}` - Delete object

### Blocks
- `GET /api/v1/blocks/object/{object_id}` - Get blocks for object
- `POST /api/v1/blocks` - Create block
- `PUT /api/v1/blocks/{id}` - Update block
- `POST /api/v1/blocks/batch-update` - Batch update blocks

### Tasks (requires auth)
- `GET /api/v1/tasks` - List tasks
- `POST /api/v1/tasks/{id}/assign` - Assign to agent
- `POST /api/v1/tasks/{id}/status` - Update status

### Agents (requires auth)
- `GET /api/v1/agents` - List agents
- `POST /api/v1/agents/{name}/chat` - Send message
- `GET /api/v1/agents/{name}/chat` - Get chat history

### Search (optional auth)
- `GET /api/v1/search?q={query}` - Semantic search
- `GET /api/v1/search/similar/{id}` - Find similar

### Files (requires auth)
- `GET /api/v1/files` - List files
- `POST /api/v1/files/{id}/reindex` - Reindex file

### Settings (requires auth)
- `GET /api/v1/settings` - Get settings
- `PUT /api/v1/settings` - Update settings
- `GET /api/v1/settings/watched-folders` - List watched folders
- `POST /api/v1/settings/watched-folders` - Add folder
- `DELETE /api/v1/settings/watched-folders/{id}` - Remove folder
- `POST /api/v1/settings/backup` - Trigger backup/export

### WebSockets
- `ws://localhost:8010/ws/system` - System updates
- `ws://localhost:8010/ws/agents/{name}` - Agent-specific updates

## Development

### Docker Compose Workflow

```bash
cp .env.example .env
docker-compose up --build
```

### Common Commands

```bash
docker-compose up --build -d
docker-compose down
docker-compose logs -f backend
docker-compose logs -f frontend
```

### With File Watcher

```bash
docker-compose --profile with-watcher up --build
```

### Frontend Development

```bash
cd frontend
npm install
VITE_API_URL=http://127.0.0.1:8010 npm run dev
```

## Backup & Recovery

### Create Snapshot
```bash
curl -X POST http://localhost:6335/snapshots
```

### Restore from Snapshot
```bash
curl -X POST http://localhost:6335/snapshots/recover \
  -H "Content-Type: application/json" \
  -d '{"location": "/qdrant/snapshots/snapshot-file"}'
```

### Export to Markdown
```bash
curl -X POST http://localhost:8010/api/v1/settings/backup \
  -H "Content-Type: application/json" \
  -d '{"type": "markdown"}'
```

## Troubleshooting

### Qdrant won't start
- Check port 6335 is available or override it in `.env`
- Verify Docker has sufficient memory (4GB+)

### Files not indexing
- Check folder paths in Settings
- Verify Docker has access to host paths
- Check file watcher logs: `docker-compose logs file-watcher`

### Agent chat not working
- Verify OpenClaw URL in Settings
- Check backend logs: `docker-compose logs backend`

### Search not finding results
- Wait for indexing to complete
- Check Qdrant collections: http://localhost:6335/dashboard

## License

MIT License - See LICENSE file

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Support

- GitHub Issues: [Report bugs](https://github.com/ghively/knowledge-os/issues)
- Documentation: [Wiki](https://github.com/ghively/knowledge-os/wiki)
