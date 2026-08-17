"""Email domain model (BUILD_SPEC sections 61, 64, 96).

Section 64's capabilities: search/read, thread read, send, reply, associate
with a task/provider/entity, create a waiting item, ingest observations. The
last three are deliberately *not* separate operations here — a message a
caller wants to keep becomes a ``Document`` (domain/documents.py) linked to a
task or entity through the existing ``REFERENCES``/``ABOUT`` edges, following
up on a message becomes an ordinary ``WaitingItem``, and noteworthy content
becomes a ``Memory``. Building parallel email-specific versions of state
LifeOps already has a durable home for would be exactly the "generic
mega-repository" AGENTS.md warns against — email produces LifeOps entities, it
does not need its own copies of them.

Sending and replying are the two writes, and both are external commitments
section 61 requires an idempotency key for — so neither is executed here.
``build_send_payload``/``build_reply_payload`` produce the ``Action`` payload
LifeOps prepares through the existing outbox (``ActionType.SEND_EMAIL``);
domain/actions.py generates the key from that payload, never from a value this
module invents.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lifeops.errors import ValidationError

_MAX_RECIPIENTS = 25


class EmailMessage(BaseModel):
    """One message, as read from the provider (section 64's search/read)."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    thread_id: str
    from_address: str
    to_addresses: list[str] = Field(default_factory=list)
    subject: str
    snippet: str = ""
    received_at: str = ""
    folder: str = ""


class EmailThread(BaseModel):
    """A message and its relatives, section 64's "thread read"."""

    model_config = ConfigDict(extra="forbid")

    thread_id: str
    subject: str
    messages: list[EmailMessage] = Field(default_factory=list)


class EmailSendDraft(BaseModel):
    """Input shape for section 64's send/reply.

    ``in_reply_to``/``thread_id`` set together mean "reply"; both absent mean
    "send new". LifeOps does not expose two wire shapes for what is, on the
    provider side, the same write with one more header.
    """

    model_config = ConfigDict(extra="forbid")

    to_addresses: list[str] = Field(min_length=1, max_length=_MAX_RECIPIENTS)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=50_000)
    thread_id: str | None = None
    in_reply_to: str | None = None
    task_id: str | None = None
    target_entity_id: str | None = None


def validate_send_draft(draft: EmailSendDraft) -> EmailSendDraft:
    """Reject an obviously malformed address rather than a full RFC 5322
    parse — LifeOps is not a mail transfer agent, and the provider will
    reject anything this does not already catch."""
    for address in draft.to_addresses:
        if "@" not in address or address.strip() != address or " " in address:
            raise ValidationError(
                f"not a usable email address: {address!r}", field="to_addresses"
            )
    if bool(draft.thread_id) != bool(draft.in_reply_to):
        raise ValidationError(
            "a reply needs both thread_id and in_reply_to, or neither",
            field="thread_id",
        )
    return draft


def build_send_payload(draft: EmailSendDraft) -> dict[str, object]:
    """The exact request LifeOps records before it goes out (section 60)."""
    validate_send_draft(draft)
    payload: dict[str, object] = {
        "to_addresses": list(draft.to_addresses),
        "subject": draft.subject,
        "body": draft.body,
    }
    if draft.thread_id:
        payload["thread_id"] = draft.thread_id
        payload["in_reply_to"] = draft.in_reply_to
    return payload
