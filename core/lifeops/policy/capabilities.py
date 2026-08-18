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
start persisting it in audit records. Later phases extend the same manifest
(WRITE_WORLD in Phase 3) rather than inventing parallel policy.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from lifeops.errors import CapabilityDeniedError, SafeModeError


class Capability(StrEnum):
    """A named thing a client may be permitted to do."""

    #: Phase 11 (sections 73, 100). Its own capability rather than borrowing
    #: MANAGE_CONFIGURATION: that is the Console's human-present grant, and
    #: self-configuration is precisely the case where no human is present.
    SELF_CONFIGURE = "self_configure"
    READ_WORLD = "read_world"
    WRITE_WORLD = "write_world"
    READ_PREFERENCES = "read_preferences"
    WRITE_PREFERENCE = "write_preference"
    READ_TASKS = "read_tasks"
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    READ_MEMORY = "read_memory"
    WRITE_MEMORY = "write_memory"

    # Declared now, granted in later phases. Present so that a client whose
    # config claims them fails validation loudly instead of being ignored.
    # SEARCH_MEMORY stays declared for config stability; memory recall is
    # guarded by READ_MEMORY.
    SEARCH_MEMORY = "search_memory"
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
    #: A background process acting on already-recorded intent, not a
    #: conversation. It originates nothing.
    WORKER = "worker"


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

#: Hermes is the primary assistant and holds the broadest grant.
#: Memory read+write (Phase 2, section 91) and world read+write (Phase 3,
#: section 92): remembering and shaping the user's world is its core job.
#:
#: Phase 7 (section 96) adds BOOK_APPOINTMENT and SEND_EXTERNAL_MESSAGE.
#: Hermes is the client that actually reads a calendar and drafts an email on
#: the user's behalf, so it is the client that must be able to prepare those
#: Actions — otherwise section 96's read -> reversible-write -> external-
#: communication flow has no caller. Preparing is not executing: booking
#: still needs a human's APPROVE_ACTION (Console-only, below), and a hold
#: still cannot become a booking without independent verification
#: (domain/calendar.py, section 63's warning).
#:
#: Phase 9 (section 98) adds SHOPPING_CHECKOUT. Hermes is the client that
#: searches, builds a grocery cart, and applies substitutions, so it needs the
#: one capability both ``build_grocery_cart`` (R1, automatic) and
#: ``submit_grocery_order`` (R3, always approved) spend
#: (``CAPABILITY_FOR_ACTION`` below) — granting it does not skip approval:
#: checkout still needs a human's APPROVE_ACTION before ``execute_action`` may
#: run it, same as booking.
HERMES = ClientIdentity(
    client_id="hermes-personal",
    role=ClientRole.PRIMARY_ASSISTANT,
    display_name="Hermes",
    description="The user's primary conversational assistant.",
    capabilities=_READ_ONLY
    | {
        Capability.WRITE_WORLD,
        Capability.WRITE_PREFERENCE,
        Capability.CREATE_TASK,
        Capability.UPDATE_TASK,
        Capability.READ_MEMORY,
        Capability.WRITE_MEMORY,
        Capability.BOOK_APPOINTMENT,
        Capability.SEND_EXTERNAL_MESSAGE,
        Capability.SHOPPING_CHECKOUT,
        # Section 100: Hermes manages its own skills, routines, and templates.
        # The boundary is enforced in the domain rather than by withholding
        # this — a protected change becomes a code change request, not a
        # blanket refusal to let Hermes tune itself.
        Capability.SELF_CONFIGURE,
    },
)

#: A general interactive MCP client (ChatGPT, another Claude surface).
#: Reads and creates tasks; may state preferences on the user's behalf, since
#: the user is talking to it directly. It may read memory but not write it:
#: durable recollection of the user's life is the primary assistant's job.
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
        Capability.READ_MEMORY,
    },
)

#: A coding agent. Reads the world, files tasks, and may recall memory (useful
#: context for code work) — but does not get to write the user's recollections
#: or rewrite stated preferences: its job is the repository (section 35).
CODING_CLIENT = ClientIdentity(
    client_id="claude-code",
    role=ClientRole.ENGINEERING_ASSISTANT,
    display_name="Claude Code",
    description="An engineering assistant operating on the repository.",
    capabilities=_READ_ONLY | {Capability.CREATE_TASK, Capability.READ_MEMORY},
)

