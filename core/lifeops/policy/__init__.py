"""Deterministic authorization, risk, and trust policy.

Policy functions are pure and take the client identity explicitly. Nothing here
consults a model, and nothing here reads global request state.
"""

from lifeops.policy.capabilities import (
    CODING_CLIENT,
    CONSOLE,
    HERMES,
    INTERACTIVE_CLIENT,
    Capability,
    CapabilityGrant,
    ClientIdentity,
    ClientRole,
    RiskClass,
    UnknownClientPolicy,
    all_clients,
    require,
    resolve_client,
)
from lifeops.policy.trust import authority_of, is_user_authoritative, may_supersede

__all__ = [
    "CODING_CLIENT",
    "CONSOLE",
    "HERMES",
    "INTERACTIVE_CLIENT",
    "Capability",
    "CapabilityGrant",
    "ClientIdentity",
    "ClientRole",
    "RiskClass",
    "UnknownClientPolicy",
    "all_clients",
    "authority_of",
    "is_user_authoritative",
    "may_supersede",
    "require",
    "resolve_client",
]
