# Agent System Guide

Complete guide to the Agent Runtime System, building custom agents, and using agents effectively.

---

## Table of Contents

1. [Agent Architecture](#agent-architecture)
2. [Agent Identity](#agent-identity)
3. [Built-in Agents](#built-in-agents)
4. [Creating Custom Agents](#creating-custom-agents)
5. [Tool System](#tool-system)
6. [Memory Management](#memory-management)
7. [Scheduling](#scheduling)
8. [Webhooks](#webhooks)
9. [MCP Integration](#mcp-integration)
10. [Troubleshooting](#troubleshooting)

---

## Agent Architecture

### Component Stack

```
Agent Runtime (Central Orchestrator)
├─ Agent Loop (ReAct execution)
├─ Session Manager (Chat persistence)
├─ Memory Manager (Semantic retrieval)
├─ Tool Registry (Tool management)
├─ LLM Router (Provider routing)
├─ Rate Limiter (Token budgeting)
├─ Audit Logger (Decision logging)
├─ Scheduler (Background tasks)
├─ Collaboration Service (Sub-agents)
├─ Webhook Service (Event triggers)
└─ Security Manager (Approval gates)
```

### Execution Flow

```
User Message
    ↓
Session Management (create or load)
    ↓
Context Building (gather context from objects, files, memories)
    ↓
Agent Loop (max 10 iterations):
  1. THINK: LLM generates response/tool_calls
  2. CHOOSE: Parse tools, check rate limits
  3. EXECUTE: Run tools in sandbox
  4. OBSERVE: Process results
  5. CONTINUE or STOP?
    ↓
Response Streaming (SSE to client)
    ↓
Post-Processing (save, audit, memory update)
```

### Resource Limits

**Per-Agent (Daily):**
- 100,000 tokens (configurable)
- 1,000 requests
- 10 requests per minute

**Per-Iteration:**
- Max 10 iterations per message
- 300 seconds max execution time
- 4KB per tool output (truncated)

---

## Agent Identity

Agents are defined using **Markdown files** (inspired by OpenClaw):

### File Structure

```
/agents/{agent-name}/
├─ AGENT.md          # Identity & capabilities
├─ SOUL.md           # Personality & values
├─ MEMORY.md         # Curated memories
└─ TOOLS.md          # Available tools
```

### AGENT.md

Defines agent identity and capabilities:

```markdown
# Researcher Agent

A specialized agent for research and information gathering.

## Capabilities
- Semantic search across knowledge base
- Web search and summarization
- Data analysis and visualization
- Report generation

## Instructions
- Always cite sources
- Verify information accuracy
- Provide balanced perspectives
- Update memory after research

## Tools
Allowed to use: search, read, write, execute_code, web_search
```

### SOUL.md

Defines personality and values:

```markdown
# Soul & Values

## Personality
- Inquisitive and thorough
- Respectful of privacy
- Eager to help and collaborate

## Values
- Accuracy over speed
- Transparency in process
- Respect user autonomy
- Learn from feedback

## Communication Style
- Clear and organized
- Sources and citations
- Adaptive to user needs
```

### MEMORY.md

Curated memories updated daily:

```markdown
# Memory Log

## Key Facts
- User prefers concise summaries
- Interest in machine learning
- Timezone: EST

## Recent Interactions
- Researched climate policy (2026-04-23)
- Analyzed market trends (2026-04-22)

## Skills & Knowledge
- Expert in data science
- Python and R fluent
```

### TOOLS.md

Declares available tools:

```markdown
# Available Tools

## Built-in Tools
- search(query) - Semantic search
- read(path) - Read file
- write(path, content) - Write file

## External Tools
- web_search(query) - Brave Search API
- execute_code(language, code) - Run code

## Restrictions
- No write access outside /data
- No execution without approval
```

---

## Built-in Agents

Knowledge OS comes with 5 pre-configured agent templates:

### Researcher Agent

Specializes in research and information gathering.

```bash
POST /api/v1/agents/researcher/chat
```

**Capabilities:**
- Semantic search
- Web search (if configured)
- Analysis and summarization

### Writer Agent

Specializes in content creation and editing.

```bash
POST /api/v1/agents/writer/chat
```

**Capabilities:**
- Content generation
- Editing and refinement
- Formatting and styling

### Coder Agent

Specializes in programming tasks.

```bash
POST /api/v1/agents/coder/chat
```

**Capabilities:**
- Code generation
- Debugging
- Optimization suggestions

### Analyst Agent

Specializes in data analysis.

```bash
POST /api/v1/agents/analyst/chat
```

**Capabilities:**
- Data analysis
- Visualization
- Reporting

### Personal Assistant

General-purpose helpful assistant.

```bash
POST /api/v1/agents/personal-assistant/chat
```

**Capabilities:**
- Task management
- Scheduling
- Information retrieval

---

## Creating Custom Agents

### Step 1: Create Agent Directory

```bash
mkdir -p agents/my-agent
cd agents/my-agent
```

### Step 2: Create AGENT.md

```markdown
# My Custom Agent

Description of what your agent does.

## Capabilities
- Capability 1
- Capability 2

## Instructions
- Instruction 1
- Instruction 2

## Domain
Specify what domain/area this agent specializes in.
```

### Step 3: Create SOUL.md

```markdown
# Personality

## Traits
- Trait 1
- Trait 2

## Values
- Value 1
- Value 2

## Communication Style
How should this agent communicate?
```

### Step 4: Create TOOLS.md

```markdown
# Available Tools

## Built-in Tools
- search - Semantic search
- read - Read files

## External Tools
(List any external tools)

## Restrictions
(Any limitations)
```

### Step 5: Create MEMORY.md

```markdown
# Memory

## Summary
Summary of important facts and learnings.
```

### Step 6: Verify

The agent should now appear in:
```bash
GET /api/v1/agents
```

And be accessible at:
```bash
POST /api/v1/agents/my-agent/chat
```

---

## Tool System

### Built-in Tools

**search(query: str) → List[Object]**
```python
# Semantic search across objects
result = agent.tool_search("best practices for AI safety")
```

**read(path: str) → str**
```python
# Read file content
content = agent.tool_read("/data/notes/project.md")
```

**write(path: str, content: str) → None**
```python
# Write file content
agent.tool_write("/data/notes/new.md", "Content")
```

**execute_code(language: str, code: str) → str**
```python
# Execute code in sandbox
result = agent.tool_execute_code("python", "print(2+2)")
```

### Tool Approval Flow

Dangerous tools require human approval:

```python
# Tool is dangerous if:
if tool.destructive or tool.requires_approval:
    # Send approval request to user
    await approval_manager.request(
        agent_id=agent_id,
        tool_name="delete_file",
        description="Delete /data/old-file.txt",
        timeout=300  # 5 minute timeout
    )
    
    # Wait for user response
    response = await approval_manager.wait(request_id)
    
    if response.approved:
        # Execute tool
        result = await tool.execute()
    else:
        # Reject and inform agent
        error = ToolRejected("User denied approval")
```

**User sees approval dialog:**
```
Tool Approval Required

Agent: Researcher
Tool: delete_file
Description: Delete old research document

Arguments:
  path: /data/archive/2025-research.txt

[Approve] [Deny]
```

### Tool Sandbox

Tools execute in a restricted environment:

**Filesystem:**
- Read: `/data`, `/tmp`
- Write: `/data`, `/tmp`
- No access: `/`, `/etc`, `/home`, etc.

**Network:**
- Allowed: HTTP(S) requests
- Blocked: Raw sockets, SSH

**Execution:**
- Max 30 seconds per tool
- Single process (no spawning)
- Memory limited

**Output:**
- Max 4KB returned to agent
- Longer output truncated with `[... output truncated]`

---

## Memory Management

### Automatic Memory

Agents automatically create daily memory logs:

```
/agents/{agent-name}/memory/{date}.txt
```

**Entry Format:**
```
[10:00] Researched climate policy
[11:30] Analyzed market trends
[14:00] Helped user with writing task
```

### Memory Retrieval

When processing messages, agents automatically retrieve relevant memories:

```python
# Semantic search for relevant memories
relevant_memories = memory_manager.search(
    agent_id=agent_id,
    query=user_message,
    limit=5,
    days_back=30  # Last 30 days
)

# Included in context for LLM
context = {
    "recent_memories": relevant_memories,
    "agent_identity": agent_identity,
    "conversation_history": history
}
```

### Memory Curation

Daily curation updates MEMORY.md:

```python
# Automatic daily at 23:00 UTC
curated = memory_curation_service.curate(
    agent_id=agent_id,
    day=yesterday,
    max_tokens=500
)

# Updates MEMORY.md with important facts
```

Manual curation endpoint:

```bash
POST /api/v1/agent-runtime/{agent_id}/curate-memory
```

---

## Scheduling

### Create Scheduled Task

```bash
POST /api/v1/agent-runtime/schedule
Content-Type: application/json

{
  "agent_id": "researcher",
  "name": "Daily Research",
  "cron_expression": "0 9 * * *",
  "task_type": "periodic_research",
  "config": {
    "topic": "AI Safety",
    "depth": "comprehensive"
  },
  "enabled": true
}
```

### Cron Expression Format

Standard cron format (5 fields):

```
minute hour day_of_month month day_of_week
0      9    *            *     *            # 9 AM every day
0      9    *            *     1-5          # 9 AM weekdays
*/15   *    *            *     *            # Every 15 minutes
0      0    1            *     *            # 1st of month
0      */4  *            *     *            # Every 4 hours
```

### List Scheduled Tasks

```bash
GET /api/v1/agent-runtime/schedule
```

### Manually Run Task

```bash
POST /api/v1/agent-runtime/schedule/{task_id}/run
```

### Delete Task

```bash
DELETE /api/v1/agent-runtime/schedule/{task_id}
```

---

## Webhooks

### Create Webhook

```bash
POST /api/v1/agent-runtime/webhooks
Content-Type: application/json

{
  "agent_id": "researcher",
  "name": "API Update Trigger",
  "event_type": "api_update",
  "enabled": true
}
```

**Response:**
```json
{
  "id": "webhook-id",
  "url_path": "/api/v1/webhooks/incoming/webhook-id",
  "secret": "secret-key-for-hmac"
}
```

### Trigger Webhook

```bash
POST /api/v1/webhooks/incoming/{webhook_id}
Content-Type: application/json
X-Webhook-Signature: sha256=...

{
  "event": "data_updated",
  "data": {...}
}
```

**Signature Verification:**
```python
# Calculate: HMAC-SHA256(secret, body)
expected_sig = hmac.new(
    secret.encode(),
    body,
    hashlib.sha256
).hexdigest()

if expected_sig == provided_sig:
    # Valid webhook
```

### Webhook Processing

When webhook received:
1. Verify HMAC signature
2. Trigger agent with webhook data
3. Agent processes event
4. Results logged to audit trail

---

## MCP Integration

### Add MCP Server

```bash
POST /api/v1/agent-runtime/mcp/servers
Content-Type: application/json

{
  "name": "filesystem",
  "transport": "stdio",
  "command": "python -m mcp_server_filesystem",
  "args": ["/data"],
  "enabled": true
}
```

### List MCP Servers

```bash
GET /api/v1/agent-runtime/mcp/servers
```

### Get Server Tools

```bash
GET /api/v1/agent-runtime/mcp/servers/filesystem/tools
```

**Response:**
```json
{
  "tools": [
    {
      "name": "read_file",
      "description": "Read file content",
      "input_schema": {
        "type": "object",
        "properties": {
          "path": {"type": "string"}
        }
      }
    }
  ]
}
```

### Test MCP Server

```bash
POST /api/v1/agent-runtime/mcp/test
Content-Type: application/json

{
  "server": "filesystem",
  "tool": "read_file",
  "args": {"path": "/data/test.txt"}
}
```

---

## Usage Tracking

### Get Agent Usage

```bash
GET /api/v1/agent-runtime/{agent_id}/usage
```

**Response:**
```json
{
  "current": {
    "agent_id": "researcher",
    "minute_requests": 5,
    "minute_limit": 10,
    "daily_tokens": 45000,
    "daily_token_limit": 100000,
    "retry_after_seconds": 0
  },
  "history": [
    {
      "date": "2026-04-23",
      "total_tokens": 32000,
      "total_requests": 87
    }
  ]
}
```

### Get Audit Log

```bash
GET /api/v1/agent-runtime/{agent_id}/audit
```

Shows all agent decisions and actions.

---

## Troubleshooting

### Agent Not Responding

1. Check agent status:
```bash
GET /api/v1/agents/researcher
```

2. Check LLM provider:
```bash
curl http://localhost:11434/api/tags  # Ollama
```

3. Check logs:
```bash
GET /api/v1/system/logs?source=backend&level=error
```

### Tool Execution Fails

1. Check tool availability:
```bash
GET /api/v1/agent-runtime/mcp/servers/{server}/tools
```

2. Test tool directly:
```bash
POST /api/v1/agent-runtime/mcp/test
```

3. Check sandbox restrictions (filesystem, network)

### Rate Limit Exceeded

```json
{
  "detail": "Rate limit exceeded",
  "retry_after_seconds": 300
}
```

Solutions:
- Wait 5 minutes for minute limit to reset
- Wait 24 hours for daily limit
- Increase limits in configuration

### Memory Not Updating

Check curation task:
```bash
GET /api/v1/agent-runtime/schedule?name=Memory%20Curation
```

Manual curation:
```bash
POST /api/v1/agent-runtime/{agent_id}/curate-memory
```

---

## Best Practices

1. **Clear Identity** — Well-defined AGENT.md helps LLM understand purpose
2. **Specific Instructions** — Detailed instructions improve output quality
3. **Tool Minimalism** — Provide only necessary tools
4. **Regular Curation** — Update MEMORY.md with important facts
5. **Monitor Usage** — Track token usage to avoid limits
6. **Test Thoroughly** — Test with varied inputs before production

---

**See also:**
- [API.md](API.md) - Agent endpoints
- [CONFIGURATION.md](CONFIGURATION.md) - Agent configuration
- [Architecture](ARCHITECTURE.md) - Technical details
