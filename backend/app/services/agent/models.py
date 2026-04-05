"""Pydantic models for the agent runtime."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SafetyLevel = Literal["safe", "internal", "external", "destructive"]
ProviderName = Literal["openai", "anthropic", "ollama", "google"]
MessageRole = Literal["system", "user", "assistant", "tool"]
StreamingEventType = Literal["text_delta", "tool_start", "tool_result", "thinking", "done", "error"]


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


class StreamingEvent(BaseModel):
    type: StreamingEventType
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    message: Optional[str] = None
    delta: Optional[str] = None
    tool_name: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)

