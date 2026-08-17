"""Read enumerations out of BUILD_SPEC.md.

The spec is authoritative (AGENTS.md), so these suites treat it as data rather
than transcribing its lists into Python — a transcription is precisely what
drifts, and drifting quietly is the failure this package exists to prevent.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SPEC = REPO_ROOT / "BUILD_SPEC.md"


@lru_cache(maxsize=1)
def _spec_lines() -> tuple[str, ...]:
    return tuple(BUILD_SPEC.read_text(encoding="utf-8").splitlines())


def fenced_list(section: int) -> list[str]:
    """Entries of the first fenced block under ``# <section>. ...``.

    Blank lines are dropped so the caller gets exactly the enumeration, in the
    order the spec writes it — order is part of the contract where a phase
    claims to implement a list "in the spec's order".
    """
    lines = _spec_lines()
    heading = re.compile(rf"^# {section}\. ")
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise AssertionError(f"BUILD_SPEC.md has no section {section}")

    fence = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("```")), None
    )
    if fence is None:
        raise AssertionError(f"BUILD_SPEC.md section {section} has no fenced block")

    end = next(
        (i for i in range(fence + 1, len(lines)) if lines[i].startswith("```")), None
    )
    if end is None:
        raise AssertionError(f"BUILD_SPEC.md section {section} has an unclosed fence")

    return [line.strip() for line in lines[fence + 1 : end] if line.strip()]


def snake(camel: str) -> str:
    """``WaitingItem`` -> ``waiting_item``.

    Section 36 names types in CamelCase; the code spells the same types as
    lowercase enum values. This is the bridge between the two spellings.
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", camel).lower()


def fenced_fields(section: int) -> list[str]:
    """Field names from a ``key:``-style fenced block (sections 54, 59, 60, 62).

    The spec writes schemas as bare YAML keys with empty values; this strips
    the trailing colon so the result compares directly against model fields.
    """
    return [line.rstrip(":").strip() for line in fenced_list(section)]
