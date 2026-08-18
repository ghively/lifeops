"""Bills and payees (BUILD_SPEC sections 72, 99).

Section 99 is emphatic about order — "Bills first. Payments last." — so this
module models what is *owed* and to *whom*, and nothing about moving money.
Paying happens through the action outbox that Phase 4 built and section 99's
gate proved, not through anything here.

Section 72's seven rules govern the phase. Five were already true before this
module existed, which is the point of having built the outbox first:

  * manual payment always requires approval — R4 in section 56, and R4 is
    never policy-relaxable;
  * amount changes invalidate approval — the approval binds to the payload
    hash, and the amount is in the payload;
  * external confirmation required — an action is EXECUTED, not VERIFIED,
    until evidence arrives;
  * idempotency mandatory — keys are derived by LifeOps, never by a model;
  * no raw "pay arbitrary recipient" tool — the action vocabulary is narrow
    and semantic, and there is no do_action.

The two this module adds are *new payee always requires approval* and
*credentials never exposed to Hermes*. The first is why ``ADD_PAYEE`` is an
R4 action rather than a plain write. The second is why a ``Payee`` carries a
reference to a secret, never a secret: account numbers live in the encrypted
secret store, and nothing on this record would be dangerous to read aloud.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lifeops.errors import ValidationError
from lifeops.ids import new_ulid_id, slug_id

PREFIX_BILL = "bill"
PREFIX_PAYEE = "payee"


class BillStatus(StrEnum):
    """Where a bill stands.

    ``DISPUTED`` exists because the alternative is a user silently paying
    something they meant to challenge. It is not a synonym for overdue.
    """

    DUE = "due"
    SCHEDULED = "scheduled"
    PAID = "paid"
    OVERDUE = "overdue"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"


#: Statuses from which a payment may still be attempted. A paid or cancelled
#: bill is history, and history is never paid again.
PAYABLE_STATUSES: frozenset[BillStatus] = frozenset(
    {BillStatus.DUE, BillStatus.SCHEDULED, BillStatus.OVERDUE}
)


class Payee(BaseModel):
    """Someone the user pays.

    Section 72: *"credentials never exposed to Hermes"*. This record carries a
    ``secret_ref`` — a key into the encrypted secret store — and never an
    account number, sort code, or card. Everything here is safe to read aloud,
    which is the test a field must pass to live on this model.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    #: The world entity this payee corresponds to, when one exists — usually a
    #: provider. Keeps "who we pay" and "who we deal with" one thing.
    provider_entity_id: str | None = None
    #: A handle into the secret store. Never the credential itself.
    secret_ref: str | None = None

    created_at: str
    #: Section 72: a payee is not usable until a human approved adding it.
    approved_at: str | None = None
    approved_by: str | None = None
    created_by_client: str | None = None

    @property
    def is_approved(self) -> bool:
        return self.approved_at is not None

    @staticmethod
    def make_id(display_name: str) -> str:
        return slug_id(PREFIX_PAYEE, display_name)


class Bill(BaseModel):
    """One thing owed (section 99: bills first)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    payee_id: str
    description: str
    #: Held as a string, not a float. Money in binary floating point is how
    #: 89.10 becomes 89.09999999999999, and this value is hashed into an
    #: approval binding where an off-by-a-cent difference must not be
    #: introduced by the representation.
    amount: str
    currency: str = "USD"

    due_at: str | None = None
    status: BillStatus = BillStatus.DUE

    #: Set once a payment action for this bill has been prepared, so a second
    #: attempt can find the first rather than starting a parallel one.
    action_id: str | None = None
    paid_at: str | None = None
    #: The provider's confirmation. A bill is not paid because LifeOps says
    #: so (section 53).
    external_reference: str | None = None

    source_document_id: str | None = None
    created_at: str
    updated_at: str
    created_by_client: str | None = None

    @property
    def is_payable(self) -> bool:
        return self.status in PAYABLE_STATUSES

    @staticmethod
    def make_id() -> str:
        return new_ulid_id(PREFIX_BILL)


class PayeeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    provider_entity_id: str | None = None
    secret_ref: str | None = None

    @field_validator("secret_ref")
    @classmethod
    def _looks_like_a_reference(cls, value: str | None) -> str | None:
        """Refuse anything that looks like the credential itself.

        A caller passing a card number here would otherwise persist it to
        NornicDB, which section 72 and SECURITY.md both forbid. Digits are the
        cheap tell, and a reference never needs to be mostly digits.
        """
        if value is None:
            return None
        digits = sum(character.isdigit() for character in value)
        if digits >= 8:
            raise ValueError(
                "secret_ref must reference a stored secret, not contain one"
            )
        return value


class BillDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payee_id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    amount: str = Field(min_length=1, max_length=40)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    due_at: str | None = None
    source_document_id: str | None = None


# --- pure rules ---------------------------------------------------------------


def validate_amount(amount: str) -> str:
    """Normalise a money string, refusing anything that is not one.

    Kept strict and textual on purpose: the amount travels into an approval's
    payload hash, so "89.10" and "89.1" must not both be accepted for the same
    bill and then differ when a human re-reads the screen.
    """
    cleaned = amount.strip()
    if not cleaned:
        raise ValidationError("an amount is required", field="amount")
    negative = cleaned.startswith("-")
    body = cleaned[1:] if negative else cleaned
    if not body.replace(".", "", 1).isdigit() or body.count(".") > 1:
        raise ValidationError(f"not a valid amount: {amount!r}", field="amount")
    if negative:
        raise ValidationError(
            "a bill amount cannot be negative; record a credit as a separate "
            "bill rather than a negative one",
            field="amount",
        )
    whole, _, fraction = body.partition(".")
    if fraction and len(fraction) != 2:
        raise ValidationError(
            f"amount {amount!r} must have exactly two decimal places",
            field="amount",
        )
    return f"{int(whole)}.{fraction or '00'}"


def may_pay(bill: Bill, payee: Payee) -> None:
    """Whether a payment may even be prepared for this bill.

    Raises rather than returning False so the reason reaches the caller: "this
    is already paid" and "this payee was never approved" need different
    responses from a human and from a model.
    """
    if not bill.is_payable:
        raise ValidationError(
            f"bill {bill.id} is {bill.status} and cannot be paid",
            field="status",
            bill_id=bill.id,
            status=str(bill.status),
        )
    if not payee.is_approved:
        raise ValidationError(
            f"payee {payee.id} has not been approved; section 72 requires a "
            "human to approve a new payee before it can be paid",
            field="payee_id",
            payee_id=payee.id,
        )
