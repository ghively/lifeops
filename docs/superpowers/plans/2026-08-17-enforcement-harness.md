# Enforcement Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Commit Phase 3, then build four test suites in `tests/spec/` that make AGENTS.md's existing rules mechanically enforceable before Phases 4–11 can violate them.

**Architecture:** Each suite isolates its detection logic into a pure function that takes explicit inputs, so the detector itself can be tested with a positive control (a synthetic defect it must catch) and a negative control (real code it must pass). The suites read `BUILD_SPEC.md` as data rather than transcribing it into Python, because a transcription is exactly what drifts.

**Tech Stack:** Python 3.14, pytest 8 (`asyncio_mode = "auto"`), ruff (line-length 100, `select = ["E","F","I","UP","B","SIM"]`), stdlib `ast` and `inspect` — no new dependencies.

**Spec:** [`docs/superpowers/specs/2026-08-17-lifeops-program-roadmap-design.md`](../specs/2026-08-17-lifeops-program-roadmap-design.md), sections 4 and 6.

## Global Constraints

- **No new dependencies.** AGENTS.md requires a written justification before any dependency is added. These suites use only `ast`, `inspect`, `re`, `pathlib`, and `pytest`.
- **`make lint` runs `ruff check core tests`** — every file created here must be ruff-clean at line-length 100.
- **Comments explain *why*, not *what*** (AGENTS.md). Reference `BUILD_SPEC` sections where a decision traces to one.
- **Suites needing NornicDB must skip when it is unreachable, never fail.** None of these four need it; all must run without a database.
- **Git mutations are confirmed with the user each time.** Every commit step below stops for confirmation before running.
- **`make check` = `lint test console-test console-build`.** `make test` runs bare `pytest` with `testpaths = ["tests"]`, so `tests/spec/` is collected automatically; only `test-fast` names directories explicitly and needs updating.

---

### Task 1: Commit Phase 3 and the roadmap

Phase 3 is complete and verified — 427 Python tests, 106 Console tests, `make check` green, live smoke run and cleaned up — but it sits uncommitted in the working tree. Nothing else should be built on top of an uncommitted tree.

**Files:**
- Modify: none (this task only commits existing work)

**Interfaces:**
- Consumes: nothing
- Produces: a clean working tree at `lifeops/phase-0`, with Phase 3 and the roadmap design doc committed

- [ ] **Step 1: Confirm the tree is green before committing**

Run: `make check`
Expected: `All checks passed!`, `427 passed`, `Tests  106 passed (106)`, `✓ built`

- [ ] **Step 2: Review exactly what will be committed**

Run: `git status --short && git diff --stat`
Expected: 24 modified files, plus untracked `core/lifeops/domain/world.py`, `core/lifeops/repositories/nornic/world.py`, `console/src/components/world/`, `console/src/pages/lifeops/WorldPage.tsx`, and four new test files. Confirm no stray scratch files are included.

- [ ] **Step 3: Stage and commit Phase 3 — ASK THE USER FIRST**

```bash
git add ARCHITECTURE.md CLAUDE.md DATA_MODEL.md MCP_API.md README.md TESTING.md \
        console/package.json console/package-lock.json console/src \
        core/lifeops tests
git commit -m "feat(lifeops): Phase 3 — world graph and entity inspector

- World domain per BUILD_SPEC 36-39: Household, Provider, and Asset
  alongside Person, with a bounded facts bag and canonical slug IDs
- The full section 39 relationship vocabulary, all twenty types in the
  spec's order. Section 39 bounds inventing new types; it does not
  license implementing fewer
- Preferences project into the graph as section 15 draws them
  (Gene -PREFERS-> \"After 10 AM\"), current versions only, owned by the
  preference layer and never written by the world repository
- WorldService holds only the world repository, mirroring MemoryService:
  no world write can reach tasks, preferences, approvals, or payments
- Entity inspector aggregate spanning four repositories, degrading to
  what the caller may read rather than returning 403
- Four read-only MCP tools; world writes stay on the Console because
  shaping the user's world is their act, not a model's
- Graph traversal tolerates endpoints owned by other aggregates: an
  ABOUT edge to a Task is reported as a task, never drawn as a node"
```

