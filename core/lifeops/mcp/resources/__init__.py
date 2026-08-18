"""MCP resources — read-oriented context (BUILD_SPEC section 48).

Reads belong to resources, not tools: an agent that needs "who am I acting
for?" or "what is on today?" should read context, not invoke an operation.
Phase 0 shipped exactly five tools and no resources by design (section 49);
Phase 1 added the first three: ``lifeops://me``, ``lifeops://today``, and
``lifeops://waiting``. This pass adds the rest of section 48's suggested set:
``lifeops://household``, ``lifeops://approvals``, ``lifeops://entity/{id}``,
``lifeops://task/{id}``, and ``lifeops://provider/{id}``.

Every resource composes existing public read operations on LifeOpsCore — no
business rules live here — and honours the same per-connection client identity
and capability manifest as the tools. Failures come back as data
(``{"ok": false, "error": "<stable_code>"}``) rather than as raised errors, so
the calling model can distinguish "not permitted" from "not found" instead of
retrying blindly.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.mcpserver import MCPServer

from lifeops.clock import Clock, now_iso
from lifeops.core import LifeOpsCore
from lifeops.domain.approvals import Approval
from lifeops.domain.preferences import Preference
from lifeops.domain.tasks import TERMINAL_STATES, Task, TaskState
from lifeops.domain.world import WorldEntityType
from lifeops.errors import LifeOpsError, NotFoundError
from lifeops.observability.logging import trace_context
from lifeops.policy import ClientIdentity

logger = logging.getLogger(__name__)


def _task_view(task: Task) -> dict[str, Any]:
    """The same task shape the ``list_tasks`` tool returns."""
    return {
        "id": task.id,
        "title": task.title,
        "state": str(task.state),
        "priority": str(task.priority),
        "due_at": task.due_at,
        "created_at": task.created_at,
        "needs_attention": task.needs_attention,
    }


def _preference_view(preference: Preference) -> dict[str, Any]:
    """The same preference shape the ``get_preferences`` tool returns."""
    return {
        "id": preference.id,
        "key": preference.key,
        "value": preference.value,
        "confidence": preference.confidence,
        "source": str(preference.source_type),
        "since": preference.valid_from,
    }


def _approval_view(approval: Approval) -> dict[str, Any]:
    """The same approval shape the Approval screen reads (section 58)."""
    return {
        "id": approval.id,
        "action_id": approval.action_id,
        "action_type": approval.action_type,
        "status": str(approval.status),
        "requested_by": approval.requested_by,
        "target_entity_id": approval.target_entity_id,
        "amount": approval.amount,
        "expires_at": approval.expires_at,
    }


def register_resources(
    server: MCPServer,
    *,
    core: LifeOpsCore,
    client: ClientIdentity,
    clock: Clock,
) -> None:
    """Attach the LifeOps read resources to ``server`` for one client identity."""

    def _fail(exc: LifeOpsError) -> dict[str, Any]:
        """Return a structured failure, as the tools do.

        Resource reads surface exceptions to the client as a generic protocol
        error, which a model cannot act on; an ``ok: false`` payload with a
        stable code is something it can reason about.
        """
        return {"ok": False, "error": exc.code, "message": exc.message, **exc.details}

    @server.resource(
        "lifeops://me",
        name="me",
        title="The primary user",
        description=(
            "Who the assistant is acting for: the primary person's identity, "
            "display name, and timezone. Read this before personalising a "
            "reply or filing work on the user's behalf."
        ),
        mime_type="application/json",
    )
    async def me() -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                person = await core.get_person(client)
                return {"ok": True, "person": person.model_dump()}
            except LifeOpsError as exc:
                return _fail(exc)

    @server.resource(
        "lifeops://today",
        name="today",
        title="Today view",
        description=(
            "What matters right now: every open task, the subset that is due "
            "or overdue, and the user's standing preferences. Read this at the "
            "start of a session instead of calling list_tasks and "
            "get_preferences separately."
        ),
        mime_type="application/json",
    )
    async def today() -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                now = now_iso(clock)
                open_states = [s for s in TaskState if s not in TERMINAL_STATES]
                tasks = await core.list_tasks(client, states=open_states)
                preferences = await core.get_preferences(client)
                # RFC 3339 UTC strings compare chronologically (lifeops.clock).
                due = [t for t in tasks if t.due_at is not None and t.due_at <= now]
                return {
                    "ok": True,
                    "as_of": now,
                    "open_tasks": [_task_view(t) for t in tasks],
                    "due_tasks": [_task_view(t) for t in due],
                    "preferences": [_preference_view(p) for p in preferences],
                }
            except LifeOpsError as exc:
                return _fail(exc)

    @server.resource(
        "lifeops://waiting",
        name="waiting",
        title="Waiting on the outside world",
        description=(
            "Tasks in WAITING_EXTERNAL with their waiting context: what was "
            "last attempted, what is being waited on, and since when. Read "
            "this when the user asks what is outstanding, or before reporting "
            "that nothing is in progress."
        ),
        mime_type="application/json",
    )
    async def waiting() -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                tasks = await core.list_tasks(client, states=[TaskState.WAITING_EXTERNAL])
                return {
                    "ok": True,
                    "waiting": [
                        {
                            **_task_view(t),
                            "current_action": t.current_action,
                            "waiting_item_id": t.waiting_item_id,
                            "verification_state": str(t.verification_state),
                            "updated_at": t.updated_at,
                        }
                        for t in tasks
                    ],
                    "total": len(tasks),
                }
            except LifeOpsError as exc:
                return _fail(exc)

    @server.resource(
        "lifeops://household",
        name="household",
        title="Household",
        description=(
            "The household entity, if one has been recorded in the world "
            "graph — members, address, and current facts. `household` is "
            "``null`` on a fresh deployment where none exists yet."
        ),
        mime_type="application/json",
    )
    async def household() -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                graph = await core.world_graph(
                    client, entity_types=[str(WorldEntityType.HOUSEHOLD)], limit=5
                )
                if not graph.nodes:
                    return {"ok": True, "household": None}
                if len(graph.nodes) > 1:
                    # More than one household is unusual but not invalid — a
                    # shared-living setup, for instance. Return candidates
                    # rather than silently picking one.
                    return {
                        "ok": True,
                        "households": [n.model_dump(mode="json") for n in graph.nodes],
                        "total": len(graph.nodes),
                    }
                detail = await core.get_entity_detail(client, entity_id=graph.nodes[0].id)
                return {"ok": True, "household": detail.entity.model_dump(mode="json")}
            except LifeOpsError as exc:
                return _fail(exc)

    @server.resource(
        "lifeops://approvals",
        name="approvals",
        title="Pending approvals",
        description=(
            "Actions currently awaiting a human decision — bookings, "
            "messages, purchases the user has not yet approved or declined. "
            "Read this before telling the user something is 'done': a "
            "PREPARE'd action is not executed until a human approves it."
        ),
        mime_type="application/json",
    )
    async def approvals() -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                pending = await core.list_pending_approvals(client, limit=50)
                return {
                    "ok": True,
                    "approvals": [_approval_view(a) for a in pending],
                    "total": len(pending),
                }
            except LifeOpsError as exc:
                return _fail(exc)

    @server.resource(
        "lifeops://entity/{entity_id}",
        name="entity",
        title="World entity",
        description=(
            "One entity's current facts, named relationships, and related "
            "tasks and memories — the same aggregate the World screen's "
            "inspector panel shows. Accepts any canonical entity id, e.g. "
            "person_gene, provider_abc_electric, asset_land_rover."
        ),
        mime_type="application/json",
    )
    async def entity(entity_id: str) -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                detail = await core.get_entity_detail(client, entity_id=entity_id)
                return {"ok": True, "entity": detail.model_dump(mode="json")}
            except LifeOpsError as exc:
                return _fail(exc)

    @server.resource(
        "lifeops://task/{task_id}",
        name="task",
        title="One task",
        description=(
            "A single task by id, in the same shape list_tasks returns. Use "
            "this to refresh one task's state rather than re-listing all of "
            "them."
        ),
        mime_type="application/json",
    )
    async def task(task_id: str) -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                found = await core.get_task(client, task_id=task_id)
                return {"ok": True, "task": _task_view(found)}
            except LifeOpsError as exc:
                return _fail(exc)

    @server.resource(
        "lifeops://provider/{provider_id}",
        name="provider",
        title="One provider",
        description=(
            "A single provider entity by its canonical id, e.g. "
            "provider_abc_electric — the same shape the get_provider tool "
            "returns for an exact id match."
        ),
        mime_type="application/json",
    )
    async def provider(provider_id: str) -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                detail = await core.get_entity_detail(client, entity_id=provider_id)
                if detail.entity.entity_type is not WorldEntityType.PROVIDER:
                    raise NotFoundError(
                        f"no such provider: {provider_id}", provider_id=provider_id
                    )
                return {"ok": True, "provider": detail.model_dump(mode="json")}
            except LifeOpsError as exc:
                return _fail(exc)
