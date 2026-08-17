"""WaitingItem — work blocked on someone else (BUILD_SPEC sections 13, 54, 55).

A waiting item is the durable record of "we asked, and now we are waiting".
It outlives the conversation that created it, which is the whole point of
Phase 4: a follow-up that only exists in a chat transcript is not durable work.

Section 55 says to store continuation state in NornicDB rather than adopting a
workflow engine. That state lives here rather than in a parallel table:

  * ``next_action_at`` is section 55's ``wake_at``. One instant, one field —
    the worker reads it to find due items, and the Waiting screen reads it to
    show "Follow-up tomorrow" (section 13).
  * ``attempt_count`` is deliberately *not* ``followup_count``. A worker
    attempt that errors is not a follow-up the provider ever saw, and
    conflating them would either hide failures or fake contact.
  * ``lease_owner`` / ``lease_until`` let one worker claim an item without a
    lock service. A lease that expires is reclaimable, so a worker that dies
    mid-item does not strand it forever.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.errors import ValidationError
from lifeops.ids import new_waiting_id

#: Follow-up backoff in hours, indexed by how many follow-ups have been sent.
#: Widening intervals rather than a fixed cadence: chasing a provider hourly
#: is how a personal assistant becomes a nuisance. The last value repeats.
FOLLOWUP_BACKOFF_HOURS: tuple[int, ...] = (24, 48, 96)

DEFAULT_MAX_FOLLOWUPS = 3


class WaitingStatus(StrEnum):
    """Where a waiting item stands.

    ``ESCALATED`` means the follow-up budget is spent and a human should look;
    the item is not closed, because silently giving up on the user's behalf is
    worse than saying "this needs you".
    """

    WAITING = "waiting"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


#: Statuses the due-work worker will pick up. Resolved and cancelled items are
#: history, and history is never woken.
ACTIVE_STATUSES: frozenset[WaitingStatus] = frozenset(
    {WaitingStatus.WAITING, WaitingStatus.ESCALATED}
)


class WaitingItem(BaseModel):
    """One thing being waited on (section 54)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    subject: str
    waiting_on_entity_id: str | None = None

    waiting_since: str
    expected_by: str | None = None
    #: Section 55's ``wake_at``: when the worker should next act on this.
    next_action_at: str | None = None
    last_contact_at: str | None = None

    followup_count: int = Field(default=0, ge=0)
    max_followups: int = Field(default=DEFAULT_MAX_FOLLOWUPS, ge=0)
    status: WaitingStatus = WaitingStatus.WAITING

    #: Worker mechanics (section 55), distinct from the domain counters above.
    attempt_count: int = Field(default=0, ge=0)
    lease_owner: str | None = None
    lease_until: str | None = None

    created_by_client: str | None = None

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def followups_exhausted(self) -> bool:
        return self.followup_count >= self.max_followups

    @staticmethod
    def make_id() -> str:
        return new_waiting_id()


class WaitingDraft(BaseModel):
    """Input shape for recording a new waiting item."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=500)
    waiting_on_entity_id: str | None = None
    expected_by: str | None = None
    max_followups: int = Field(default=DEFAULT_MAX_FOLLOWUPS, ge=0, le=10)


# --- pure rules ---------------------------------------------------------------


def next_followup_at(followup_count: int, *, now: str) -> str:
    """When the next follow-up is due, given how many have already gone out.

    Returns an ISO instant computed by adding the backoff for this attempt to
    ``now``. Kept pure so both the worker and the Console preview agree.
    """
    from datetime import datetime, timedelta

    index = min(followup_count, len(FOLLOWUP_BACKOFF_HOURS) - 1)
    hours = FOLLOWUP_BACKOFF_HOURS[index]
    moment = datetime.fromisoformat(now.replace("Z", "+00:00"))
    return (moment + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def is_due(item: WaitingItem, *, now: str) -> bool:
    """Whether the worker should act on this item.

    An item held under an unexpired lease belongs to another worker and is not
    due for this one, even if its wake time has passed.
    """
    if not item.is_active or item.next_action_at is None:
        return False
    if item.lease_until is not None and item.lease_until > now:
        return False
    return item.next_action_at <= now


def record_followup(item: WaitingItem, *, now: str) -> WaitingItem:
    """Apply one follow-up, escalating when the budget is spent.

    Returns a new record rather than mutating: the same discipline the task
    state machine uses, so a caller cannot half-apply a transition.
    """
    if not item.is_active:
        raise ValidationError(
            f"waiting item {item.id} is {item.status} and takes no follow-up",
            waiting_id=item.id,
            status=str(item.status),
        )

    updated = item.model_copy(deep=True)
    updated.followup_count += 1
    updated.attempt_count += 1
    updated.last_contact_at = now
    updated.lease_owner = None
    updated.lease_until = None

    if updated.followups_exhausted:
        updated.status = WaitingStatus.ESCALATED
        updated.next_action_at = None
    else:
        updated.next_action_at = next_followup_at(updated.followup_count, now=now)
    return updated


def resolve(item: WaitingItem, *, now: str) -> WaitingItem:
    """Close a waiting item because the thing arrived."""
    updated = item.model_copy(deep=True)
    updated.status = WaitingStatus.RESOLVED
    updated.next_action_at = None
    updated.last_contact_at = now
    updated.lease_owner = None
    updated.lease_until = None
    return updated