- [ ] **Step 4: Commit the roadmap design doc separately — ASK THE USER FIRST**

The roadmap is program planning, not Phase 3 code, so it gets its own commit.

```bash
git add docs/superpowers/specs/2026-08-17-lifeops-program-roadmap-design.md \
        docs/superpowers/plans/2026-08-17-enforcement-harness.md
git commit -m "docs: program roadmap for Phases 4-11 and the harness plan

Sequencing, per-phase gates, the section 36 entity-type ownership map,
and the enforcement harness that makes AGENTS.md self-checking."
```

- [ ] **Step 5: Verify the tree is clean**

Run: `git status --short`
Expected: empty output (or only `docs/superpowers/plans/` if this plan is not yet committed)

---

### Task 2: Spec fidelity suite

Phase 3 narrowed BUILD_SPEC section 39's twenty relationship types to four and documented the narrowing as a design principle. Sections 36 and 39 both present their lists as *Initial* and warn against **adding** to them; neither licenses implementing fewer. This task makes that mechanical.

The shared `BUILD_SPEC.md` parser lands here because this is the first suite that needs it.

**Files:**
- Create: `tests/spec/__init__.py`
- Create: `tests/spec/spec_source.py`
- Create: `tests/spec/test_spec_fidelity.py`
- Modify: `Makefile:61-62`

**Interfaces:**
- Consumes: `lifeops.domain.world.WorldEntityType`, `lifeops.domain.world.WorldRelationship`
- Produces:
  - `tests.spec.spec_source.fenced_list(section: int) -> list[str]` — entries of the first fenced block under `# <section>. `
  - `tests.spec.spec_source.snake(camel: str) -> str` — `"WaitingItem"` → `"waiting_item"`
  - `tests.spec.spec_source.REPO_ROOT: pathlib.Path`
  - `tests.spec.test_spec_fidelity.PHASE_FOR_ENTITY_TYPE: dict[str, str]`

- [ ] **Step 1: Create the test package**

Create `tests/spec/__init__.py` as an empty file, matching `tests/unit/__init__.py`.

```bash
mkdir -p tests/spec && touch tests/spec/__init__.py
```

- [ ] **Step 2: Write the BUILD_SPEC parser**

Create `tests/spec/spec_source.py`:

```python
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
```

- [ ] **Step 3: Verify the parser reads the real spec**

Run: `.venv/bin/python -c "from tests.spec.spec_source import fenced_list, snake; print(len(fenced_list(36)), len(fenced_list(39)), snake('WaitingItem'))"`
Expected: `18 20 waiting_item`

- [ ] **Step 4: Write the fidelity tests**

Create `tests/spec/test_spec_fidelity.py`:

```python
"""BUILD_SPEC enumerations must survive contact with the code.

Phase 3 implemented four of section 39's twenty relationship types and wrote
the narrowing up as a principle. Sections 36 and 39 both give their lists as
*Initial* and then warn against adding to them — a bound on invention, not
licence to implement less. These tests turn that from a judgement call into a
red build.
"""

from __future__ import annotations

from lifeops.domain.world import WorldEntityType, WorldRelationship
from tests.spec.spec_source import fenced_list, snake

#: Every section 36 canonical entity type, mapped to the phase that owns it.
#: Mirrors section 7 of the program roadmap. A type may be deferred, but only
#: out loud: "unscheduled" is a decision, a missing key is an accident.
PHASE_FOR_ENTITY_TYPE: dict[str, str] = {
    "Person": "0",
    "Preference": "0",
    "Task": "0",
    "Memory": "2",
    "Household": "3",
    "Provider": "3",
    "Asset": "3",
    "WaitingItem": "4",
    "Action": "4",
    "Approval": "4",
    "Appointment": "7",
    "Event": "7",
    "Document": "7",
    "ServiceRequest": "8",
    "ShoppingList": "9",
    "Bill": "10",
    "WorkflowTemplate": "11",
    "Knowledge": "unscheduled",
}


class TestRelationshipVocabulary:
    def test_the_whole_section_39_vocabulary_is_implemented(self) -> None:
        """All twenty types, in the spec's order."""
        assert [str(r) for r in WorldRelationship] == fenced_list(39)


class TestEntityTypes:
    def test_every_section_36_type_is_assigned_a_phase(self) -> None:
        """Nothing from the spec's list may vanish without a decision."""
        spec_types = set(fenced_list(36))
        assert set(PHASE_FOR_ENTITY_TYPE) == spec_types

    def test_the_world_graph_renders_only_section_36_types(self) -> None:
        """The graph may render a subset (section 92 scopes Phase 3), but it
        may not invent a type the world model does not define."""
        spec_types = {snake(name) for name in fenced_list(36)}
        rendered = {str(entity_type) for entity_type in WorldEntityType}
        assert rendered <= spec_types

    def test_every_rendered_type_is_owned_by_a_delivered_phase(self) -> None:
        """A type the graph draws cannot still be marked unscheduled."""
        by_snake = {snake(name): phase for name, phase in PHASE_FOR_ENTITY_TYPE.items()}
        for entity_type in WorldEntityType:
            assert by_snake[str(entity_type)] != "unscheduled"
```

