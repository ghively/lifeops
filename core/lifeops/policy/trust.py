"""Trust hierarchy (BUILD_SPEC section 46).

External content creates evidence. It does not create user authority.

This module ranks the provenance of a claim so later phases can answer "may
this new observation overwrite what the user told me directly?" without each
caller inventing its own ordering. Phase 0 uses it to keep an inferred
preference from silently displacing an explicit one.
"""

from __future__ import annotations

from lifeops.domain.preferences import PreferenceSource

# Higher wins. The gap between USER_EXPLICIT and everything else is deliberate:
# nothing observed in the world outranks the user saying it.
_AUTHORITY: dict[PreferenceSource, int] = {
    PreferenceSource.USER_EXPLICIT: 100,
    PreferenceSource.SYSTEM: 80,  # verified system state
    PreferenceSource.CALENDAR: 60,  # trusted first-party provider
    PreferenceSource.DOCUMENT: 50,  # user-approved document
    PreferenceSource.EMAIL: 40,  # external message
    PreferenceSource.PHONE_CALL: 40,
    PreferenceSource.CONVERSATION: 35,
    PreferenceSource.WEBSITE: 20,  # public website
    PreferenceSource.USER_INFERRED: 15,  # model inference about the user
    PreferenceSource.AGENT: 10,  # model inference
}


def authority_of(source: PreferenceSource) -> int:
    """The rank of a source. Unknown sources raise rather than defaulting:
    the old ``.get(source, 0)`` silently ranked a future enum member below
    AGENT *and* let two of them supersede each other (0 >= 0) — a quiet
    landing on the permissive side, which is exactly what
    ``risk_for_action`` refuses for the same reason."""
    try:
        return _AUTHORITY[source]
    except KeyError:
        raise ValueError(
            f"no authority declared for preference source {source!r}"
        ) from None


def may_supersede(
    incoming: PreferenceSource,
    existing: PreferenceSource,
) -> bool:
    """Whether a claim from ``incoming`` may replace one from ``existing``.

    Equal authority is allowed to supersede: the user restating a preference,
    or a calendar re-sync, is a legitimate update. Only a *weaker* source is
    refused, which is what stops a web page or a model guess from quietly
    overwriting something the user said out loud.
    """
    return authority_of(incoming) >= authority_of(existing)


def is_user_authoritative(source: PreferenceSource) -> bool:
    return source is PreferenceSource.USER_EXPLICIT
