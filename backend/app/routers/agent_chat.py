"""Runtime agent chat router."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.services.agent.models import MCPServerConfig
from app.services.agent.runtime import agent_runtime

router = APIRouter()

ALLOWED_AGENT_FILES = {"AGENT.md", "SOUL.md", "MEMORY.md", "TOOLS.md"}


class RuntimeChatRequest(BaseModel):
    agent_id: str
    message: str
    session_id: Optional[str] = None


class RuntimeFileUpdateRequest(BaseModel):
    content: str


class MCPServerCreateRequest(BaseModel):
    name: str
    transport: str
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 30
    enabled: bool = True
    auto_connect: bool = True


class MCPTestRequest(MCPServerCreateRequest):
    pass


@router.post("/chat")
@write_rate_limit
async def runtime_chat(
    request: Request,
    data: RuntimeChatRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
    return StreamingResponse(
        agent_runtime.chat_sse(agent_id=data.agent_id, message=data.message, session_id=data.session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/cli-status")
@read_rate_limit
async def cli_status(request: Request, current_user: dict = Depends(get_current_user)):
    return {"agents": agent_runtime.tool_registry.cli_tool.health_check()}


@router.get("/mcp/servers")
@read_rate_limit
async def list_mcp_servers(request: Request, current_user: dict = Depends(get_current_user)):
    return {"servers": [status.model_dump() for status in await agent_runtime.tool_registry.mcp_manager.list_servers()]}


@router.post("/mcp/servers")
@write_rate_limit
async def create_mcp_server(
    request: Request,
    data: MCPServerCreateRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
    config = MCPServerConfig(**data.model_dump())
    status = await agent_runtime.tool_registry.mcp_manager.configure_server(config, persist=True)
    if config.enabled and config.auto_connect:
        try:
            status = await agent_runtime.tool_registry.mcp_manager.connect_server(config.name)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return status.model_dump()


@router.delete("/mcp/servers/{name}")
@write_rate_limit
async def delete_mcp_server(name: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        await agent_runtime.tool_registry.mcp_manager.remove_server(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "name": name}


@router.post("/mcp/servers/{name}/connect")
@write_rate_limit
async def connect_mcp_server(name: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        status = await agent_runtime.tool_registry.mcp_manager.connect_server(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return status.model_dump()


@router.post("/mcp/servers/{name}/disconnect")
@write_rate_limit
async def disconnect_mcp_server(name: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        status = await agent_runtime.tool_registry.mcp_manager.disconnect_server(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return status.model_dump()


@router.get("/mcp/servers/{name}/tools")
@read_rate_limit
async def list_mcp_server_tools(name: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        status = await agent_runtime.tool_registry.mcp_manager.get_server_status(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"server": status.model_dump(), "tools": agent_runtime.tool_registry.mcp_manager.list_server_tools(name)}


@router.post("/mcp/test")
@write_rate_limit
async def test_mcp_server(
    request: Request,
    data: MCPTestRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
    config = MCPServerConfig(**data.model_dump())
    result = await agent_runtime.tool_registry.mcp_manager.test_connection(config)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("")
@read_rate_limit
async def list_runtime_agents(request: Request, current_user: dict = Depends(get_current_user)):
    return {"agents": agent_runtime.list_agents()}


@router.get("/sessions")
@read_rate_limit
async def list_runtime_sessions(
    request: Request,
    agent_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    return {"sessions": await agent_runtime.list_sessions(agent_id)}


@router.get("/sessions/{session_id}/messages")
@read_rate_limit
async def get_runtime_session_messages(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    return {"messages": await agent_runtime.get_session_messages(session_id)}


@router.delete("/sessions/{session_id}")
@write_rate_limit
async def delete_runtime_session(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    await agent_runtime.delete_session(session_id)
    return {"deleted": True, "session_id": session_id}


@router.post("/{agent_id}")
@write_rate_limit
async def create_runtime_agent(agent_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    return agent_runtime.create_agent(agent_id)


@router.get("/{agent_id}")
@read_rate_limit
async def get_runtime_agent(agent_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    return agent_runtime.get_agent(agent_id)


@router.delete("/{agent_id}")
@write_rate_limit
async def delete_runtime_agent(agent_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    agent_runtime.delete_agent(agent_id)
    return {"deleted": True, "agent_id": agent_id}


@router.get("/{agent_id}/files/{name}")
@read_rate_limit
async def get_runtime_agent_file(agent_id: str, name: str, request: Request, current_user: dict = Depends(get_current_user)):
    if name not in ALLOWED_AGENT_FILES:
        raise HTTPException(status_code=404, detail="Unsupported runtime file")
    return PlainTextResponse(agent_runtime.get_file(agent_id, name))


@router.put("/{agent_id}/files/{name}")
@write_rate_limit
async def update_runtime_agent_file(
    agent_id: str,
    name: str,
    request: Request,
    data: RuntimeFileUpdateRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
    if name not in ALLOWED_AGENT_FILES:
        raise HTTPException(status_code=404, detail="Unsupported runtime file")
    agent_runtime.update_file(agent_id, name, data.content)
    return {"updated": True, "agent_id": agent_id, "file": name}