- [ ] **Step 5: Run the suite**

Run: `.venv/bin/pytest tests/spec -q`
Expected: `4 passed`

- [ ] **Step 6: Prove the fidelity test actually bites**

Temporarily break it, confirm red, then restore. This verifies the guard is load-bearing rather than vacuous.

```bash
.venv/bin/python - <<'EOF'
import pathlib
p = pathlib.Path("core/lifeops/domain/world.py")
s = p.read_text()
p.write_text(s.replace('    REFERENCES = "REFERENCES"\n', ''))
EOF
.venv/bin/pytest tests/spec -q 2>&1 | tail -5
git checkout core/lifeops/domain/world.py
.venv/bin/pytest tests/spec -q
```

Expected: first run FAILS on `test_the_whole_section_39_vocabulary_is_implemented`; after `git checkout`, `4 passed`.

- [ ] **Step 7: Wire the suite into test-fast**

Modify `Makefile` lines 61-62. `make test` already collects `tests/spec` via `testpaths`; only `test-fast` names directories explicitly.

```makefile
test-fast:  ## Unit, policy, spec, and integration tests (no database)
	@$(PYTEST) tests/unit tests/policy tests/spec tests/integration -q
```

- [ ] **Step 8: Verify the wiring and lint**

Run: `make test-fast && .venv/bin/ruff check core tests`
Expected: test count rises from 358 to 362 (the four fidelity tests); `All checks passed!`

- [ ] **Step 9: Commit — ASK THE USER FIRST**

```bash
git add tests/spec Makefile
git commit -m "test(spec): pin BUILD_SPEC enumerations against the code

Section 39's twenty relationship types and section 36's eighteen entity
types are read out of the spec and compared to the code, so narrowing an
enumeration fails the build instead of passing review. Every section 36
type must be assigned a phase; deferring one is an explicit entry."
```

---

### Task 3: Protocol conformance suite

AGENTS.md step 4 of "Adding a domain entity" requires an in-memory fake. Phase 3 shipped a `WorldRepository` Protocol with no fake at all, and once written the fake diverged from the NornicDB implementation twice — first over ID validation (the fake returned `None` where the real repository raised), then over the preference projection. Both leave unit tests green and production broken.

**Files:**
- Create: `tests/spec/test_protocol_conformance.py`

**Interfaces:**
- Consumes: `lifeops.repositories.interfaces`, `lifeops.repositories.fakes`, and the five `lifeops.repositories.nornic.*` repository modules. Does **not** use `tests.spec.spec_source` — this suite reads code, not the spec.
- Produces:
  - `tests.spec.test_protocol_conformance.missing_members(impl: type, protocol: type) -> list[str]`
  - `tests.spec.test_protocol_conformance.parameters(func) -> list[tuple]`

- [ ] **Step 1: Write the conformance tests**

Create `tests/spec/test_protocol_conformance.py`:

