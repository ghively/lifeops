"""LifeOps MCP server.

The portable agent interface. Hermes is the primary consumer; Claude Code,
ChatGPT-compatible clients, and future agents connect to the same server and
operate on the same personal world state, subject to their own permissions
(BUILD_SPEC sections 1 and 34).

Tools are narrow and semantic. There is no ``run_cypher``, no ``create_node``,
and no ``do_action``: a raw graph write cannot carry authorization, state
validity, approval, idempotency, or verification, and LifeOps can (section 7).

Phase 0 exposed exactly five tools and nothing more (section 49). Phase 1
adds read-only resources — ``lifeops://me``, ``lifeops://today``,
``lifeops://waiting`` — because read-oriented context belongs to resources,
not tools (section 48).

Client identity
---------------
Identity is declared per *connection*, not per call, because a tool argument
is model-controlled and would let an agent name itself Hermes. Over stdio each
client gets its own launch entry with ``--client``; over HTTP the identity
comes from the ``X-LifeOps-Client`` header.
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from lifeops.container import Container
from lifeops.domain.preferences import PreferenceDraft, PreferenceSource
from lifeops.domain.tasks import TaskDraft, TaskPriority, TaskState
from lifeops.errors import LifeOpsError
from lifeops.mcp.resources import register_resources
from lifeops.observability.logging import configure_logging, trace_context
from lifeops.policy import ClientIdentity, UnknownClientPolicy, resolve_client
from lifeops.settings import get_settings

logger = logging.getLogger(__name__)

INSTRUCTIONS = """\
LifeOps is the user's personal operating layer. It owns their durable world
state: people, preferences, and tasks.

Use it whenever the user states a lasting preference, asks what they prefer, or
asks about work that should outlive this conversation. State recorded here is
visible to every LifeOps client, including the user's Console, so prefer it
over remembering things only in context.

Preferences are temporal. Saving a key that already exists supersedes the old
value and keeps the history; nothing is overwritten.

