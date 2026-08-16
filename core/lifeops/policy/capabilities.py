"""Client identity and capability policy (BUILD_SPEC sections 34 and 35).

Two rules shape this module:

  * Authority is never inferred from a model or provider name. A request
    carries a client identity, and that identity is what policy consults.
    "Claude said so" is not a permission.

  * There is no policy *language*. Capabilities are an explicit map and the
    decision function is deterministic and readable. A rules engine here would
    be a system built for a problem that does not exist (section 105).

Phase 0 wires only the capabilities the five MCP tools need. The unused risk
classes are declared because the enum has to be stable before other phases
start persisting it in audit records.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.errors import CapabilityDeniedError, SafeModeError


class Capability(StrEnum):
    """A named thing a client may be permitted to do."""

    READ_WORLD = "read_world"
    READ_PREFERENCES = "read_preferences"
    WRITE_PREFERENCE = "write_preference"
    READ_TASKS = "read_tasks"
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"

    # Declared now, granted in later phases. Present so that a client whose
    # config claims them fails validation loudly instead of being ignored.
    SEARCH_MEMORY = "search_memory"
    WRITE_MEMORY = "write_memory"
    SEND_EXTERNAL_MESSAGE = "send_external_message"
    BOOK_APPOINTMENT = "book_appointment"
    SHOPPING_CHECKOUT = "shopping_checkout"
    FINANCIAL_PAYMENT = "financial_payment"
    MANAGE_CONFIGURATION = "manage_configuration"
    APPROVE_ACTION = "approve_action"


class RiskClass(StrEnum):
    """BUILD_SPEC section 56."""

    R0_READ = "R0"
    R1_LOCAL_REVERSIBLE = "R1"
    R2_EXTERNAL_COMMUNICATION = "R2"
    R3_EXTERNAL_COMMITMENT = "R3"
    R4_FINANCIAL_LEGAL_MEDICAL = "R4"


#: Capabilities blocked whenever LifeOps is in safe mode (section 83).
#: Reads, memory search, tasks, and local state stay available.
SAFE_MODE_BLOCKED: frozenset[Capability] = frozenset(
    {
        Capability.SEND_EXTERNAL_MESSAGE,
        Capability.BOOK_APPOINTMENT,
        Capability.SHOPPING_CHECKOUT,
        Capability.FINANCIAL_PAYMENT,
    }
)


class ClientRole(StrEnum):
    PRIMARY_ASSISTANT = "primary_assistant"
    INTERACTIVE_ASSISTANT = "interactive_assistant"
    ENGINEERING_ASSISTANT = "engineering_assistant"
    CONSOLE = "console"


class ClientIdentity(BaseModel):
    """Who is asking. Resolved before any capability check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_id: str
    role: ClientRole
    display_name: str
    capabilities: frozenset[Capability]
    description: str = ""

    def has(self, capability: Capability) -> bool:
        return capability in self.capabilities


# --- The capability manifest (BUILD_SPEC section 35) -------------------------

_READ_ONLY: frozenset[Capability] = frozenset(
    {
        Capability.READ_WORLD,
        Capability.READ_PREFERENCES,
        Capability.READ_TASKS,
    }
)

#: Hermes is the primary assistant and holds the broadest Phase 0 grant.
HERMES = ClientIdentity(
    client_id="hermes-personal",
    role=ClientRole.PRIMARY_ASSISTANT,
    display_name="Hermes",
    description="The user's primary conversational assistant.",
    capabilities=_READ_ONLY
    | {
        Capability.WRITE_PREFERENCE,
        Capability.CREATE_TASK,
        Capability.UPDATE_TASK,
    },
)

#: A general interactive MCP client (ChatGPT, another Claude surface).
#: Reads and creates tasks; may state preferences on the user's behalf, since
#: the user is talking to it directly.
INTERACTIVE_CLIENT = ClientIdentity(
    client_id="interactive-mcp",
    role=ClientRole.INTERACTIVE_ASSISTANT,
    display_name="Interactive MCP client",
    description="A trusted conversational client other than Hermes.",
    capabilities=_READ_ONLY
    | {
        Capability.WRITE_PREFERENCE,
        Capability.CREATE_TASK,
        Capability.UPDATE_TASK,
    },
)

