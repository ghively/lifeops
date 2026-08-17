"""Approval — a human authorising one exact action (BUILD_SPEC 57, 58, 59).

Section 57 states the binding: an approval is tied to actor, client, action
type, recipient, amount, payload hash, and expiry, and *material change
invalidates approval*. That sentence is the whole module. Because the approval
carries the payload hash of what was shown, changing the payload afterwards
changes the hash and the approval stops matching — so "material change" is
decided by arithmetic rather than by whoever is reading the diff.

``consumed_at`` exists so an approval authorises exactly one commit. Without
it, a captured approval could be replayed against a second identical action,
which is precisely the failure idempotency is supposed to prevent.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.domain.actions import Action, authorised_scope
from lifeops.ids import new_approval_id

#: How long an approval stays usable. Long enough to walk away from the
#: screen, short enough that yesterday's yes cannot authorise today's booking.
DEFAULT_APPROVAL_TTL_MINUTES = 30


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    EXPIRED = "expired"


class Approval(BaseModel):
    """One approval decision (section 59)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    action_id: str
    #: What the human was actually shown. The binding of section 57.
    payload_hash: str

    requested_by: str
    approved_by: str | None = None
    approved_at: str | None = None
    expires_at: str
    consumed_at: str | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING

    #: The remaining section 57 bindings, kept explicit so the approval record
    #: is legible on its own rather than only via its action.
    action_type: str
    target_entity_id: str | None = None
    amount: str | None = None
    #: Section 58's two lists. Carried on the record rather than derived in an
    #: adapter, so HTTP and any future surface show the same boundary.
    authorises_action: str
    does_not_authorise: list[str] = Field(default_factory=list)

    created_at: str

    @staticmethod
    def make_id() -> str:
        return new_approval_id()


# --- pure rules ---------------------------------------------------------------


def expires_at(now: str, *, minutes: int = DEFAULT_APPROVAL_TTL_MINUTES) -> str:
    from datetime import datetime, timedelta

    moment = datetime.fromisoformat(now.replace("Z", "+00:00"))
    return (moment + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def request(action: Action, *, now: str, requested_by: str) -> Approval:
    """Open an approval bound to this action's exact payload."""
    _may, _may_not = authorised_scope(action.type)
    return Approval(
        id=Approval.make_id(),
        action_id=action.id,
        payload_hash=action.payload_hash,
        requested_by=requested_by,
        expires_at=expires_at(now),
        action_type=str(action.type),
        authorises_action=_may,
        does_not_authorise=list(_may_not),
        target_entity_id=action.target_entity_id,
        amount=_amount_of(action),
        created_at=now,
    )


def _amount_of(action: Action) -> str | None:
    """The money at stake, where the payload names any.

    Read from the payload rather than required on it, because most action
    types involve no amount and inventing a zero would read as "free" rather
    than "not applicable".
    """
    for key in ("amount", "total", "price"):
        value = action.payload.get(key)
        if value is not None:
            return str(value)
    return None


def is_usable(approval: Approval, *, now: str) -> bool:
    """Whether this approval can authorise a commit right now."""
    return (
        approval.status is ApprovalStatus.APPROVED
        and approval.consumed_at is None
        and approval.expires_at > now
    )


def authorises(approval: Approval, action: Action, *, now: str) -> bool:
    """Whether this approval authorises *this* action, unchanged.

    The payload-hash comparison is section 57's "material change invalidates
    approval": edit the appointment time after approval and the hashes differ,
    so the approval no longer authorises it.
    """
    return (
        is_usable(approval, now=now)
        and approval.action_id == action.id
        and approval.payload_hash == action.payload_hash
    )


def decide(
    approval: Approval, *, approved: bool, by: str, now: str
) -> Approval:
    """Record the human's decision."""
    updated = approval.model_copy(deep=True)
    if approval.expires_at <= now:
        updated.status = ApprovalStatus.EXPIRED
        return updated
    updated.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DECLINED
    updated.approved_by = by
    updated.approved_at = now
    return updated


def consume(approval: Approval, *, now: str) -> Approval:
    """Spend the approval so it cannot authorise a second commit."""
    updated = approval.model_copy(deep=True)
    updated.consumed_at = now
    return updated
