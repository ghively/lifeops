"""Audit — the durable answer to "why did Hermes do that?" (BUILD_SPEC 62).

Phase 0 shipped an ephemeral activity buffer that dies with the process, and
SECURITY.md recorded the absence of a real audit log as a known gap. This is
that gap closed.

The field list is section 62's verbatim, because the section exists to answer
two specific questions — *why did Hermes do that* and *which client changed
this* — and dropping a field is dropping half an answer. An audit record is
append-only by construction: there is no update operation anywhere in the
repository interface.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lifeops.ids import new_audit_id


class AuditRecord(BaseModel):
    """One recorded decision or action (section 62)."""

    model_config = ConfigDict(extra="forbid")

    id: str

    #: Who asked, and on whose behalf. `requester` is the human or system that
    #: initiated; `user` is the subject the work was done for. They differ when
    #: an agent acts for the primary user on a schedule.
    requester: str | None = None
    user: str | None = None
    client: str
    session: str | None = None

    intent: str | None = None
    tool: str | None = None
    risk: str | None = None

    approval: str | None = None
    action: str | None = None
    target: str | None = None

    result: str
    verification: str | None = None

    timestamp: str
    trace_id: str | None = None

    details: dict[str, str] = Field(default_factory=dict)

    @staticmethod
    def make_id() -> str:
        return new_audit_id()
