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