```python
"""Every repository Protocol needs a fake, and the fake must not drift.

Two Phase 3 defects motivate this. The WorldRepository Protocol shipped with
no fake, so nothing could exercise the core without a database. Then the fake,
once written, disagreed with the NornicDB implementation twice — it returned
None where the real repository raised on a non-world ID, and it knew nothing of
the preference projection. Signature-level drift is invisible to every other
suite: the fakes stay green precisely because they are wrong in the same way
the test expects.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from lifeops.repositories import interfaces
from lifeops.repositories.fakes import (
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWorldRepository,
)
from lifeops.repositories.nornic.memory import NornicMemoryRepository
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.tasks import NornicTaskRepository
from lifeops.repositories.nornic.world import NornicWorldRepository

#: (Protocol, in-memory fake, NornicDB implementation).
PAIRS: list[tuple[type, type, type]] = [
    (interfaces.PersonRepository, FakePersonRepository, NornicPersonRepository),
    (
        interfaces.PreferenceRepository,
        FakePreferenceRepository,
        NornicPreferenceRepository,
    ),
    (interfaces.TaskRepository, FakeTaskRepository, NornicTaskRepository),
    (interfaces.MemoryRepository, FakeMemoryRepository, NornicMemoryRepository),
    (interfaces.WorldRepository, FakeWorldRepository, NornicWorldRepository),
]

#: HealthCheck is satisfied by NornicClient rather than a repository and has no
#: in-memory counterpart. Exempt by name, so adding a Protocol without a fake
#: fails rather than being silently skipped.
EXEMPT_PROTOCOLS = {"HealthCheck"}

IDS = [protocol.__name__ for protocol, _, _ in PAIRS]


def declared_protocols() -> dict[str, type]:
    """Every Protocol defined in ``interfaces`` — not merely imported into it."""
    return {
        name: obj
        for name, obj in vars(interfaces).items()
        if isinstance(obj, type)
        and getattr(obj, "_is_protocol", False)
        and obj.__module__ == interfaces.__name__
    }


def missing_members(impl: type, protocol: type) -> list[str]:
    """Protocol members the implementation does not provide."""
    return sorted(
        member
        for member in protocol.__protocol_attrs__
        if not hasattr(impl, member)
    )


def parameters(func: Any) -> list[tuple[str, Any, Any]]:
    """A method's parameters by name, kind, and default.

    Annotations are deliberately excluded: ``from __future__ import
    annotations`` makes them strings, and two equivalent spellings of the same
    type would read as drift. Names, kinds, and defaults are what callers
    actually bind to.
    """
    return [
        (p.name, p.kind, p.default)
        for p in inspect.signature(func).parameters.values()
    ]


def test_every_protocol_is_paired_or_exempt() -> None:
    """A new Protocol without a fake is the Phase 3 defect, exactly."""
    covered = {protocol.__name__ for protocol, _, _ in PAIRS} | EXEMPT_PROTOCOLS
    assert set(declared_protocols()) == covered


@pytest.mark.parametrize(("protocol", "fake", "nornic"), PAIRS, ids=IDS)
def test_fake_implements_the_protocol(
    protocol: type, fake: type, nornic: type
) -> None:
    assert missing_members(fake, protocol) == []


@pytest.mark.parametrize(("protocol", "fake", "nornic"), PAIRS, ids=IDS)
def test_nornic_implements_the_protocol(
    protocol: type, fake: type, nornic: type
) -> None:
    assert missing_members(nornic, protocol) == []


@pytest.mark.parametrize(("protocol", "fake", "nornic"), PAIRS, ids=IDS)
def test_fake_and_nornic_signatures_agree(
    protocol: type, fake: type, nornic: type
) -> None:
    """A fake that takes different arguments is a fake of something else."""
    drift = {
        member: (parameters(getattr(fake, member)), parameters(getattr(nornic, member)))
        for member in sorted(protocol.__protocol_attrs__)
        if parameters(getattr(fake, member)) != parameters(getattr(nornic, member))
    }
    assert drift == {}
```

- [ ] **Step 2: Run the suite**

Run: `.venv/bin/pytest tests/spec/test_protocol_conformance.py -q`
Expected: `16 passed` (1 pairing test + 15 parametrized)

- [ ] **Step 3: Prove the drift detector bites**

Temporarily change a fake's signature, confirm red, restore.

