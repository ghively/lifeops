"""Detection of optional local runtimes (BUILD_SPEC sections 30, 66).

Local voice and browser adapters depend on packages LifeOps deliberately does
not install (section 105: no dependency without a concrete problem); they
report honestly whether a usable runtime is present instead of failing deep
inside an import.
"""

from __future__ import annotations

import importlib.util


def detect_runtime(candidates: tuple[str, ...]) -> str | None:
    """The first candidate module that is actually importable, if any."""
    for name in candidates:
        try:
            if importlib.util.find_spec(name) is not None:
                return name
        except (ImportError, ValueError):
            # find_spec can raise for a malformed or partially-shadowed
            # module name; treat that the same as "not present".
            continue
    return None
