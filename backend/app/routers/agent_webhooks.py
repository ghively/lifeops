"""Incoming webhook router for runtime agents."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from app.services.agent.runtime import agent_runtime

router = APIRouter()


@router.post("/incoming/{hook_id}")
async def receive_runtime_webhook(
    hook_id: str,
    request: Request,
    x_knowledgeos_signature: str = Header(default="", alias="X-KnowledgeOS-Signature"),
    x_knowledgeos_event: str | None = Header(default=None, alias="X-KnowledgeOS-Event"),
):
    body = await request.body()
    try:
        return await agent_runtime.handle_incoming_webhook(
            hook_id=hook_id,
            body=body,
            signature=x_knowledgeos_signature,
            event_type=x_knowledgeos_event,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
