"""Calendar provider adapters (BUILD_SPEC sections 63, 96).

Mirrors ``lifeops.voice``: a ``Protocol`` every backend implements, a fake for
tests, a real adapter, and a small service that selects and calls whichever
backend the user has enabled. Nothing here is a repository — persistence of
what the calendar produces (Appointment, CalendarEvent) is
``LifeOpsCore``'s job, not this package's.
"""

from __future__ import annotations
