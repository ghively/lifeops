"""Async MCP client manager for runtime tool integration."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.database.sqlite import sqlite_manager
from app.services.agent.models import MCPServerConfig, MCPServerStatus, ToolDefinition, ToolResult
from app.utils.time import utc_now_iso

logger = logging.getLogger(__name__)


def _runtime_tool_name(server_name: str, tool_name: str) -> str:
    return f"mcp__{server_name}__{tool_name}"


@dataclass
class MCPConnectionHandle:
    config: MCPServerConfig
    session: Any
    exit_stack: AsyncExitStack
    tools: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    state: str = "disconnected"
    error: Optional[str] = None
    last_checked_at: Optional[str] = None
    last_connected_at: Optional[str] = None


class MCPClientManager:
    """Manages configured MCP servers and routes tool calls."""

    def __init__(self, default_timeout_seconds: int = 30):
        self.default_timeout_seconds = default_timeout_seconds
        self._configs: Dict[str, MCPServerConfig] = {}
        self._connections: Dict[str, MCPConnectionHandle] = {}
        self._tool_routes: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        persisted = await sqlite_manager.list_mcp_server_configs()
        async with self._lock:
            self._configs = {item["name"]: MCPServerConfig(**item) for item in persisted}
        for config in list(self._configs.values()):
            if config.enabled and config.auto_connect:
                try:
                    await self.connect_server(config.name)
                except Exception:
                    logger.warning("Failed to auto-connect MCP server %s", config.name, exc_info=True)

    async def shutdown(self) -> None:
        for name in list(self._connections.keys()):
            await self.disconnect_server(name)

    async def ensure_servers(self, server_configs: List[Dict[str, Any]] | List[MCPServerConfig], persist: bool = False) -> None:
        for item in server_configs:
            config = item if isinstance(item, MCPServerConfig) else MCPServerConfig(**item)
            await self.configure_server(config, persist=persist)
            if config.enabled and config.auto_connect and not self.is_connected(config.name):
                try:
                    await self.connect_server(config.name)
                except Exception:
                    logger.warning("Failed to connect MCP server %s during ensure", config.name, exc_info=True)

    async def configure_server(self, config: MCPServerConfig, persist: bool = True) -> MCPServerStatus:
        async with self._lock:
            self._configs[config.name] = config
        if persist:
            await sqlite_manager.upsert_mcp_server_config(config.model_dump())
        if self.is_connected(config.name):
            await self.disconnect_server(config.name)
        return self._status_for(config.name)

    async def remove_server(self, name: str) -> None:
        await self.disconnect_server(name)
        async with self._lock:
            self._configs.pop(name, None)
        await sqlite_manager.delete_mcp_server_config(name)

    def is_connected(self, name: str) -> bool:
        connection = self._connections.get(name)
        return bool(connection and connection.state == "connected")

    def list_tool_definitions(self, server_name: Optional[str] = None) -> List[ToolDefinition]:
        tools: List[ToolDefinition] = []
        connections = (
            [(server_name, self._connections.get(server_name))]
            if server_name
            else sorted(self._connections.items(), key=lambda item: item[0])
        )
        for name, connection in connections:
            if not connection or connection.state != "connected":
                continue
            for tool in connection.tools.values():
                tools.append(
                    ToolDefinition(
                        name=tool["runtime_name"],
                        description=tool["description"],
                        parameters_schema=tool["input_schema"],
                        safety_level="external",
                        source="mcp",
                    )
                )
        return tools

    def list_server_tools(self, name: str) -> List[Dict[str, Any]]:
        connection = self._connections.get(name)
        if not connection:
            return []
        return list(connection.tools.values())

    async def list_servers(self) -> List[MCPServerStatus]:
        async with self._lock:
            names = sorted(self._configs.keys())
        return [self._status_for(name) for name in names]

    async def get_server_status(self, name: str) -> MCPServerStatus:
        return self._status_for(name)

    async def connect_server(self, name: str) -> MCPServerStatus:
        config = self._configs.get(name)
        if not config:
            raise KeyError(f"Unknown MCP server: {name}")

        await self.disconnect_server(name)
        exit_stack = AsyncExitStack()
        started_at = time.perf_counter()
        try:
            session = await self._open_session(config, exit_stack)
            connection = MCPConnectionHandle(
                config=config,
                session=session,
                exit_stack=exit_stack,
                state="connected",
                last_connected_at=utc_now_iso(),
                last_checked_at=utc_now_iso(),
            )
            self._connections[name] = connection
            await self.refresh_tools(name)
            logger.info("Connected MCP server %s", name, extra={"duration_ms": round((time.perf_counter() - started_at) * 1000, 2)})
            return self._status_for(name)
        except Exception as exc:
            await exit_stack.aclose()
            self._connections[name] = MCPConnectionHandle(
                config=config,
                session=None,
                exit_stack=AsyncExitStack(),
                state="error",
                error=str(exc),
                last_checked_at=utc_now_iso(),
            )
            logger.warning("Failed to connect MCP server %s", name, exc_info=True)
            raise

    async def disconnect_server(self, name: str) -> MCPServerStatus:
        connection = self._connections.pop(name, None)
        if connection:
            try:
                await connection.exit_stack.aclose()
            except Exception:
                logger.warning("Failed to close MCP server connection %s cleanly", name, exc_info=True)
            for runtime_name in list(connection.tools.keys()):
                self._tool_routes.pop(runtime_name, None)
        return self._status_for(name)

    async def refresh_tools(self, name: str) -> List[Dict[str, Any]]:
        connection = self._connections.get(name)
        if not connection or connection.state != "connected":
            return []

        try:
            result = await asyncio.wait_for(
                connection.session.list_tools(),
                timeout=connection.config.timeout_seconds or self.default_timeout_seconds,
            )
            tools = getattr(result, "tools", []) or []
            for runtime_name in list(connection.tools.keys()):
                self._tool_routes.pop(runtime_name, None)
            connection.tools = {
                _runtime_tool_name(name, tool.name): self._tool_to_dict(name, tool)
                for tool in tools
            }
            connection.state = "connected"
            connection.error = None
            connection.last_checked_at = utc_now_iso()
            for runtime_name in list(connection.tools.keys()):
                self._tool_routes[runtime_name] = name
            return list(connection.tools.values())
        except Exception as exc:
            connection.state = "error"
            connection.error = str(exc)
            connection.last_checked_at = utc_now_iso()
            logger.warning("Failed to refresh MCP tools for %s", name, exc_info=True)
            return []

    async def health_check(self, name: Optional[str] = None) -> List[MCPServerStatus]:
        names = [name] if name else sorted(self._configs.keys())
        statuses = []
        for server_name in names:
            connection = self._connections.get(server_name)
            if connection and connection.state == "connected":
                try:
                    if hasattr(connection.session, "send_ping"):
                        await asyncio.wait_for(
                            connection.session.send_ping(),
                            timeout=connection.config.timeout_seconds or self.default_timeout_seconds,
                        )
                    else:
                        await self.refresh_tools(server_name)
                    connection.error = None
                    connection.state = "connected"
                    connection.last_checked_at = utc_now_iso()
                except Exception as exc:
                    connection.state = "error"
                    connection.error = str(exc)
                    connection.last_checked_at = utc_now_iso()
                    logger.warning("MCP health check failed for %s", server_name, exc_info=True)
            statuses.append(self._status_for(server_name))
        return statuses

    async def execute_tool(self, runtime_name: str, arguments: Dict[str, Any]) -> ToolResult:
        server_name = self._tool_routes.get(runtime_name)
        if not server_name and runtime_name.startswith("mcp__"):
            parts = runtime_name.split("__", 2)
            if len(parts) == 3:
                server_name = parts[1]
                if server_name in self._configs and not self.is_connected(server_name):
                    await self.connect_server(server_name)
                    await self.refresh_tools(server_name)
                    server_name = self._tool_routes.get(runtime_name, server_name)
        if not server_name:
            raise KeyError(f"Unknown MCP tool: {runtime_name}")

        connection = self._connections.get(server_name)
        if not connection or connection.state != "connected":
            return ToolResult(
                tool_name=runtime_name,
                success=False,
                error=f"MCP server '{server_name}' is not connected",
                content="",
            )

        tool = connection.tools.get(runtime_name)
        if not tool:
            await self.refresh_tools(server_name)
            tool = connection.tools.get(runtime_name)
        if not tool:
            raise KeyError(f"Unknown MCP tool: {runtime_name}")

        started_at = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                connection.session.call_tool(tool["name"], arguments=arguments or {}),
                timeout=connection.config.timeout_seconds or self.default_timeout_seconds,
            )
            duration_ms = int(round((time.perf_counter() - started_at) * 1000))
            payload = self._tool_result_payload(response)
            return ToolResult(
                tool_name=runtime_name,
                success=not payload["is_error"],
                content=payload["content"],
                data={
                    "server_name": server_name,
                    "tool_name": tool["name"],
                    "structured_content": payload["structured_content"],
                    "content_items": payload["content_items"],
                },
                error=payload["error"],
                duration_ms=duration_ms,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                tool_name=runtime_name,
                success=False,
                error=f"MCP tool call timed out after {connection.config.timeout_seconds} seconds",
                duration_ms=int(round((time.perf_counter() - started_at) * 1000)),
            )
        except Exception as exc:
            connection.state = "error"
            connection.error = str(exc)
            connection.last_checked_at = utc_now_iso()
            logger.warning("MCP tool call failed for %s on %s", runtime_name, server_name, exc_info=True)
            return ToolResult(
                tool_name=runtime_name,
                success=False,
                error=str(exc),
                duration_ms=int(round((time.perf_counter() - started_at) * 1000)),
            )

    async def test_connection(self, config: MCPServerConfig) -> Dict[str, Any]:
        test_name = f"__test__{config.name}"
        async with self._lock:
            original_config = self._configs.get(test_name)
            self._configs[test_name] = config.model_copy(update={"name": test_name})
        try:
            await self.connect_server(test_name)
            tools = self.list_server_tools(test_name)
            return {"success": True, "tools": tools, "status": self._status_for(test_name).model_dump()}
        except Exception as exc:
            return {"success": False, "error": str(exc), "status": self._status_for(test_name).model_dump()}
        finally:
            await self.disconnect_server(test_name)
            async with self._lock:
                self._configs.pop(test_name, None)
                if original_config:
                    self._configs[test_name] = original_config

    async def _open_session(self, config: MCPServerConfig, exit_stack: AsyncExitStack) -> Any:
        if config.transport == "stdio":
            read_stream, write_stream = await exit_stack.enter_async_context(self._stdio_client_context(config))
        elif config.transport == "http":
            read_stream, write_stream = await exit_stack.enter_async_context(self._http_client_context(config))
        else:  # pragma: no cover - validated by model
            raise ValueError(f"Unsupported MCP transport: {config.transport}")

        client_session_cls = self._load_client_session_class()
        session = await exit_stack.enter_async_context(client_session_cls(read_stream, write_stream))
        await asyncio.wait_for(
            session.initialize(),
            timeout=config.timeout_seconds or self.default_timeout_seconds,
        )
        return session

    def _stdio_client_context(self, config: MCPServerConfig):
        sdk = self._load_mcp_stdio()
        env = _filter_subprocess_env(config.env)
        params = sdk["StdioServerParameters"](
            command=config.command,
            args=config.args,
            env=env,
        )
        return sdk["stdio_client"](params)

    def _http_client_context(self, config: MCPServerConfig):
        streamable_http_client = self._load_streamable_http_client()
        if config.headers:
            http_client = httpx.AsyncClient(headers=config.headers, timeout=config.timeout_seconds or self.default_timeout_seconds)
            return _streamable_http_with_client(streamable_http_client, config.url, http_client)
        return streamable_http_client(config.url)

    def _tool_to_dict(self, server_name: str, tool: Any) -> Dict[str, Any]:
        original_name = getattr(tool, "name", "")
        description = getattr(tool, "description", "") or f"MCP tool {original_name} from {server_name}"
        input_schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {"type": "object", "properties": {}}
        runtime_name = _runtime_tool_name(server_name, original_name)
        return {
            "name": original_name,
            "server_name": server_name,
            "runtime_name": runtime_name,
            "description": f"[MCP:{server_name}] {description}",
            "input_schema": input_schema,
        }

    def _tool_result_payload(self, response: Any) -> Dict[str, Any]:
        content_items = []
        text_parts = []
        for item in getattr(response, "content", []) or []:
            serialized = self._serialize_content_item(item)
            content_items.append(serialized)
            if serialized["type"] == "text" and serialized.get("text"):
                text_parts.append(serialized["text"])
        structured_content = getattr(response, "structuredContent", None)
        is_error = bool(getattr(response, "isError", False))
        error = None
        if is_error:
            error = "\n".join(text_parts).strip() or "MCP tool returned an error"
        content = "\n".join(part for part in text_parts if part).strip()
        if not content and structured_content is not None:
            content = json.dumps(structured_content)
        return {
            "content": content,
            "content_items": content_items,
            "structured_content": structured_content,
            "is_error": is_error,
            "error": error,
        }

    def _serialize_content_item(self, item: Any) -> Dict[str, Any]:
        if hasattr(item, "model_dump"):
            data = item.model_dump()
        elif isinstance(item, dict):
            data = dict(item)
        else:
            data = {"value": str(item)}
        if hasattr(item, "text"):
            data.setdefault("type", "text")
            data.setdefault("text", getattr(item, "text"))
        return data

    def _status_for(self, name: str) -> MCPServerStatus:
        config = self._configs.get(name)
        if not config:
            raise KeyError(f"Unknown MCP server: {name}")
        connection = self._connections.get(name)
        tools = list(connection.tools.values()) if connection else []
        return MCPServerStatus(
            name=config.name,
            transport=config.transport,
            connected=bool(connection and connection.state == "connected"),
            state=connection.state if connection else "disconnected",
            enabled=config.enabled,
            auto_connect=config.auto_connect,
            tool_count=len(tools),
            tools=tools,
            error=connection.error if connection else None,
            last_checked_at=connection.last_checked_at if connection else None,
            last_connected_at=connection.last_connected_at if connection else None,
        )

    def _load_client_session_class(self):
        try:
            from mcp import ClientSession
        except ImportError as exc:  # pragma: no cover - depends on runtime environment
            raise RuntimeError("The 'mcp' package is not available in the current Python environment") from exc
        return ClientSession

    def _load_mcp_stdio(self) -> Dict[str, Any]:
        try:
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:  # pragma: no cover - depends on runtime environment
            raise RuntimeError("The 'mcp' package is not available in the current Python environment") from exc
        return {"StdioServerParameters": StdioServerParameters, "stdio_client": stdio_client}

    def _load_streamable_http_client(self):
        try:
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:  # pragma: no cover - depends on runtime environment
            raise RuntimeError("The 'mcp' package is not available in the current Python environment") from exc
        return streamable_http_client


import re


_SENSITIVE_ENV_PATTERNS = re.compile(
    r"(SECRET|TOKEN|KEY|PASSWORD|API_KEY|OPENCLAW)",
    re.IGNORECASE,
)


def _filter_subprocess_env(config_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return a safe environment dict for MCP subprocess, stripping sensitive host vars."""
    env: Dict[str, str] = {}
    for key, value in os.environ.items():
        if _SENSITIVE_ENV_PATTERNS.search(key):
            continue
        env[key] = value
    if config_env:
        env.update(config_env)
    return env


class _streamable_http_with_client:
    """Adapter to keep a custom httpx client tied to the transport context."""

    def __init__(self, streamable_http_client, url: str, http_client: httpx.AsyncClient):
        self._streamable_http_client = streamable_http_client
        self._url = url
        self._http_client = http_client
        self._stack = AsyncExitStack()

    async def __aenter__(self):
        await self._stack.enter_async_context(self._http_client)
        return await self._stack.enter_async_context(
            self._streamable_http_client(self._url, http_client=self._http_client)
        )

    async def __aexit__(self, exc_type, exc, tb):
        return await self._stack.__aexit__(exc_type, exc, tb)
