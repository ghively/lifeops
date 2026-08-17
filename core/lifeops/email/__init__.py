"""Email provider adapters (BUILD_SPEC sections 61, 64, 96).

Same shape as ``lifeops.calendar`` and ``lifeops.voice``: a ``Protocol``, a
fake for tests, a real adapter, and a service that selects the enabled
backend. Persisting anything email produces (a Document, a WaitingItem, a
Memory) is ``LifeOpsCore``'s job — this package only talks to the mail server.
"""

from __future__ import annotations
