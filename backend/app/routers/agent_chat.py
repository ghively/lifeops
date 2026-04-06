"""Runtime agent chat router."""

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.middleware.auth import get_current_user
from app.middleware.rate_limit import read_rate_limit, write_rate_limit
from app.services.agent.models import MCPServerConfig
from app.services.agent.rate_limiter import AgentRateLimitExceeded
from app.services.agent.runtime import get_agent_runtime

router = APIRouter()

ALLOWED_AGENT_FILES = {"AGENT.md", "SOUL.md", "MEMORY.md", "TOOLS.md"}


class RuntimeChatRequest(BaseModel):
    agent_id: str
    message: str
    session_id: Optional[str] = None
    shared_context: Dict[str, Any] = Field(default_factory=dict)


class RuntimeFileUpdateRequest(BaseModel):
    content: str


class RuntimeAgentCreateRequest(BaseModel):
    template_id: Optional[str] = None


class ScheduleTaskRequest(BaseModel):
    agent_id: str
    name: str
    cron_expression: str
    task_type: str
    config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class MemoryCurationRequest(BaseModel):
    frequency: str = "daily"


class WebhookCreateRequest(BaseModel):
    agent_id: str
    name: str
    event_type: str
    enabled: bool = True


class CreateFromTemplateRequest(BaseModel):
    agent_id: str
    template_id: str


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
    try:
        await get_agent_runtime().check_chat_rate_limits(
            agent_id=data.agent_id,
            message=data.message,
            user_id=current_user["id"],
        )
    except AgentRateLimitExceeded as exc:
        return JSONResponse(
            status_code=429,
            content={
                "detail": exc.message,
                **exc.snapshot.model_dump(),
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )

    return StreamingResponse(
        get_agent_runtime().chat_sse(
            agent_id=data.agent_id,
            message=data.message,
            session_id=data.session_id,
            shared_context=data.shared_context,
            user_id=current_user["id"],
            skip_rate_limit_checks=True,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/cli-status")
@read_rate_limit
async def cli_status(request: Request, current_user: dict = Depends(get_current_user)):
    return {"agents": get_agent_runtime().tool_registry.cli_tool.health_check()}


@router.get("/mcp/servers")
@read_rate_limit
async def list_mcp_servers(request: Request, current_user: dict = Depends(get_current_user)):
    return {"servers": [status.model_dump() for status in await get_agent_runtime().tool_registry.mcp_manager.list_servers()]}


@router.post("/mcp/servers")
@write_rate_limit
async def create_mcp_server(
    request: Request,
    data: MCPServerCreateRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
    config = MCPServerConfig(**data.model_dump())
    status = await get_agent_runtime().tool_registry.mcp_manager.configure_server(config, persist=True)
    if config.enabled and config.auto_connect:
        try:
            status = await get_agent_runtime().tool_registry.mcp_manager.connect_server(config.name)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return status.model_dump()


@router.delete("/mcp/servers/{name}")
@write_rate_limit
async def delete_mcp_server(name: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        await get_agent_runtime().tool_registry.mcp_manager.remove_server(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True, "name": name}


@router.post("/mcp/servers/{name}/connect")
@write_rate_limit
async def connect_mcp_server(name: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        status = await get_agent_runtime().tool_registry.mcp_manager.connect_server(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return status.model_dump()


@router.post("/mcp/servers/{name}/disconnect")
@write_rate_limit
async def disconnect_mcp_server(name: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        status = await get_agent_runtime().tool_registry.mcp_manager.disconnect_server(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return status.model_dump()


@router.get("/mcp/servers/{name}/tools")
@read_rate_limit
async def list_mcp_server_tools(name: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        status = await get_agent_runtime().tool_registry.mcp_manager.get_server_status(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"server": status.model_dump(), "tools": get_agent_runtime().tool_registry.mcp_manager.list_server_tools(name)}


@router.post("/mcp/test")
@write_rate_limit
async def test_mcp_server(
    request: Request,
    data: MCPTestRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
    config = MCPServerConfig(**data.model_dump())
    result = await get_agent_runtime().tool_registry.mcp_manager.test_connection(config)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("")
@read_rate_limit
async def list_runtime_agents(request: Request, current_user: dict = Depends(get_current_user)):
    return {"agents": get_agent_runtime().list_agents()}


@router.get("/sessions")
@read_rate_limit
async def list_runtime_sessions(
    request: Request,
    agent_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    return {"sessions": await get_agent_runtime().list_sessions(agent_id)}


@router.get("/sessions/{session_id}/messages")
@read_rate_limit
async def get_runtime_session_messages(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    return {"messages": await get_agent_runtime().get_session_messages(session_id)}


@router.delete("/sessions/{session_id}")
@write_rate_limit
async def delete_runtime_session(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    await get_agent_runtime().delete_session(session_id)
    return {"deleted": True, "session_id": session_id}


@router.get("/templates")
@read_rate_limit
async def list_runtime_templates(request: Request, current_user: dict = Depends(get_current_user)):
    return {"templates": get_agent_runtime().list_templates()}


@router.post("/create-from-template")
@write_rate_limit
async def create_runtime_agent_from_template(
    request: Request,
    data: CreateFromTemplateRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
    return get_agent_runtime().create_agent(data.agent_id, template_id=data.template_id)


@router.post("/schedule")
@write_rate_limit
async def create_runtime_schedule(
    request: Request,
    data: ScheduleTaskRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
    return await get_agent_runtime().create_scheduled_task(**data.model_dump())


@router.get("/schedule")
@read_rate_limit
async def list_runtime_schedule(
    request: Request,
    agent_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    return {"tasks": await get_agent_runtime().list_scheduled_tasks(agent_id)}


@router.delete("/schedule/{task_id}")
@write_rate_limit
async def delete_runtime_schedule(task_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    await get_agent_runtime().delete_scheduled_task(task_id)
    return {"deleted": True, "id": task_id}


@router.post("/schedule/{task_id}/run")
@write_rate_limit
async def run_runtime_schedule(task_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    try:
        return await get_agent_runtime().run_scheduled_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{agent_id}/curate-memory")
@write_rate_limit
async def trigger_memory_curation(
    agent_id: str,
    request: Request,
    data: MemoryCurationRequest = Body(default=MemoryCurationRequest()),
    current_user: dict = Depends(get_current_user),
):
    return await get_agent_runtime().curate_memory(agent_id, frequency=data.frequency)


@router.post("/webhooks")
@write_rate_limit
async def create_runtime_webhook(
    request: Request,
    data: WebhookCreateRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
    return await get_agent_runtime().create_webhook(**data.model_dump())


@router.get("/webhooks")
@read_rate_limit
async def list_runtime_webhooks(
    request: Request,
    agent_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    return {"webhooks": await get_agent_runtime().list_webhooks(agent_id)}


@router.delete("/webhooks/{webhook_id}")
@write_rate_limit
async def delete_runtime_webhook(webhook_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    await get_agent_runtime().delete_webhook(webhook_id)
    return {"deleted": True, "id": webhook_id}


@router.post("/{agent_id}")
@write_rate_limit
async def create_runtime_agent(
    agent_id: str,
    request: Request,
    data: RuntimeAgentCreateRequest = Body(default=RuntimeAgentCreateRequest()),
    current_user: dict = Depends(get_current_user),
):
    return get_agent_runtime().create_agent(agent_id, template_id=data.template_id)


@router.get("/{agent_id}")
@read_rate_limit
async def get_runtime_agent(agent_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    return get_agent_runtime().get_agent(agent_id)


@router.get("/{agent_id}/usage")
@read_rate_limit
async def get_runtime_agent_usage(agent_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    return await get_agent_runtime().get_usage(agent_id, current_user["id"])


@router.get("/{agent_id}/audit")
@read_rate_limit
async def get_runtime_agent_audit(
    agent_id: str,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    return await get_agent_runtime().get_audit_log(agent_id, page=page, page_size=page_size)


@router.delete("/{agent_id}")
@write_rate_limit
async def delete_runtime_agent(agent_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    get_agent_runtime().delete_agent(agent_id)
    return {"deleted": True, "agent_id": agent_id}


@router.get("/{agent_id}/files/{name}")
@read_rate_limit
async def get_runtime_agent_file(agent_id: str, name: str, request: Request, current_user: dict = Depends(get_current_user)):
    if name not in ALLOWED_AGENT_FILES:
        raise HTTPException(status_code=404, detail="Unsupported runtime file")
    return PlainTextResponse(get_agent_runtime().get_file(agent_id, name))


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
    get_agent_runtime().update_file(agent_id, name, data.content)
    return {"updated": True, "agent_id": agent_id, "file": name}