Tasks move through a validated state machine. Creating one captures it; it does
not execute anything.
"""


def build_server(container: Container, client: ClientIdentity) -> MCPServer:
    """Construct the MCP server bound to one client identity."""

    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[None]:
        await container.startup()
        try:
            yield
        finally:
            await container.shutdown()

    server = MCPServer(
        name="lifeops",
        title="LifeOps",
        version="0.1.0",
        instructions=INSTRUCTIONS,
        lifespan=lifespan,
    )

    def _fail(exc: LifeOpsError) -> dict[str, Any]:
        """Return a structured failure.

        Errors come back as data rather than as an exception string so the
        calling model can distinguish "you may not do that" from "that does
        not exist" and react appropriately instead of retrying blindly.
        """
        return {"ok": False, "error": exc.code, "message": exc.message, **exc.details}

    # --- reads --------------------------------------------------------------

    @server.tool(
        name="get_person",
        title="Get person",
        description=(
            "Look up a person in the user's world. Call with no arguments to "
            "get the primary user — who the assistant is acting for."
        ),
    )
    async def get_person(
        person_id: Annotated[
            str | None,
            Field(description="Canonical LifeOps person ID, e.g. person_gene."),
        ] = None,
        name: Annotated[
            str | None,
            Field(description="Search by display name or alias instead of ID."),
        ] = None,
    ) -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                if name:
                    people = await container.core.find_people(client, name=name)
                    return {
                        "ok": True,
                        "people": [p.model_dump() for p in people],
                        "total": len(people),
                    }
                person = await container.core.get_person(client, person_id=person_id)
                return {"ok": True, "person": person.model_dump()}
            except LifeOpsError as exc:
                return _fail(exc)

    @server.tool(
        name="get_preferences",
        title="Get preferences",
        description=(
            "List the user's current preferences. Consult this before making "
            "any scheduling, purchasing, or contact decision on their behalf. "
            "Returns only preferences that are still in effect."
        ),
    )
    async def get_preferences(
        subject_id: Annotated[
            str | None,
            Field(description="Whose preferences. Defaults to the primary user."),
        ] = None,
        key_prefix: Annotated[
            str | None,
            Field(
                description=(
                    "Filter by key prefix, e.g. 'scheduling' returns "
                    "scheduling.earliest_appointment_time and its siblings."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                prefs = await container.core.get_preferences(
                    client, subject_id=subject_id, key_prefix=key_prefix
                )
                return {
                    "ok": True,
                    "preferences": [
                        {
                            "id": p.id,
                            "key": p.key,
                            "value": p.value,
                            "confidence": p.confidence,
                            "source": str(p.source_type),
                            "since": p.valid_from,
                        }
                        for p in prefs
                    ],
                    "total": len(prefs),
                }
            except LifeOpsError as exc:
                return _fail(exc)

    @server.tool(
        name="list_tasks",
        title="List tasks",
        description=(
            "List the user's durable tasks. These survive conversations and "
            "restarts, and are shared with every other LifeOps client."
        ),
    )
    async def list_tasks(
        state: Annotated[
            list[TaskState] | None,
            Field(description="Filter to these states. Omit for all tasks."),
        ] = None,
        owner_entity_id: Annotated[
            str | None, Field(description="Filter to tasks owned by this person.")
        ] = None,
        limit: Annotated[int, Field(ge=1, le=200, description="Maximum results.")] = 50,
    ) -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                tasks = await container.core.list_tasks(
                    client, states=state, owner_entity_id=owner_entity_id, limit=limit
                )
                return {
                    "ok": True,
                    "tasks": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "state": str(t.state),
                            "priority": str(t.priority),
                            "due_at": t.due_at,
                            "created_at": t.created_at,
                            "needs_attention": t.needs_attention,
                        }
                        for t in tasks
                    ],
                    "total": len(tasks),
                }
            except LifeOpsError as exc:
                return _fail(exc)

    # --- writes -------------------------------------------------------------

    @server.tool(
        name="save_preference",
        title="Save preference",
        description=(
            "Record a lasting preference. Use this when the user states how "
            "they want things done ('nothing before ten', 'always the same "
            "mechanic'), not for one-off instructions about the current task.\n\n"
            "Saving a key that already exists supersedes the previous value and "
            "preserves its history. Set source_type to user_explicit only when "
            "the user actually said it; use user_inferred when you are guessing."
        ),
    )
    async def save_preference(
        key: Annotated[
            str,
            Field(
                description=(
                    "Stable dotted topic key, e.g. "
                    "scheduling.earliest_appointment_time. Reuse an existing "
                    "key when updating a preference."
                )
            ),
        ],
        value: Annotated[
            str, Field(description="The preference, in the user's own terms.")
        ],
        subject_id: Annotated[
            str | None, Field(description="Whose preference. Defaults to the primary user.")
        ] = None,
        source_type: Annotated[
            PreferenceSource,
            Field(description="Where this came from. Governs whether it may "
                  "supersede an existing value."),
        ] = PreferenceSource.USER_EXPLICIT,
        confidence: Annotated[
            float, Field(ge=0.0, le=1.0, description="Certainty, 0 to 1.")
        ] = 1.0,
        notes: Annotated[str | None, Field(description="Optional context.")] = None,
    ) -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                pref = await container.core.save_preference(
                    client,
                    PreferenceDraft(
                        key=key,
                        value=value,
                        subject_id=subject_id,
                        source_type=source_type,
                        confidence=confidence,
                        notes=notes,
                    ),
                )
                return {
                    "ok": True,
                    "preference": {
                        "id": pref.id,
                        "key": pref.key,
                        "value": pref.value,
                        "since": pref.valid_from,
                        "supersedes": pref.supersedes,
                    },
                }
            except LifeOpsError as exc:
                return _fail(exc)

    @server.tool(
        name="create_task",
        title="Create task",
        description=(
            "Capture a durable task. It persists across conversations and is "
            "visible in the user's Console and to other clients.\n\n"
            "This records intent only; it executes nothing. Set "
            "verification_required when completion will depend on an outside "
            "party confirming it, so the task cannot be closed on assertion alone."
        ),
    )
    async def create_task(
        title: Annotated[str, Field(description="Short imperative summary.")],
        description: Annotated[
            str | None, Field(description="Detail worth keeping.")
        ] = None,
        priority: Annotated[TaskPriority, Field(description="Priority.")] = TaskPriority.MEDIUM,
        due_at: Annotated[
            str | None, Field(description="RFC 3339 timestamp, e.g. 2026-08-20T17:00:00Z.")
        ] = None,
        owner_entity_id: Annotated[
            str | None, Field(description="Owning person. Defaults to the primary user.")
        ] = None,
        verification_required: Annotated[
            bool,
            Field(
                description=(
                    "True when an external system must confirm completion "
                    "(a booking, an order, a payment)."
                )
            ),
        ] = False,
    ) -> dict[str, Any]:
        with trace_context(client_id=client.client_id):
            try:
                task = await container.core.create_task(
                    client,
                    TaskDraft(
                        title=title,
                        description=description,
                        priority=priority,
                        due_at=due_at,
                        owner_entity_id=owner_entity_id,
                        verification_required=verification_required,
                        source=f"mcp:{client.client_id}",
                    ),
                )
                return {
                    "ok": True,
                    "task": {
                        "id": task.id,
                        "title": task.title,
                        "state": str(task.state),
                        "priority": str(task.priority),
                        "due_at": task.due_at,
                    },
                }
            except LifeOpsError as exc:
                return _fail(exc)

    register_resources(server, core=container.core, client=client, clock=container.clock)

    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="lifeops-mcp", description="LifeOps MCP server"
    )
    parser.add_argument(
        "--client",
        default=os.environ.get("LIFEOPS_MCP_CLIENT_ID"),
        help=(
            "Client identity for this connection, e.g. hermes-personal or "
            "claude-code. Determines which capabilities the connection holds."
        ),
    )
    parser.add_argument(
        "--transport",
        default=os.environ.get("LIFEOPS_MCP_TRANSPORT", "stdio"),
        choices=("stdio", "sse", "streamable-http"),
    )
    parser.add_argument("--host", default=os.environ.get("LIFEOPS_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("LIFEOPS_MCP_PORT", "8081"))
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    # stdio carries the protocol on stdout, so logs must go to stderr and
    # nowhere else. configure_logging already targets stderr.
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    # An unrecognised client is refused rather than quietly downgraded: a
    # typo in a launch config should be visible, not silently reduce access.
    client = resolve_client(args.client, unknown=UnknownClientPolicy.DENY)
    logger.info(
        "starting LifeOps MCP server",
        extra={"client_id": client.client_id, "transport": args.transport},
    )

    container = Container(settings)
    server = build_server(container, client)

    transport: Literal["stdio", "sse", "streamable-http"] = args.transport
    if transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport=transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
