"""LifeOps domain models and deterministic state rules.

Domain modules define *what is true* and *what changes are legal*. They hold no
Cypher, no HTTP, and no MCP. That separation is what lets NornicDB be replaced
by swapping repository implementations (BUILD_SPEC section 81).
"""

from lifeops.domain.people import Person
from lifeops.domain.preferences import Preference, PreferenceSource
from lifeops.domain.tasks import Task, TaskPriority, TaskState, VerificationState

__all__ = [
    "Person",
    "Preference",
    "PreferenceSource",
    "Task",
    "TaskPriority",
    "TaskState",
    "VerificationState",
]
