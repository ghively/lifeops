"""Pydantic models for the agent runtime."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


SafetyLevel = Literal["safe", "internal", "external", "destructive"]
ProviderName = Literal["openai", "anthropic", "ollama", "google"]
MessageRole = Literal["system", "user", "assistant", "tool"]
StreamingEventType = Literal[
    "text_delta",
    "tool_start",
    "tool_result",
    "thinking",
    "subagent_start",
    "subagent_result",
    "approval_required",
    "security_warning",
    "done",
    "error",
]
MCPTransport = Literal["stdio", "http"]
MCPServerState = Literal["connected", "disconnected", "error"]
ScheduledTaskType = Literal["periodic_research", "memory_curation", "data_cleanup", "webhook_triggered"]


class LLMProviderConfig(BaseModel):
    provider: ProviderName = "openai"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_tokens: int = 2048
    fallback_model: Optional[str] = None


class CLIAgentConfig(BaseModel):
    name: str
    command: str
    args: List[str] = Field(default_factory=list)
    install_check: Optional[str] = None
    timeout: int = 300
    description: str = ""
    enabled: bool = True
    env: Dict[str, str] = Field(default_factory=dict)


class MCPServerConfig(BaseModel):
    name: str
    transport: MCPTransport
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 30
    enabled: bool = True
    auto_connect: bool = True

    @model_validator(mode="after")
    def validate_transport_fields(self) -> "MCPServerConfig":
        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio MCP servers require a command")
        if self.transport == "http" and not self.url:
            raise ValueError("http MCP servers require a url")
        return self


class MCPServerStatus(BaseModel):
    name: str
    transport: MCPTransport
    connected: bool = False
    state: MCPServerState = "disconnected"
    enabled: bool = True
    auto_connect: bool = True
    tool_count: int = 0
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    last_checked_at: Optional[str] = None
    last_connected_at: Optional[str] = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters_schema: Dict[str, Any] = Field(default_factory=dict)
    safety_level: SafetyLevel = "safe"
    source: Literal["native", "cli", "mcp"] = "native"
    enabled: bool = True


class ToolResult(BaseModel):
    tool_name: str
    success: bool = True
    content: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    truncated: bool = False


class MemoryEntry(BaseModel):
    id: str
    content: str
    source: Literal["daily_log", "memory_md", "qdrant", "working"] = "working"
    timestamp: Optional[str] = None
    score: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tokens: int = 0


class AgentIdentity(BaseModel):
    agent_id: str
    name: str
    model: str = "gpt-4o-mini"
    capabilities: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    instructions: str = ""
    personality: str = ""
    tone: str = ""
    rules: List[str] = Field(default_factory=list)
    long_term_memory: str = ""
    system_prompt: str = ""
    cli_agents: List[CLIAgentConfig] = Field(default_factory=list)
    mcp_servers: List[Dict[str, Any]] = Field(default_factory=list)
    llm: Optional[LLMProviderConfig] = None
    tool_preferences: Dict[str, Any] = Field(default_factory=dict)
    rate_limits: Dict[str, int] = Field(default_factory=dict)
    file_mtimes: Dict[str, float] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    agent_id: str
    root_path: str
    identity: AgentIdentity


class AgentMessage(BaseModel):
    id: Optional[str] = None
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    tool_results: List[ToolResult] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentSession(BaseModel):
    id: str
    agent_id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentUsageSnapshot(BaseModel):
    agent_id: str
    user_id: str
    minute_requests: int = 0
    minute_limit: int = 0
    daily_tokens: int = 0
    daily_token_limit: int = 0
    daily_requests: int = 0
    retry_after_seconds: int = 0
    date: Optional[str] = None


class AgentAuditEvent(BaseModel):
    id: Optional[str] = None
    agent_id: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    event_type: str
    details: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class StreamingEvent(BaseModel):
    type: StreamingEventType
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    message: Optional[str] = None
    delta: Optional[str] = None
    tool_name: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class AgentMention(BaseModel):
    agent_id: str
    name: str
    summary: str
    system_prompt: str = ""


class AgentRouteMessageRequest(BaseModel):
    from_agent_id: str
    to_agent_id: str
    message: str
    shared_context: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None
    timeout_seconds: int = 90


class AgentScheduledTask(BaseModel):
    id: str
    agent_id: str
    name: str
    cron_expression: str
    task_type: ScheduledTaskType
    config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    created_at: Optional[str] = None


class AgentWebhook(BaseModel):
    id: str
    agent_id: str
    name: str
    url_path: str
    secret: str
    event_type: str
    enabled: bool = True
    created_at: Optional[str] = None


class AgentTemplate(BaseModel):
    id: str
    name: str
    description: str
    files: Dict[str, str] = Field(default_factory=dict)


class SubAgentTask(BaseModel):
    agent_id: str
    prompt: str
    allowed_tools: List[str] = Field(default_factory=list)
    shared_context: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 90


class SubAgentResult(BaseModel):
    agent_id: str
    success: bool = True
    content: str = ""
    session_id: Optional[str] = None
    error: Optional[str] = None
    tool_results: List[ToolResult] = Field(default_factory=list)