#: The Console acts as the user directly: it is the surface where a human
#: corrects state and administers configuration. Memory read+write covers the
#: Memory screen's correct/invalidate flows (section 17, section 91).
#:
#: BOOK_APPOINTMENT and SEND_EXTERNAL_MESSAGE (Phase 7, section 96) let the
#: human operating the Console place a hold or send an email themselves, not
#: only approve one Hermes prepared — the Console already stands in for the
#: user directly for every other write. It also holds APPROVE_ACTION, so a
#: Console-prepared booking still needs the human's own decision before it
#: can execute; nothing here is a way around the approval gate.
#:
#: SHOPPING_CHECKOUT (Phase 9, section 98) is granted for the same reason: the
#: human operating the Console can build and submit a cart themselves, not
#: only approve one Hermes assembled. APPROVE_ACTION stays the only path to
#: actually clearing a checkout to run — the Console holding both is not a way
#: around that, the same way it already is not for booking.
CONSOLE = ClientIdentity(
    client_id="lifeops-console",
    role=ClientRole.CONSOLE,
    display_name="LifeOps Console",
    description="The user operating LifeOps through the web interface.",
    capabilities=_READ_ONLY
    | {
        Capability.WRITE_WORLD,
        Capability.WRITE_PREFERENCE,
        Capability.CREATE_TASK,
        Capability.UPDATE_TASK,
        Capability.READ_MEMORY,
        Capability.WRITE_MEMORY,
        Capability.SELF_CONFIGURE,
        Capability.MANAGE_CONFIGURATION,
        Capability.APPROVE_ACTION,
        # Phase 10, and deliberately Console-only. Section 72 requires that
        # credentials are never exposed to Hermes and that every payment and
        # every new payee is approved by a human; the narrowest way to
        # guarantee both is for the capability to exist only where a human is
        # present. Hermes can read what is owed and can tell the user a
        # payment is due — it cannot prepare or commit one, so there is no
        # path from a model's reasoning to money moving.
        Capability.FINANCIAL_PAYMENT,
        Capability.BOOK_APPOINTMENT,
        Capability.SEND_EXTERNAL_MESSAGE,
        Capability.SHOPPING_CHECKOUT,
    },
)

#: The due-work worker (BUILD_SPEC section 55).
#:
#: It gets an identity of its own rather than borrowing Hermes's. Two reasons,
#: both load-bearing. Section 62's audit log exists to answer "which client
#: changed this?" — a worker filing its follow-ups as Hermes makes that answer
#: false. And it needs exactly two capabilities: reading what is due and
#: updating it. Running as Hermes would hand a loop that nobody is watching the
#: ability to write memory, preferences, and the world graph.
DUE_WORK_WORKER = ClientIdentity(
    client_id="lifeops-worker",
    role=ClientRole.WORKER,
    display_name="LifeOps due-work worker",
    description="Follows up on waiting items that have come due.",
    capabilities=frozenset({Capability.READ_TASKS, Capability.UPDATE_TASK}),
)


_REGISTRY: dict[str, ClientIdentity] = {
    client.client_id: client
    for client in (
        HERMES,
        INTERACTIVE_CLIENT,
        CODING_CLIENT,
        CONSOLE,
        DUE_WORK_WORKER,
    )
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
        # Under DENY a *missing* identity is refused exactly like a wrong
        # one: an MCP server launched with neither --client nor its env var
        # must fail loudly, not silently become the default identity.
        # SECURITY.md promises "a missing identity is refused, never
        # defaulted" — this branch is where that promise is kept.
        if unknown is UnknownClientPolicy.DENY:
            raise CapabilityDeniedError(
                "no client identity was provided", client_id=""
            )
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


#: Which capability each external action spends (BUILD_SPEC sections 51, 52).
#:
#: The risk classes were declared in Phase 0 and left unused precisely so this
#: mapping could exist without inventing new policy. Preparing an action is
#: gated on the capability for its class, so a client that may email cannot
#: book, and one that may book cannot pay — without any new enum member.
CAPABILITY_FOR_ACTION: dict[str, Capability] = {
    "send_email": Capability.SEND_EXTERNAL_MESSAGE,
    "request_quote": Capability.SEND_EXTERNAL_MESSAGE,
    "place_phone_call": Capability.SEND_EXTERNAL_MESSAGE,
    "book_appointment": Capability.BOOK_APPOINTMENT,
    "cancel_appointment": Capability.BOOK_APPOINTMENT,
    "build_grocery_cart": Capability.SHOPPING_CHECKOUT,
    "submit_grocery_order": Capability.SHOPPING_CHECKOUT,
    "prepare_payment": Capability.FINANCIAL_PAYMENT,
    "commit_payment": Capability.FINANCIAL_PAYMENT,
    "add_payee": Capability.FINANCIAL_PAYMENT,
}


def capability_for_action(action_type: str) -> Capability:
    """The capability an action type requires.

    Unknown types raise rather than defaulting: a new action reaching this
    function without a declared risk class is a policy gap, and defaulting it
    to the weakest capability would be the wrong way to discover that.
    """
    try:
        return CAPABILITY_FOR_ACTION[str(action_type)]
    except KeyError:
        raise ValueError(f"no capability declared for action type {action_type!r}") from None
