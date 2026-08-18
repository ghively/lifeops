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
    FakeActionRepository,
    FakeApprovalRepository,
    FakeAuditRepository,
    FakeBillRepository,
    FakeMemoryRepository,
    FakePersonRepository,
    FakePreferenceRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorldRepository,
)
from lifeops.repositories.nornic.actions import NornicActionRepository
from lifeops.repositories.nornic.approvals import NornicApprovalRepository
from lifeops.repositories.nornic.audit import NornicAuditRepository
from lifeops.repositories.nornic.bills import NornicBillRepository
from lifeops.repositories.nornic.memory import NornicMemoryRepository
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.tasks import NornicTaskRepository
from lifeops.repositories.nornic.waiting import NornicWaitingRepository
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
    (interfaces.WaitingRepository, FakeWaitingRepository, NornicWaitingRepository),
    (interfaces.ActionRepository, FakeActionRepository, NornicActionRepository),
    (interfaces.ApprovalRepository, FakeApprovalRepository, NornicApprovalRepository),
    (interfaces.AuditRepository, FakeAuditRepository, NornicAuditRepository),
    (interfaces.BillRepository, FakeBillRepository, NornicBillRepository),
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
        member for member in protocol.__protocol_attrs__ if not hasattr(impl, member)
    )


def parameters(func: Any) -> list[tuple[str, Any, Any]]:
    """A method's parameters by name, kind, and default.

    Annotations are deliberately excluded: ``from __future__ import
    annotations`` makes them strings, and two equivalent spellings of the same
    type would read as drift. Names, kinds, and defaults are what callers
    actually bind to.
    """
    return [
        (p.name, p.kind, p.default) for p in inspect.signature(func).parameters.values()
    ]


def test_every_protocol_is_paired_or_exempt() -> None:
    """A new Protocol without a fake is the Phase 3 defect, exactly."""
    covered = {protocol.__name__ for protocol, _, _ in PAIRS} | EXEMPT_PROTOCOLS
    assert set(declared_protocols()) == covered


@pytest.mark.parametrize(("protocol", "fake", "nornic"), PAIRS, ids=IDS)
def test_fake_implements_the_protocol(protocol: type, fake: type, nornic: type) -> None:
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