```bash
.venv/bin/python - <<'EOF'
import pathlib
p = pathlib.Path("core/lifeops/repositories/fakes/__init__.py")
s = p.read_text()
p.write_text(s.replace(
    "    async def list_for_entity(\n        self, entity_id: str, *, current_only: bool = True, limit: int = 50\n    ) -> list[MemoryRecord]:",
    "    async def list_for_entity(\n        self, entity_id: str, *, current_only: bool = True\n    ) -> list[MemoryRecord]:", 1))
EOF
.venv/bin/pytest tests/spec/test_protocol_conformance.py -q 2>&1 | tail -5
git checkout core/lifeops/repositories/fakes/__init__.py
.venv/bin/pytest tests/spec/test_protocol_conformance.py -q
```

Expected: first run FAILS on `test_fake_and_nornic_signatures_agree[MemoryRepository]`; after restore, `16 passed`.

- [ ] **Step 4: Lint and commit — ASK THE USER FIRST**

```bash
.venv/bin/ruff check core tests
git add tests/spec/test_protocol_conformance.py
git commit -m "test(spec): every repository Protocol needs a matching fake

Asserts each Protocol in interfaces.py has both a fake and a NornicDB
implementation, and that their method signatures agree. Phase 3 shipped a
WorldRepository with no fake, then a fake that disagreed with the real
repository twice — drift no other suite can see."
```

---

### Task 4: No-stub-cores suite

Phase 3's integration tests defined a `StubWorldCore` implementing the world surface, and its MCP tests defined a `_StubWorldCore`. Forty tests passed against a core service that had never been written; every route would have failed on its first real call. Faking a repository is correct — it is the I/O boundary. Faking the core service tests the adapter against the test author's belief about the core rather than against the core.

**Files:**
- Create: `tests/spec/test_no_stub_cores.py`

**Interfaces:**
- Consumes: `lifeops.core.LifeOpsCore`, `tests.spec.spec_source.REPO_ROOT`
- Produces:
  - `tests.spec.test_no_stub_cores.core_surface() -> set[str]`
  - `tests.spec.test_no_stub_cores.offending_classes(source: str, surface: set[str]) -> list[tuple[str, list[str]]]`
  - `tests.spec.test_no_stub_cores.OVERLAP_THRESHOLD: int`

- [ ] **Step 1: Write the detector and its tests**

Create `tests/spec/test_no_stub_cores.py`:

```python
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
            offenders = offending_classes(
                path.read_text(encoding="utf-8"), surface
            )
            if offenders:
                found[str(path.relative_to(REPO_ROOT))] = offenders
        assert found == {}
```

- [ ] **Step 2: Run the suite**

Run: `.venv/bin/pytest tests/spec/test_no_stub_cores.py -q`
Expected: `4 passed`

- [ ] **Step 3: Prove the scan bites on a real file**

Write a throwaway test file containing a stub core, confirm the scan finds it, then delete it.

```bash
cat > tests/unit/test_temp_stub_probe.py <<'EOF'
class StubWorldCore:
    async def world_graph(self, client): ...
    async def get_entity_detail(self, client, *, entity_id): ...
    async def entity_history(self, client, *, entity_id): ...
EOF
.venv/bin/pytest tests/spec/test_no_stub_cores.py -q 2>&1 | tail -5
rm tests/unit/test_temp_stub_probe.py
.venv/bin/pytest tests/spec/test_no_stub_cores.py -q
```

Expected: first run FAILS on `test_no_test_file_defines_a_stub_core` naming `tests/unit/test_temp_stub_probe.py`; after deletion, `4 passed`.

- [ ] **Step 4: Lint and commit — ASK THE USER FIRST**

```bash
.venv/bin/ruff check core tests
git add tests/spec/test_no_stub_cores.py
git commit -m "test(spec): forbid tests that fake LifeOpsCore

Faking a repository is the I/O boundary; faking the core is faking the
rules under test. Phase 3 passed forty tests against a StubWorldCore for a
service that did not exist. Detector carries its own positive and negative
controls so the repository scan cannot go vacuous."
```

---

### Task 5: Cypher coverage suite

The in-memory fakes stayed green through two genuine NornicDB defects in Phase 3: undirected pattern matches returning phantom rows, and the preference projection reading columns that do not exist on a `:Preference` node. Only `tests/persistence/` can catch that class of bug, and AGENTS.md step 7 already requires it.

Coverage is asserted by repository class name rather than by filename, because `tests/persistence/test_nornic_repositories.py` legitimately covers three repositories at once.

