# Phase 1: Agent Runtime — Implementation Plan

## Overview

Build the core agent runtime with:
1. Agent identity system (markdown files)
2. LLM routing (multi-provider)
3. Native tool execution
4. CLI agent delegation (Codex, Claude Code, Kimi CLI, Gemini CLI)
5. MCP client support
6. Agent loop (ReAct pattern)
7. Streaming responses (SSE)
8. Session management
9. Auto-memory (daily logs + MEMORY.md curation)

## Architecture

```
User → Agent Chat (WebSocket)
         ↓
    Agent Orchestrator
    ├── IdentityLoader (AGENT.md, SOUL.md, MEMORY.md, TOOLS.md)
    ├── LLMRouter (OpenAI/Anthropic/Ollama/Google)
    ├── ToolRegistry
    │   ├── Native tools (create_object, search, manage_tasks, etc.)
    │   ├── CLI Agent tools (codex, claude_code, kimi, gemini, opencode)
    │   └── MCP Client (external tool servers)
    ├── MemoryManager (daily logs, Qdrant, MEMORY.md)
    └── SessionManager (conversation history, context window)
```

## Key Design Decisions

### CLI Agent Delegation (NOT API-based sub-agents)

Instead of spawning in-process sub-agents that need their own API keys, delegate to CLI tools:

```python
class CLIAgentTool:
    """Delegate tasks to external CLI coding agents."""
    
    AGENTS = {
        "codex": {
            "command": "codex",
            "args": ["--full-auto", "--print"],
            "install_check": "which codex",
            "env": {},  # Uses system SSO or API key
            "timeout": 300,
            "description": "OpenAI Codex CLI — coding, file editing, git operations",
        },
        "claude_code": {
            "command": "claude",
            "args": ["--print", "--permission-mode", "bypassPermissions"],
            "install_check": "which claude",
            "timeout": 300,
            "description": "Claude Code — coding, analysis, file operations",
        },
        "kimi": {
            "command": "kimi",
            "args": ["--print"],
            "install_check": "which kimi",
            "timeout": 300,
            "description": "Kimi CLI — coding, research, web search (256K context)",
        },
        "gemini": {
            "command": "gemini",
            "args": ["-p"],
            "install_check": "which gemini",
            "timeout": 120,
            "description": "Gemini CLI — analysis, research, Google Search grounding",
        },
        "opencode": {
            "command": "opencode",
            "args": ["--non-interactive"],
            "install_check": "which opencode",
            "timeout": 300,
            "description": "OpenCode — coding assistant",
        },
    }
```

**Why CLI delegation over API sub-agents:**
- No extra API keys needed — CLIs use their own auth (SSO, subscriptions, etc.)
- Coding-plan restrictions are respected (Kimi Code stays as coding tool)
- Each CLI has its own strengths (Codex for code, Gemini for analysis, Kimi for research)
- Privacy: local agent stays in your data, CLIs run in their own sandboxed processes
- Works offline with local models (Ollama via any CLI that supports it)

### Agent Loop (ReAct)

```
while not done:
    1. Build context (identity + memory + conversation history + retrieved memories)
    2. Call LLM with tools
    3. If LLM wants to use a tool:
       a. Execute tool (native, CLI, or MCP)
       b. Add tool result to conversation
       c. Go to step 2
    4. If LLM responds with text:
       a. Stream to user
       b. Check if agent wants to remember something
       c. Done
```

### Memory (Qdrant + Markdown Hybrid)

- **Markdown files** are source of truth (human-readable, editable)
- **Qdrant** stores embeddings for semantic retrieval
- Daily logs → `memory/YYYY-MM-DD.md` (auto-written by agent)
- Long-term → `MEMORY.md` (curated periodically by agent)
- Working memory → in-memory dict, flushed to daily log on session end

### LLM Provider Config

Users configure providers in Settings or per-agent in TOOLS.md:

```yaml
# TOOLS.md example
## LLM Provider
model: openai/gpt-4o
fallback: anthropic/claude-sonnet-4-20250514

## CLI Agents Available
- codex: coding, git, file operations
- gemini: analysis, research, documentation
- kimi: research, web search, coding

## MCP Servers
- name: brave-search
  transport: stdio
  command: npx
  args: ["-y", "@anthropic/mcp-server-brave-search"]
```

## File Structure (per agent)

```
backend/agents/
└── {agent_id}/
    ├── AGENT.md          # Identity, model, capabilities
    ├── SOUL.md           # Personality, rules
    ├── MEMORY.md         # Long-term curated memory
    ├── TOOLS.md          # Tool config, MCP servers, CLI agents
    └── memory/
        └── 2026-04-05.md # Daily logs
```

## New Backend Files

```
backend/app/services/agent/
├── __init__.py
├── runtime.py           # AgentRuntime — main orchestrator
├── identity.py          # IdentityLoader — parse markdown files
├── llm_router.py        # LLMRouter — multi-provider abstraction
├── tool_registry.py     # ToolRegistry — native + CLI + MCP tools
├── cli_agent.py         # CLIAgentTool — delegate to CLI coding agents
├── mcp_client.py        # MCPClient — connect to MCP servers
├── agent_loop.py        # ReAct loop implementation
├── memory.py            # MemoryManager — daily logs, Qdrant, curation
├── session.py           # SessionManager — conversation history
├── streaming.py         # SSE streaming helpers
└── models.py            # Pydantic models for agent system
```

## API Endpoints

```
POST   /api/v1/agents/{id}/chat          # Send message (returns SSE stream)
GET    /api/v1/agents/{id}/chat/stream   # SSE endpoint for streaming
GET    /api/v1/agents/{id}/sessions      # List sessions
GET    /api/v1/agents/{id}/sessions/{sid}# Get session history
DELETE /api/v1/agents/{id}/sessions/{sid}# Delete session

# Agent management
POST   /api/v1/agents                     # Create agent
PUT    /api/v1/agents/{id}               # Update agent config
GET    /api/v1/agents/{id}               # Get agent details
GET    /api/v1/agents/{id}/files         # List agent markdown files
GET    /api/v1/agents/{id}/files/{name}  # Get file content
PUT    /api/v1/agents/{id}/files/{name}  # Update file content

# CLI agent status
GET    /api/v1/agents/cli/status         # Which CLI agents are available
```

## Database Schema (additions to SQLite)

```sql
CREATE TABLE agent_sessions (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    message_count INTEGER DEFAULT 0,
    metadata TEXT
);

CREATE TABLE agent_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_sessions(id),
    role TEXT NOT NULL,  -- user, assistant, system, tool
    content TEXT NOT NULL,
    tool_calls TEXT,     -- JSON array of tool calls
    tool_results TEXT,   -- JSON array of tool results
    tokens_in INTEGER,
    tokens_out INTEGER,
    created_at TEXT NOT NULL
);
```

## Implementation Order

1. **models.py** — Pydantic models for everything
2. **identity.py** — Parse AGENT.md, SOUL.md, MEMORY.md, TOOLS.md
3. **llm_router.py** — Provider abstraction (start with OpenAI-compatible)
4. **cli_agent.py** — CLI subprocess delegation
5. **tool_registry.py** — Unified tool interface (native + CLI + MCP stub)
6. **agent_loop.py** — ReAct loop
7. **memory.py** — Daily logs + Qdrant retrieval
8. **session.py** — SQLite session/message persistence
9. **streaming.py** — SSE helpers
10. **runtime.py** — Wire everything together
11. **API routes** — New router for agent chat
12. **Tests** — Unit tests for each component

## Dependencies to Add

```
# backend/requirements.txt
openai>=1.0.0          # OpenAI-compatible client (works with most providers)
mcp>=1.0.0             # Official MCP Python SDK
tiktoken>=0.5.0        # Token counting
watchfiles>=0.20.0     # File watching for hot-reload agent config
```
