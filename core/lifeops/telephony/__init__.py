"""Telephony provider adapters (BUILD_SPEC sections 68, 69, 88, 97).

Same shape as ``lifeops.calendar`` and ``lifeops.email``: a ``Protocol``, a
fake for tests, and a service that selects the enabled backend. Section 88's
rule applies in full here — no telephony SDK dependency is added and no
credential is ever asked for by the coding agent, so this package ships with
no working real transport, only the ``Protocol`` a real one would implement
and the fake that proves the rest of the phase against it (AGENTS.md, section
104: a fresh checkout must run with Telephony reporting "Not configured").
"""

from __future__ import annotations