**Files:**
- Create: `tests/spec/test_cypher_coverage.py`

**Interfaces:**
- Consumes: `tests.spec.spec_source.REPO_ROOT`
- Produces:
  - `tests.spec.test_cypher_coverage.repository_classes(nornic_dir: Path) -> dict[str, list[str]]`
  - `tests.spec.test_cypher_coverage.uncovered(nornic_dir: Path, persistence_dir: Path) -> list[str]`

- [ ] **Step 1: Write the coverage check and its tests**

Create `tests/spec/test_cypher_coverage.py`:

```python
"""Every NornicDB repository needs a persistence test.

The fakes proved insufficient twice in Phase 3 — once for undirected Cypher
patterns returning phantom rows, once for a projection reading properties that
a :Preference node does not carry. In both cases every unit and integration
test stayed green, because a fake cannot be wrong about Cypher.

Coverage is keyed on the repository class name, not the filename:
test_nornic_repositories.py covers three repositories in one file, and
splitting it to satisfy a naming rule would be the rule serving itself.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.spec.spec_source import REPO_ROOT

NORNIC_DIR = REPO_ROOT / "core" / "lifeops" / "repositories" / "nornic"
PERSISTENCE_DIR = REPO_ROOT / "tests" / "persistence"

#: client.py is the driver, not a repository; it has no Cypher of its own to
#: cover and is exercised by every suite that reaches the database.
NOT_REPOSITORIES = {"__init__", "client"}


def repository_classes(nornic_dir: Path) -> dict[str, list[str]]:
    """Map each repository module to the ``Nornic*`` classes it defines."""
    found: dict[str, list[str]] = {}
    for module in sorted(nornic_dir.glob("*.py")):
        if module.stem in NOT_REPOSITORIES:
            continue
        tree = ast.parse(module.read_text(encoding="utf-8"))
        classes = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name.startswith("Nornic")
        ]
        if classes:
            found[module.name] = sorted(classes)
    return found


def uncovered(nornic_dir: Path, persistence_dir: Path) -> list[str]:
    """``module.py:ClassName`` for every repository no persistence test names."""
    corpus = "\n".join(
        path.read_text(encoding="utf-8") for path in persistence_dir.glob("*.py")
    )
    return [
        f"{module}:{cls}"
        for module, classes in repository_classes(nornic_dir).items()
        for cls in classes
        if cls not in corpus
    ]


class TestDetector:
    """Controls, so the repository assertion below cannot be vacuous."""

    def test_it_reports_an_untested_repository(self, tmp_path: Path) -> None:
        nornic = tmp_path / "nornic"
        persistence = tmp_path / "persistence"
        nornic.mkdir()
        persistence.mkdir()
        (nornic / "widgets.py").write_text("class NornicWidgetRepository:\n    pass\n")
        (persistence / "test_nornic_other.py").write_text("# unrelated\n")

        assert uncovered(nornic, persistence) == ["widgets.py:NornicWidgetRepository"]

    def test_it_accepts_coverage_from_a_shared_file(self, tmp_path: Path) -> None:
        """One persistence file may cover several repositories."""
        nornic = tmp_path / "nornic"
        persistence = tmp_path / "persistence"
        nornic.mkdir()
        persistence.mkdir()
        (nornic / "widgets.py").write_text("class NornicWidgetRepository:\n    pass\n")
        (nornic / "gadgets.py").write_text("class NornicGadgetRepository:\n    pass\n")
        (persistence / "test_nornic_repositories.py").write_text(
            "from x import NornicWidgetRepository, NornicGadgetRepository\n"
        )

        assert uncovered(nornic, persistence) == []

    def test_the_driver_is_not_treated_as_a_repository(self, tmp_path: Path) -> None:
        nornic = tmp_path / "nornic"
        nornic.mkdir()
        (nornic / "client.py").write_text("class NornicClient:\n    pass\n")

        assert repository_classes(nornic) == {}


class TestRepository:
    def test_every_nornic_repository_has_a_persistence_test(self) -> None:
        assert uncovered(NORNIC_DIR, PERSISTENCE_DIR) == []

    def test_the_check_is_looking_at_real_repositories(self) -> None:
        """Guards against the scan silently finding nothing to check."""
        assert set(repository_classes(NORNIC_DIR)) == {
            "memory.py",
            "people.py",
            "preferences.py",
            "tasks.py",
            "world.py",
        }
```

