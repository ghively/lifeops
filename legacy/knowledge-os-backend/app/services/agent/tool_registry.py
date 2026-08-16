"""Unified tool registry for the agent runtime."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.database.qdrant_client import qdrant_manager
from app.services.agent.audit import AgentAuditLogger
from app.services.agent.cli_agent import CLIAgentTool
from app.services.agent.mcp_client import MCPClientManager
from app.services.agent.models import ToolDefinition, ToolResult
from app.services.agent.sandbox import ToolApprovalRequired, ToolSandbox, tool_approval_manager
from app.services.agent.security import AgentSecurityManager
from app.services.embedding import embedding_service
from app.utils.time import utc_now_iso

logger = logging.getLogger(__name__)


class RuntimeTool:
    def __init__(
        self,
        definition: ToolDefinition,
        executor: Callable[..., Awaitable[ToolResult]],
    ):
        self.definition = definition
        self._executor = executor

    @property
    def name(self) -> str:
        return self.definition.name

    async def execute(self, arguments: Dict[str, Any], **kwargs) -> ToolResult:
        return await self._executor(arguments, **kwargs)

    def openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.definition.name,
                "description": self.definition.description,
                "parameters": self.definition.parameters_schema or {"type": "object", "properties": {}},
            },
        }


class ToolRegistry:
    """Registers native, CLI, and MCP tools."""

    def __init__(
        self,
        cli_tool: Optional[CLIAgentTool] = None,
        mcp_manager: Optional[MCPClientManager] = None,
        sandbox: Optional[ToolSandbox] = None,
        security: Optional[AgentSecurityManager] = None,
        audit_logger: Optional[AgentAuditLogger] = None,
    ):
        self.cli_tool = cli_tool or CLIAgentTool()
        self.mcp_manager = mcp_manager or MCPClientManager()
        self.sandbox = sandbox or ToolSandbox()
        self.security = security or AgentSecurityManager()
        self.audit_logger = audit_logger
        self._tools: Dict[str, RuntimeTool] = {}
        self._register_native_tools()
        self._register_cli_tools()

    def list_tools(self, allowed_tools: Optional[List[str]] = None) -> List[ToolDefinition]:
        allowed = set(allowed_tools or [])
        definitions = [tool.definition for tool in self._tools.values()]
        definitions.extend(self.mcp_manager.list_tool_definitions())
        if not allowed:
            return definitions
        return [definition for definition in definitions if definition.name in allowed]

    def list_openai_tools(self, allowed_tools: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        allowed = set(allowed_tools or [])
        schemas = [
            tool.openai_schema()
            for tool in self._tools.values()
            if tool.definition.enabled and (not allowed or tool.definition.name in allowed)
        ]
        schemas.extend(
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters_schema or {"type": "object", "properties": {}},
                },
            }
            for definition in self.mcp_manager.list_tool_definitions()
            if definition.enabled and (not allowed or definition.name in allowed)
        )
        return schemas

    def get(self, name: str) -> RuntimeTool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        allowed_tools: Optional[List[str]] = None,
        *,
        context: Optional[Dict[str, Any]] = None,
        identity=None,
    ) -> ToolResult:
        if allowed_tools and name not in set(allowed_tools):
            return ToolResult(tool_name=name, success=False, error=f"Tool {name} is not available in this scope", content="")
        runtime_tool = self._tools.get(name)
        definition = runtime_tool.definition if runtime_tool else self._lookup_mcp_definition(name)

        if not definition:
            return ToolResult(tool_name=name, success=False, error=f"Unknown tool: {name}", content="")

        execution_context = context or {}

        if self.audit_logger and execution_context.get("agent_id"):
            await self.audit_logger.log_event(
                agent_id=execution_context["agent_id"],
                session_id=execution_context.get("session_id"),
                user_id=execution_context.get("user_id"),
                event_type="tool.call",
                details={"tool_name": name, "arguments": arguments},
            )

        if definition and definition.safety_level == "destructive" and not execution_context.get("approval_granted"):
            approval_request = await tool_approval_manager.create_request(
                {
                    "agent_id": execution_context.get("agent_id"),
                    "session_id": execution_context.get("session_id"),
                    "user_id": execution_context.get("user_id"),
                    "tool_name": name,
                    "description": definition.description,
                    "arguments": arguments,
                }
            )
            raise ToolApprovalRequired(approval_request)

        try:
            if runtime_tool:
                result = await runtime_tool.execute(
                    arguments, context=execution_context, identity=identity, definition=definition
                )
            else:
                result = await self.mcp_manager.execute_tool(name, arguments)
        except ToolApprovalRequired:
            raise
        except Exception as exc:
            logger.exception("Tool execution failed for %s", name)
            result = ToolResult(tool_name=name, success=False, error=str(exc), content="")
        result.content = self.security.sanitize_tool_output(result.content)
        if result.error:
            result.error = self.security.sanitize_tool_output(result.error)
        result.content, truncated = self.sandbox.truncate_output(result.content)
        result.truncated = result.truncated or truncated
        if self.audit_logger and execution_context.get("agent_id"):
            await self.audit_logger.log_event(
                agent_id=execution_context["agent_id"],
                session_id=execution_context.get("session_id"),
                user_id=execution_context.get("user_id"),
                event_type="tool.result",
                details={"tool_name": name, "success": result.success, "error": result.error, "truncated": result.truncated},
            )
        return result

    def _register(self, definition: ToolDefinition, executor: Callable[..., Awaitable[ToolResult]]) -> None:
        self._tools[definition.name] = RuntimeTool(definition, executor)

    def _lookup_mcp_definition(self, name: str) -> Optional[ToolDefinition]:
        for definition in self.mcp_manager.list_tool_definitions():
            if definition.name == name:
                return definition
        return None

    def _register_native_tools(self) -> None:
        self._register(
            ToolDefinition(
                name="create_object",
                description="Create a new knowledge object in Qdrant.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "object_type": {"type": "string"},
                        "properties": {"type": "object"},
                    },
                    "required": ["title"],
                },
                safety_level="internal",
            ),
            self._create_object,
        )
        self._register(
            ToolDefinition(
                name="search_knowledge",
                description="Search indexed knowledge objects and files.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "collection": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
                safety_level="safe",
            ),
            self._search_knowledge,
        )
        self._register(
            ToolDefinition(
                name="manage_tasks",
                description="List or update task objects.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["list", "update_status"]},
                        "task_id": {"type": "string"},
                        "status": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["action"],
                },
                safety_level="internal",
            ),
            self._manage_tasks,
        )
        self._register(
            ToolDefinition(
                name="read_file",
                description="Read a local file from the workspace.",
                parameters_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                safety_level="safe",
            ),
            self._read_file,
        )
        self._register(
            ToolDefinition(
                name="write_file",
                description="Write content to a local file in the workspace.",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
                safety_level="destructive",
            ),
            self._write_file,
        )

    def _register_cli_tools(self) -> None:
        for agent_name, config in self.cli_tool.AGENTS.items():
            self._register(
                ToolDefinition(
                    name=agent_name,
                    description=config.description or f"Delegate work to {agent_name}",
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string"},
                            "cwd": {"type": "string"},
                            "timeout": {"type": "integer"},
                        },
                        "required": ["prompt"],
                    },
                    safety_level="external",
                    source="cli",
                ),
                lambda args, agent_name=agent_name: self.cli_tool.execute(
                    agent_name,
                    args.get("prompt", ""),
                    cwd=args.get("cwd"),
                    timeout=args.get("timeout"),
                ),
            )

    async def _create_object(self, arguments: Dict[str, Any], **_) -> ToolResult:
        title = arguments.get("title", "").strip()
        content = arguments.get("content", "").strip()
        object_type = arguments.get("object_type", "note")
        if not title and not content and not object_type:
            return ToolResult(
                tool_name="create_object",
                success=False,
                error="At least one of title, content, or object_type must be non-empty",
                content="",
            )
        client = qdrant_manager.get_async_client()
        object_id = str(uuid.uuid4())
        payload = {
            "id": object_id,
            "type": object_type,
            "title": title,
            "content": content,
            "properties": arguments.get("properties", {}),
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        embedding = await embedding_service.embed_text(content or title or object_type)
        await client.upsert(
            collection_name="objects",
            points=[{"id": object_id, "vector": embedding.tolist(), "payload": payload}],
        )
        return ToolResult(tool_name="create_object", content=json.dumps({"id": object_id, "title": title}), data=payload)

    async def _search_knowledge(self, arguments: Dict[str, Any], **_) -> ToolResult:
        client = qdrant_manager.get_async_client()
        query = arguments.get("query", "").strip()
        collection = arguments.get("collection") or "objects"
        limit = int(arguments.get("limit", 5))
        embedding = await embedding_service.embed_text(query)
        results = await client.search(
            collection_name=collection,
            query_vector=embedding.tolist(),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        payloads = []
        for point in results:
            payload = dict(point.payload or {})
            payload["id"] = str(point.id)
            payload["score"] = point.score
            payloads.append(payload)
        return ToolResult(tool_name="search_knowledge", content=json.dumps(payloads), data={"results": payloads})

    async def _manage_tasks(self, arguments: Dict[str, Any], **_) -> ToolResult:
        client = qdrant_manager.get_async_client()
        action = arguments.get("action", "list")
        if action == "list":
            scroll = await client.scroll(
                collection_name="objects",
                scroll_filter={"must": [{"key": "type", "match": {"value": "task"}}]},
                limit=int(arguments.get("limit", 10)),
                with_payload=True,
                with_vectors=False,
            )
            tasks = []
            for point in scroll[0]:
                payload = dict(point.payload or {})
                payload["id"] = str(point.id)
                tasks.append(payload)
            return ToolResult(tool_name="manage_tasks", content=json.dumps(tasks), data={"tasks": tasks})

        if action == "update_status":
            task_id = arguments.get("task_id")
            status = arguments.get("status")
            if not task_id:
                return ToolResult(
                    tool_name="manage_tasks", success=False, error="task_id is required for update_status action", content=""
                )
            record = await client.retrieve(collection_name="objects", ids=[task_id], with_payload=True, with_vectors=False)
            if not record:
                return ToolResult(tool_name="manage_tasks", success=False, error="Task not found", content="")
            payload = dict(record[0].payload or {})
            payload.setdefault("properties", {})
            payload["properties"]["status"] = status
            payload["properties"]["updated_at"] = utc_now_iso()
            await client.set_payload(collection_name="objects", payload=payload, points=[task_id])
            return ToolResult(
                tool_name="manage_tasks", content=json.dumps({"task_id": task_id, "status": status}), data=payload
            )

        return ToolResult(tool_name="manage_tasks", success=False, error=f"Unsupported action: {action}", content="")

    async def _read_file(self, arguments: Dict[str, Any], *, identity=None, **_) -> ToolResult:
        sandbox = self.sandbox.allowed_for_identity(getattr(identity, "tool_preferences", {}))
        path = sandbox.validate_path(arguments["path"])
        content = path.read_text(encoding="utf-8")
        return ToolResult(tool_name="read_file", content=content, data={"path": str(path)})

    async def _write_file(self, arguments: Dict[str, Any], *, identity=None, **_) -> ToolResult:
        sandbox = self.sandbox.allowed_for_identity(getattr(identity, "tool_preferences", {}))
        path = sandbox.validate_path(arguments["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        content = arguments.get("content", "")
        path.write_text(content, encoding="utf-8")
        return ToolResult(tool_name="write_file", content=f"Wrote {path}", data={"path": str(path), "bytes": len(content)})
