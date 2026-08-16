"""Console authentication — password in, bearer token out (SECURITY.md debt #1).

The Console is loopback-bound today, so the threat model is "anything else on
this machine, and anything the browser will talk to, should not get the user's
life data for free". A single password set by the user through the Console
gates every API route.

Design rules:

  * The password lives in the SecretStore — never NornicDB, never a log line,
    never a response body. This module never even logs that a check happened.
  * When no password is configured, authentication is *disabled* and every
    route works without a token. That keeps a fresh loopback deployment (and
    the test-suite) friction-free; a deployment that listens beyond loopback
    must set a password first.
  * Tokens are random, in-memory, and expiring. A restart invalidates them,
    which is acceptable for a single-user console and means there is no token
    store to protect at rest.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime

from lifeops.clock import Clock, SystemClock, to_iso
from lifeops.errors import LifeOpsError, ValidationError
from lifeops.secrets.interface import SecretStore, secret_ref
from lifeops.settings import Settings

#: SecretStore name for the Console password.
CONSOLE_PASSWORD_REF = secret_ref("console", "password")

#: How long an issued token stays valid.
TOKEN_TTL_S = 12 * 60 * 60


class AuthenticationError(LifeOpsError):
    """A route requiring a Console session was called without a valid token."""

    code = "authentication_required"
    http_status = 401


class InvalidCredentialsError(AuthenticationError):
    """Login attempted with a password that does not match."""

    code = "invalid_credentials"


class ConsoleAuth:
    """Issues and validates Console bearer tokens."""

    def __init__(
        self,
        *,
        secret_store: SecretStore,
        settings: Settings,
        clock: Clock | None = None,
    ) -> None:
        self._secrets = secret_store
        self._settings = settings
        self._clock = clock or SystemClock()
        self._tokens: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        """Auth applies only when the user has set a Console password."""
        return (
            self._settings.console_auth_enabled
            and self._secrets.exists(CONSOLE_PASSWORD_REF)
        )

    def set_password(self, password: str) -> None:
        """Set or replace the Console password. Existing tokens stay valid."""
        if not password:
            raise ValidationError("console password must not be empty", field="password")
        self._secrets.set(CONSOLE_PASSWORD_REF, password)

    def check_password(self, password: str) -> bool:
        """True when ``password`` matches the stored one. Never logged."""
        stored = self._secrets.get(CONSOLE_PASSWORD_REF)
        return stored is not None and hmac.compare_digest(stored, password)

    def login(self, password: str) -> tuple[str, str]:
        """Verify a password and return ``(token, expiry_iso)``.

        Raises InvalidCredentialsError on a mismatch. Never logs the attempt's
        password — the redaction rules in observability guard fields, but the
        simplest protection is not putting the value anywhere near a log call.
        """
        stored = self._secrets.get(CONSOLE_PASSWORD_REF)
        if stored is None or not hmac.compare_digest(stored, password):
            raise InvalidCredentialsError("the console password did not match")

        self._purge_expired()
        token = secrets.token_urlsafe(32)
        expires = self._clock.now().timestamp() + TOKEN_TTL_S
        self._tokens[token] = expires
        return token, to_iso(datetime.fromtimestamp(expires, UTC))

    def validate(self, token: str | None) -> bool:
        """True when ``token`` was issued and has not expired."""
        if not token:
            return False
        expires = self._tokens.get(token)
        if expires is None:
            return False
        if self._clock.now().timestamp() >= expires:
            del self._tokens[token]
            return False
        return True

    def _purge_expired(self) -> None:
        now = self._clock.now().timestamp()
        for token in [t for t, exp in self._tokens.items() if now >= exp]:
            del self._tokens[token]