- [ ] **Step 2: Run the suite**

Run: `.venv/bin/pytest tests/spec/test_cypher_coverage.py -q`
Expected: `5 passed`

- [ ] **Step 3: Run the whole harness together**

Run: `.venv/bin/pytest tests/spec -q`
Expected: `29 passed` (4 fidelity + 16 conformance + 4 stub-core + 5 coverage)

- [ ] **Step 4: Lint and commit — ASK THE USER FIRST**

```bash
.venv/bin/ruff check core tests
git add tests/spec/test_cypher_coverage.py
git commit -m "test(spec): every NornicDB repository needs a persistence test

Fakes cannot be wrong about Cypher, and stayed green through two real
NornicDB defects in Phase 3. Coverage is keyed on repository class name so
a shared persistence file still counts."
```

---

### Task 6: Document the harness

The harness only holds if the next phase's author knows it exists and what it is for. AGENTS.md is the working-rules document; TESTING.md describes the suites.

**Files:**
- Modify: `TESTING.md`
- Modify: `AGENTS.md`
- Modify: `docs/superpowers/specs/2026-08-17-lifeops-program-roadmap-design.md`

**Interfaces:**
- Consumes: the four suites from Tasks 2–5
- Produces: nothing code-facing

- [ ] **Step 1: Add the suite to TESTING.md's suite table**

`TESTING.md` has a three-column table at lines 6–13 (`| Suite | Needs NornicDB | Proves |`). Insert this row after the `tests/e2e` row, keeping the column count exact:

```markdown
| `tests/spec` | no | BUILD_SPEC enumerations are implemented in full, every repository Protocol has a matching fake, no test fakes LifeOpsCore, every NornicDB repository has a persistence test |
```

- [ ] **Step 2: Add the enforcement rules to AGENTS.md**

In `AGENTS.md`, under "Testing expectations", after the existing bullet list, add:

```markdown
- Spec fidelity and structure → `tests/spec`, no database

`tests/spec` enforces rules this file already states, because stating them was
not enough — Phase 3 skipped three steps of "Adding a domain entity" and no
test noticed. It asserts that BUILD_SPEC enumerations are implemented in full,
that every repository Protocol has a fake whose signatures match the NornicDB
implementation, that no test fakes `LifeOpsCore`, and that every NornicDB
repository has a persistence test.

When a phase adds an enumeration to BUILD_SPEC — section 54's WaitingItem
fields, section 59's Approval model, section 60's Action record — pin it in
`tests/spec/test_spec_fidelity.py` before implementing it.
```

- [ ] **Step 3: Mark the harness done in the roadmap**

In the roadmap's section 6, change `**Step 1 — Build the enforcement harness** (section 4).` to note completion:

```markdown
**Step 1 — Build the enforcement harness** (section 4). *Complete: `tests/spec`,
29 tests, wired into `make test-fast`.*
```

- [ ] **Step 4: Full verification**

Run: `make check`
Expected: `All checks passed!`, `456 passed` (427 existing + 29 new), `Tests  106 passed (106)`, `✓ built`

- [ ] **Step 5: Commit — ASK THE USER FIRST**

```bash
git add TESTING.md AGENTS.md docs/superpowers/specs/2026-08-17-lifeops-program-roadmap-design.md
git commit -m "docs: describe the tests/spec enforcement harness

AGENTS.md gains the rule that new BUILD_SPEC enumerations are pinned in
tests/spec before they are implemented."
```

---

## Verification Summary

After all six tasks:

| Check | Command | Expected |
|---|---|---|
| Harness alone | `.venv/bin/pytest tests/spec -q` | 29 passed |
| Fast suite | `make test-fast` | 387 passed (358 + 29) |
| Everything CI runs | `make check` | lint clean, 456 passed, 106 Console, build ✓ |
| Tree state | `git status --short` | empty |

Each detector carries a positive control, so a suite that silently stops
checking anything fails rather than passing quietly — the failure mode that
made forty green Phase 3 tests meaningless.
