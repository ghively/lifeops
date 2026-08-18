"""Workflow templates in NornicDB (BUILD_SPEC sections 73, 100).

Graph shape:

    (:WorkflowTemplate {id, name, description, trigger, next_run_at, enabled,
                        steps_json, created_at, updated_at, created_by_client})

``steps`` is a JSON string, because NornicDB property values cannot be maps or
lists of maps. Unlike the fact-bag blobs of Phases 7 and 9 this is the whole
record rather than a field smuggled into a shared bag, so the size bound that
protects entity facts does not apply — and a template is capped at 40 steps in
the domain, which is the real limit.

``coalesce`` appears nowhere in a SET clause here: on NornicDB it persists its
own expression text when the parameter is null (see CLAUDE.md).
"""

from __future__ import annotations

import json
from typing import Any

from lifeops.domain.workflow_templates import TriggerKind, WorkflowStep, WorkflowTemplate
from lifeops.repositories.nornic.client import NornicClient

_RETURN = """
    t.id AS id,
    t.name AS name,
    t.description AS description,
    t.steps_json AS steps_json,
    t.trigger AS trigger,
    t.next_run_at AS next_run_at,
    t.enabled AS enabled,
    t.created_at AS created_at,
    t.updated_at AS updated_at,
    t.created_by_client AS created_by_client
"""


def _row_to_template(row: dict[str, Any]) -> WorkflowTemplate:
    raw = row.get("steps_json")
    steps = [WorkflowStep(**step) for step in (json.loads(raw) if raw else [])]
    return WorkflowTemplate(
        id=row["id"],
        name=row["name"],
        description=row.get("description"),
        steps=steps,
        trigger=TriggerKind(row.get("trigger") or "manual"),
        next_run_at=row.get("next_run_at"),
        enabled=bool(row.get("enabled", True)),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        created_by_client=row.get("created_by_client"),
    )


class NornicWorkflowTemplateRepository:
    def __init__(self, client: NornicClient) -> None:
        self._client = client

    async def get(self, template_id: str) -> WorkflowTemplate | None:
        rows = await self._client.read(
            f"MATCH (t:WorkflowTemplate {{id: $id}}) RETURN {_RETURN}", id=template_id
        )
        return _row_to_template(rows[0]) if rows else None

    async def list_templates(self, *, limit: int = 100) -> list[WorkflowTemplate]:
        rows = await self._client.read(
            f"MATCH (t:WorkflowTemplate) RETURN {_RETURN} ORDER BY t.name ASC LIMIT $limit",
            limit=limit,
        )
        return [_row_to_template(r) for r in rows]

    async def list_due(self, *, now: str, limit: int = 50) -> list[WorkflowTemplate]:
        rows = await self._client.read(
            f"""
            MATCH (t:WorkflowTemplate)
            WHERE t.enabled = true
              AND t.next_run_at IS NOT NULL
              AND t.next_run_at <= $now
            RETURN {_RETURN}
            ORDER BY t.next_run_at ASC, t.id ASC
            LIMIT $limit
            """,
            now=now,
            limit=limit,
        )
        return [_row_to_template(r) for r in rows]

    async def upsert(self, template: WorkflowTemplate) -> WorkflowTemplate:
        await self._client.write(
            """
            MERGE (t:WorkflowTemplate {id: $id})
            SET t.name = $name,
                t.description = $description,
                t.steps_json = $steps_json,
                t.trigger = $trigger,
                t.next_run_at = $next_run_at,
                t.enabled = $enabled,
                t.created_at = $created_at,
                t.updated_at = $updated_at,
                t.created_by_client = $created_by_client
            """,
            id=template.id,
            name=template.name,
            description=template.description,
            steps_json=json.dumps([s.model_dump() for s in template.steps]),
            trigger=str(template.trigger),
            next_run_at=template.next_run_at,
            enabled=template.enabled,
            created_at=template.created_at,
            updated_at=template.updated_at,
            created_by_client=template.created_by_client,
        )
        stored = await self.get(template.id)
        return stored or template

    async def delete(self, template_id: str) -> bool:
        rows = await self._client.write(
            "MATCH (t:WorkflowTemplate {id: $id}) DETACH DELETE t "
            "RETURN count(t) AS removed",
            id=template_id,
        )
        return bool(rows and rows[0]["removed"])
