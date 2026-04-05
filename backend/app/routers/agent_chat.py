"""Runtime agent chat router."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.services.agent.runtime import agent_runtime

router = APIRouter()

ALLOWED_AGENT_FILES = {"AGENT.md", "SOUL.md", "MEMORY.md", "TOOLS.md"}


class RuntimeChatRequest(BaseModel):
    agent_id: str
    message: str
    session_id: Optional[str] = None


class RuntimeFileUpdateRequest(BaseModel):
    content: str


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


@router.get("")
@read_rate_limit
async def list_runtime_agents(request: Request, current_user: dict = Depends(get_current_user)):
    return {"agents": agent_runtime.list_agents()}


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
