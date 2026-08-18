"""Canonical LifeOps entity IDs (BUILD_SPEC section 37).

Every entity receives an application-generated stable ID. External provider
identifiers are properties, never identity. Display names are never canonical
identifiers.

Two shapes exist:

  slug IDs    person_gene, provider_abc_electric
              Stable, human-meaningful, used for singleton/long-lived entities.

  ULID IDs    task_01J..., preference_01J...
              Used for entities created continuously at runtime. ULIDs sort
              lexicographically by creation time, which keeps "most recent
              first" queries cheap without a secondary index.
"""

from __future__ import annotations

import re
import unicodedata

from ulid import ULID

# Prefixes are part of the public contract: agents and the Console both parse
# them to route an opaque ID back to its entity type.
PREFIX_PERSON = "person"
PREFIX_HOUSEHOLD = "household"
PREFIX_PROVIDER = "provider"
PREFIX_ASSET = "asset"
PREFIX_PREFERENCE = "preference"
PREFIX_TASK = "task"
PREFIX_MEMORY = "memory"

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*_[a-z0-9_]+$")


def new_ulid_id(prefix: str) -> str:
    """Generate a time-sortable ID, e.g. ``task_01j5x...``."""
    return f"{prefix}_{str(ULID()).lower()}"


def slugify(value: str) -> str:
    """Reduce arbitrary text to a stable ID fragment.

    Unicode is folded to ASCII first so that "Zoë" and "Zoe" do not become two
    different canonical entities.
    """
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("_", folded.lower()).strip("_")
    if not slug:
        raise ValueError(f"cannot derive a slug from {value!r}")
    return slug


def slug_id(prefix: str, value: str) -> str:
    """Build a slug ID, e.g. ``person_gene``."""
    return f"{prefix}_{slugify(value)}"


def new_task_id() -> str:
    return new_ulid_id(PREFIX_TASK)


def new_preference_id() -> str:
    return new_ulid_id(PREFIX_PREFERENCE)


def new_memory_id() -> str:
    return new_ulid_id(PREFIX_MEMORY)


def is_valid_id(value: str) -> bool:
    return bool(_ID_PATTERN.match(value))


def entity_type_of(entity_id: str) -> str:
    """Return the prefix of a canonical ID.

    Raises ValueError rather than guessing, because silently accepting a
    malformed ID would let a caller address the wrong entity class.
    """
    if not is_valid_id(entity_id):
        raise ValueError(f"not a canonical LifeOps ID: {entity_id!r}")
    return entity_id.split("_", 1)[0]


# Phase 4 durable-work prefixes. Single-word by necessity: entity_type_of
# splits on the first underscore, so "waiting_item_01j..." would resolve to
# the prefix "waiting" anyway.
PREFIX_WAITING = "waiting"
PREFIX_ACTION = "action"
PREFIX_APPROVAL = "approval"
PREFIX_AUDIT = "audit"


def new_waiting_id() -> str:
    return new_ulid_id(PREFIX_WAITING)


def new_action_id() -> str:
    return new_ulid_id(PREFIX_ACTION)


def new_approval_id() -> str:
    return new_ulid_id(PREFIX_APPROVAL)


def new_audit_id() -> str:
    return new_ulid_id(PREFIX_AUDIT)


# Phase 7 (calendar + email) prefixes. Single-word, same constraint as above.
PREFIX_APPOINTMENT = "appointment"
PREFIX_EVENT = "event"
PREFIX_DOCUMENT = "document"


def new_appointment_id() -> str:
    return new_ulid_id(PREFIX_APPOINTMENT)


def new_event_id() -> str:
    return new_ulid_id(PREFIX_EVENT)


def new_document_id() -> str:
    return new_ulid_id(PREFIX_DOCUMENT)


# Phase 9 (browser + shopping, BUILD_SPEC section 98) prefix. Single-word,
# same constraint as the waiting/action/approval/audit prefixes above.
PREFIX_SHOPPING_LIST = "shoppinglist"


def new_shopping_list_id() -> str:
    return new_ulid_id(PREFIX_SHOPPING_LIST)


# Phase 8 (provider workflows + telephony) prefix. Single word, no
# underscore — ``entity_type_for_id`` splits on the *first* underscore, so a
# prefix spelled ``service_request`` would parse back as ``service``.
PREFIX_SERVICE_REQUEST = "servicerequest"


def new_service_request_id() -> str:
    return new_ulid_id(PREFIX_SERVICE_REQUEST)


# BUILD_SPEC section 36's Knowledge entity type: reference content the user
# authored or a Document distilled, as distinct from Memory (personal facts
# LifeOps observed) and Document (a pointer to something ingested).
PREFIX_KNOWLEDGE = "knowledge"


def new_knowledge_id() -> str:
    return new_ulid_id(PREFIX_KNOWLEDGE)
