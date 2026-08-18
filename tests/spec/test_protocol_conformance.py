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
    FakeServiceRequestRepository,
    FakeShoppingRepository,
    FakeTaskRepository,
    FakeWaitingRepository,
    FakeWorkflowTemplateRepository,
    FakeWorldRepository,
)
from lifeops.repositories.nornic.actions import NornicActionRepository
from lifeops.repositories.nornic.approvals import NornicApprovalRepository
from lifeops.repositories.nornic.audit import NornicAuditRepository
from lifeops.repositories.nornic.bills import NornicBillRepository
from lifeops.repositories.nornic.memory import NornicMemoryRepository
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.service_requests import (
    NornicServiceRequestRepository,
)
from lifeops.repositories.nornic.shopping import NornicShoppingRepository
from lifeops.repositories.nornic.tasks import NornicTaskRepository
from lifeops.repositories.nornic.waiting import NornicWaitingRepository
from lifeops.repositories.nornic.workflow_templates import (
    NornicWorkflowTemplateRepository,
)
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
    (
        interfaces.ServiceRequestRepository,
        FakeServiceRequestRepository,
        NornicServiceRequestRepository,
    ),
    (
        interfaces.ShoppingRepository,
        FakeShoppingRepository,
        NornicShoppingRepository,
    ),
    (
        interfaces.WorkflowTemplateRepository,
        FakeWorkflowTemplateRepository,
        NornicWorkflowTemplateRepository,
    ),
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


#: Names every class carries that are not protocol members. Mirrors the
#: exclusion list CPython's ``typing._get_protocol_attrs`` uses.
_NON_MEMBERS = frozenset(
    {
        "__abstractmethods__",
        "__annotations__",
        "__class_getitem__",
        "__dict__",
        "__doc__",
        "__init__",
        "__module__",
        "__new__",
        "__slots__",
        "__subclasshook__",
        "__weakref__",
        "__parameters__",
        "__orig_bases__",
        "__protocol_attrs__",
        "__non_callable_proto_members__",
        "_is_protocol",
        "_is_runtime_protocol",
    }
)


def protocol_members(protocol: type) -> frozenset[str]:
    """The names a Protocol requires of an implementation.

    ``__protocol_attrs__`` says exactly that, but it is a CPython detail that
    first appeared in 3.12 — on 3.11, where this project also runs, it does
    not exist. Derive the same set from the MRO when it is absent.
    """
    attrs = getattr(protocol, "__protocol_attrs__", None)
    if attrs is not None:
        return frozenset(attrs)
    members: set[str] = set()
    for base in protocol.__mro__[:-1]:  # everything below object
        if base.__name__ in ("Protocol", "Generic"):
            continue
        members.update(getattr(base, "__annotations__", {}))
        members.update(
            name
            for name in vars(base)
            if not name.startswith("_abc_") and name not in _NON_MEMBERS
        )
    return frozenset(members)


def missing_members(impl: type, protocol: type) -> list[str]:
    """Protocol members the implementation does not provide."""
    return sorted(
        member for member in protocol_members(protocol) if not hasattr(impl, member)
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
        for member in sorted(protocol_members(protocol))
        if parameters(getattr(fake, member)) != parameters(getattr(nornic, member))
    }
    assert drift == {}
