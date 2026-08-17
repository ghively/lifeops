"""LifeOps error taxonomy.

Errors carry a stable ``code`` because two very different consumers read them:
the Console (which renders them to a human) and MCP clients (whose LLM has to
decide whether to retry, ask the user, or give up). Prose alone is not a
reliable signal for either.
"""

from __future__ import annotations

from typing import Any


class LifeOpsError(Exception):
    """Base class for every error LifeOps raises deliberately."""

    code = "lifeops_error"
    http_status = 500

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class NotFoundError(LifeOpsError):
    code = "not_found"
    http_status = 404


class ValidationError(LifeOpsError):
    code = "validation_error"
    http_status = 422


class ConflictError(LifeOpsError):
    code = "conflict"
    http_status = 409


class InvalidTransitionError(ConflictError):
    """A task state change the state machine does not permit (BUILD_SPEC 14).

    Raised rather than silently coerced: an LLM proposing an impossible
    transition is a signal worth surfacing, not smoothing over.
    """

    code = "invalid_transition"


class VerificationRequiredError(ConflictError):
    """Completion attempted without evidence from the target system.

    BUILD_SPEC section 6 and 53: an external action is not complete merely
    because the model says it is.
    """

    code = "verification_required"


class AuthorizationError(LifeOpsError):
    code = "not_authorized"
    http_status = 403


class CapabilityDeniedError(AuthorizationError):
    """The calling client identity does not hold the required capability."""

    code = "capability_denied"


class SafeModeError(AuthorizationError):
    """Blocked because LifeOps is in safe mode (BUILD_SPEC section 83)."""

    code = "safe_mode"


class ConfigurationError(LifeOpsError):
    code = "configuration_error"
    http_status = 400


class SecretStoreError(LifeOpsError):
    code = "secret_store_error"


class RepositoryError(LifeOpsError):
    """The persistence layer failed. Never leaks Cypher or driver internals."""

    code = "repository_error"
    http_status = 503


class ProviderError(LifeOpsError):
    """An external provider adapter failed (BUILD_SPEC sections 27-28).

    Distinct from RepositoryError, which is specifically NornicDB — this
    covers ElevenLabs, DeepSeek, or any other outside service a provider
    adapter calls.
    """

    code = "provider_error"
    http_status = 502


class ProviderNotConfiguredError(ConfigurationError):
    """The requested capability has no enabled, fully-configured provider.

    Distinguishes "nobody turned this on yet" from "the adapter is broken" —
    the Console and an MCP client need to react to those differently, and
    AGENTS.md forbids ever standing in for the missing credential.
    """

    code = "provider_not_configured"
