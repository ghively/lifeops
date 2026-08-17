"""Tests may fake repositories. They may not fake LifeOpsCore.

Phase 3 shipped forty passing tests against a StubWorldCore that implemented
the world surface the real core had never been given. The adapters called
methods that did not exist; nothing failed until the stack was actually run.
A repository fake stands in for I/O, which is a boundary worth faking. A core
fake stands in for the rules under test, which is the thing being tested.

Phase 2 got this right — its MCP tests build a real LifeOpsCore over fakes —
so this suite pins the line that already held once.
"""

from __future__ import annotations

import ast
import inspect

from lifeops.core import LifeOpsCore
from tests.spec.spec_source import REPO_ROOT

#: How many LifeOpsCore methods a test class may share before it is a stub core
#: rather than a coincidence. A container double legitimately defines `startup`
#: and `shutdown`; none of those are core operations, so real doubles score 0.
OVERLAP_THRESHOLD = 3


def core_surface() -> set[str]:
    """LifeOpsCore's public async operations."""
    return {
        name
        for name, _ in inspect.getmembers(LifeOpsCore, inspect.iscoroutinefunction)
        if not name.startswith("_")
    }


def offending_classes(source: str, surface: set[str]) -> list[tuple[str, list[str]]]:
    """Classes in ``source`` that reimplement too much of the core surface."""
    offenders: list[tuple[str, list[str]]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef):
            continue
        methods = {
            child.name
            for child in node.body
            if isinstance(child, ast.AsyncFunctionDef | ast.FunctionDef)
        }
        overlap = methods & surface
        if len(overlap) >= OVERLAP_THRESHOLD:
            offenders.append((node.name, sorted(overlap)))
    return offenders


class TestDetector:
    """Positive and negative controls, so the scan below cannot be vacuous."""

    def test_it_catches_a_stub_core(self) -> None:
        source = """
class StubWorldCore:
    async def world_graph(self, client): ...
    async def get_entity_detail(self, client, *, entity_id): ...
    async def entity_history(self, client, *, entity_id): ...
"""
        assert offending_classes(source, core_surface()) == [
            ("StubWorldCore", ["entity_history", "get_entity_detail", "world_graph"])
        ]

    def test_it_leaves_a_container_double_alone(self) -> None:
        """Faking the Container is fine — it carries the core, it is not one."""
        source = """
class StubContainer:
    def __init__(self, core, clock): ...
    async def startup(self): ...
    async def shutdown(self): ...
    async def health(self): ...
"""
        assert offending_classes(source, core_surface()) == []

    def test_it_leaves_a_repository_fake_alone(self) -> None:
        """Repositories are the I/O boundary; faking them is the point."""
        source = """
class FakeThingRepository:
    async def get(self, thing_id): ...
    async def create(self, thing): ...
    async def list_all(self): ...
"""
        assert offending_classes(source, core_surface()) == []


class TestRepository:
    def test_no_test_file_defines_a_stub_core(self) -> None:
        surface = core_surface()
        found: dict[str, list[tuple[str, list[str]]]] = {}
        for path in sorted((REPO_ROOT / "tests").rglob("*.py")):
            offenders = offending_classes(path.read_text(encoding="utf-8"), surface)
            if offenders:
                found[str(path.relative_to(REPO_ROOT))] = offenders
        assert found == {}
