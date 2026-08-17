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
            "actions.py",
            "approvals.py",
            "audit.py",
            "memory.py",
            "people.py",
            "preferences.py",
            "tasks.py",
            "waiting.py",
            "world.py",
        }
