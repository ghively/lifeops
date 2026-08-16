"""NornicDB-backed repository implementations."""

from lifeops.repositories.nornic.client import NornicClient
from lifeops.repositories.nornic.people import NornicPersonRepository
from lifeops.repositories.nornic.preferences import NornicPreferenceRepository
from lifeops.repositories.nornic.tasks import NornicTaskRepository

__all__ = [
    "NornicClient",
    "NornicPersonRepository",
    "NornicPreferenceRepository",
    "NornicTaskRepository",
]