#: A coding agent. Reads the world and files tasks, but does not get to
#: rewrite the user's stated preferences — its job is the repository, not the
#: user's life (section 35).
CODING_CLIENT = ClientIdentity(
    client_id="claude-code",
    role=ClientRole.ENGINEERING_ASSISTANT,
    display_name="Claude Code",
    description="An engineering assistant operating on the repository.",
    capabilities=_READ_ONLY | {Capability.CREATE_TASK},
)

#: The Console acts as the user directly: it is the surface where a human
#: corrects state and administers configuration.
CONSOLE = ClientIdentity(
    client_id="lifeops-console",
    role=ClientRole.CONSOLE,
    display_name="LifeOps Console",
    description="The user operating LifeOps through the web interface.",
    capabilities=_READ_ONLY
    | {
        Capability.WRITE_PREFERENCE,
        Capability.CREATE_TASK,
        Capability.UPDATE_TASK,
        Capability.MANAGE_CONFIGURATION,
        Capability.APPROVE_ACTION,
    },
)

_REGISTRY: dict[str, ClientIdentity] = {
    client.client_id: client for client in (HERMES, INTERACTIVE_CLIENT, CODING_CLIENT, CONSOLE)
}

#: Requests arriving without a declared identity are treated as a generic
#: interactive client rather than as Hermes. Defaulting to the most privileged
#: identity would make the manifest decorative.
DEFAULT_CLIENT_ID = INTERACTIVE_CLIENT.client_id


class UnknownClientPolicy(StrEnum):
    DENY = "deny"
    TREAT_AS_DEFAULT = "treat_as_default"


def resolve_client(
    client_id: str | None,
    *,
    unknown: UnknownClientPolicy = UnknownClientPolicy.TREAT_AS_DEFAULT,
) -> ClientIdentity:
    """Map a declared client_id to its identity."""
    if not client_id:
        return _REGISTRY[DEFAULT_CLIENT_ID]

    identity = _REGISTRY.get(client_id.strip().lower())
    if identity is not None:
        return identity

    if unknown is UnknownClientPolicy.DENY:
        raise CapabilityDeniedError(
            f"unknown client identity {client_id!r}", client_id=client_id
        )
    return _REGISTRY[DEFAULT_CLIENT_ID]


def all_clients() -> list[ClientIdentity]:
    """Every registered client. Feeds the Console's permission inspector."""
    return sorted(_REGISTRY.values(), key=lambda c: c.client_id)


def require(
    client: ClientIdentity,
    capability: Capability,
    *,
    safe_mode: bool = False,
) -> None:
    """Raise unless ``client`` may exercise ``capability`` right now.

    Safe mode is checked first: an emergency stop must not be defeated by a
    client that happens to hold the capability.
    """
    if safe_mode and capability in SAFE_MODE_BLOCKED:
        raise SafeModeError(
            f"{capability} is blocked while LifeOps is in safe mode",
            capability=str(capability),
            client_id=client.client_id,
        )

    if not client.has(capability):
        raise CapabilityDeniedError(
            f"client {client.client_id!r} may not {capability}",
            client_id=client.client_id,
            capability=str(capability),
            role=str(client.role),
        )


class CapabilityGrant(BaseModel):
    """Serialisable view of one client's permissions, for the Console."""

    model_config = ConfigDict(extra="forbid")

    client_id: str
    role: ClientRole
    display_name: str
    description: str
    capabilities: list[Capability] = Field(default_factory=list)

    @classmethod
    def of(cls, client: ClientIdentity) -> CapabilityGrant:
        return cls(
            client_id=client.client_id,
            role=client.role,
            display_name=client.display_name,
            description=client.description,
            capabilities=sorted(client.capabilities, key=str),
        )
