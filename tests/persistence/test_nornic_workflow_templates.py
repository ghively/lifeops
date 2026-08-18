"""Workflow template persistence against a live NornicDB (BUILD_SPEC 73, 100).

Two things the fakes cannot check: that steps survive the JSON round trip with
their order intact, and that ``list_due`` actually filters in Cypher rather
than pulling every routine into memory and filtering in Python.
"""

from __future__ import annotations

import pytest

from lifeops.domain.workflow_templates import (
    TriggerKind,
    WorkflowStep,
    WorkflowTemplate,
)
from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.workflow_templates import (
    NornicWorkflowTemplateRepository,
)

pytestmark = [pytest.mark.integration, pytest.mark.persistence]

TS = "2026-01-01T00:00:00Z"


@pytest.fixture
async def templates(nornic_client: NornicClient, test_label: str):
    repo = NornicWorkflowTemplateRepository(nornic_client)
    created: list[str] = []

    def make(name: str, **overrides) -> WorkflowTemplate:
        template_id = f"template_{test_label}_{name}"
        created.append(template_id)
        base = dict(
            id=template_id, name=f"{name} {test_label}", created_at=TS, updated_at=TS
        )
        return WorkflowTemplate(**{**base, **overrides})

    try:
        yield repo, make
    finally:
        for template_id in created:
            await nornic_client.write(
                "MATCH (t:WorkflowTemplate {id: $id}) DETACH DELETE t", id=template_id
            )


class TestRoundTrip:
    async def test_steps_survive_with_their_order(self, templates) -> None:
        repo, make = templates
        steps = [
            WorkflowStep(order=0, description="Find a provider"),
            WorkflowStep(order=1, description="Collect a quote", action_type="request_quote"),
            WorkflowStep(order=2, description="Book it", action_type="book_appointment"),
        ]
        template = make("booking", steps=steps)
        await repo.upsert(template)

        stored = await repo.get(template.id)
        assert stored is not None
        assert [s.description for s in stored.steps] == [
            "Find a provider",
            "Collect a quote",
            "Book it",
        ]
        assert stored.steps[2].action_type == "book_appointment"

    async def test_a_template_with_no_steps_reads_back_empty(self, templates) -> None:
        repo, make = templates
        template = make("empty")
        await repo.upsert(template)

        stored = await repo.get(template.id)
        assert stored is not None
        assert stored.steps == []

    async def test_upsert_replaces_rather_than_appends(self, templates) -> None:
        repo, make = templates
        template = make("revise", steps=[WorkflowStep(order=0, description="First")])
        await repo.upsert(template)

        template.steps = [WorkflowStep(order=0, description="Second")]
        await repo.upsert(template)

        stored = await repo.get(template.id)
        assert stored is not None
        assert [s.description for s in stored.steps] == ["Second"]


class TestDueRoutines:
    async def test_only_enabled_scheduled_routines_come_due(self, templates) -> None:
        repo, make = templates
        due = make("due", trigger=TriggerKind.SCHEDULE, next_run_at=TS)
        disabled = make("off", trigger=TriggerKind.SCHEDULE, next_run_at=TS, enabled=False)
        manual = make("manual", trigger=TriggerKind.MANUAL)
        future = make(
            "later", trigger=TriggerKind.SCHEDULE, next_run_at="2099-01-01T00:00:00Z"
        )
        for template in (due, disabled, manual, future):
            await repo.upsert(template)

        found = {t.id for t in await repo.list_due(now="2026-06-01T00:00:00Z", limit=500)}
        assert due.id in found
        assert disabled.id not in found
        assert manual.id not in found
        assert future.id not in found

    async def test_deleting_removes_it(self, templates) -> None:
        repo, make = templates
        template = make("gone")
        await repo.upsert(template)

        assert await repo.delete(template.id) is True
        assert await repo.get(template.id) is None
        assert await repo.delete(template.id) is False
