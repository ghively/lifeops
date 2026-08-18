"""Provider configuration validation.

Two jobs:

  * Coerce and bounds-check submitted values against the provider's field
    schema, so the Console gets a precise error instead of a stack trace.

  * Split a submission into non-secret settings and secret values. Secrets are
    routed straight to the SecretStore and never persisted alongside the rest
    of the configuration (BUILD_SPEC section 25).
"""

from __future__ import annotations

import math
from typing import Any

from lifeops.config.provider_registry import FieldKind, ProviderDefinition
from lifeops.errors import ValidationError


def _coerce(field_name: str, kind: FieldKind, value: Any) -> Any:
    if value is None:
        return None

    if kind is FieldKind.BOOLEAN:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        raise ValidationError(f"{field_name} must be a boolean", field=field_name)

    if kind is FieldKind.NUMBER:
        if isinstance(value, bool):
            raise ValidationError(f"{field_name} must be a number", field=field_name)
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{field_name} must be a number", field=field_name) from exc
        # NaN passes every bounds comparison and inf passes half of them; a
        # stored NaN timeout or port is never what anyone configured.
        if not math.isfinite(number):
            raise ValidationError(f"{field_name} must be a number", field=field_name)
        # Keep integers integral so a port does not round-trip as 993.0.
        return int(number) if number.is_integer() else number

    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be text", field=field_name)
    return value.strip()


class ValidatedUpdate:
    """The result of validating a provider configuration submission."""

    def __init__(self, settings: dict[str, Any], secrets: dict[str, str]) -> None:
        self.settings = settings
        self.secrets = secrets


def validate_update(
    provider: ProviderDefinition,
    submitted: dict[str, Any],
    *,
    known_secrets: set[str] | None = None,
) -> ValidatedUpdate:
    """Validate a partial configuration update.

    Only the submitted keys are checked. A partial update is the normal case:
    the Console edits one field at a time, and re-validating absent fields
    would force the user to re-enter an API key to change a timeout.

    ``known_secrets`` names secret fields already stored, so that a required
    secret is not reported missing just because this request did not resend it.
    """
    known_secrets = known_secrets or set()

    unknown = set(submitted) - {f.name for f in provider.fields}
    if unknown:
        raise ValidationError(
            f"unknown settings for provider {provider.id}: {sorted(unknown)}",
            provider=provider.id,
            unknown_fields=sorted(unknown),
        )

    settings: dict[str, Any] = {}
    secrets: dict[str, str] = {}

    for key, raw in submitted.items():
        field = provider.field(key)
        assert field is not None  # guarded by the unknown-key check above

        value = _coerce(key, field.kind, raw)

        if field.is_secret:
            if value is None or value == "":
                # An empty secret means "clear it", handled by the caller as a
                # delete. It must never be written as an empty credential.
                continue
            secrets[key] = str(value)
            continue

        if value is not None and field.kind is FieldKind.NUMBER:
            if field.minimum is not None and value < field.minimum:
                raise ValidationError(
                    f"{key} must be at least {field.minimum}", field=key
                )
            if field.maximum is not None and value > field.maximum:
                raise ValidationError(
                    f"{key} must be at most {field.maximum}", field=key
                )

        if value not in (None, "") and field.options:
            allowed = {opt["value"] for opt in field.options}
            if str(value) not in allowed:
                raise ValidationError(
                    f"{key} must be one of {sorted(allowed)}",
                    field=key,
                    allowed=sorted(allowed),
                )

        settings[key] = value

    return ValidatedUpdate(settings=settings, secrets=secrets)


def missing_required(
    provider: ProviderDefinition,
    settings: dict[str, Any],
    stored_secrets: set[str],
) -> list[str]:
    """Which required fields are still unset.

    Drives the NOT_CONFIGURED -> CONFIGURED transition. A field with a
    ``options_from`` source counts as missing until the user picks a value,
    because discovery cannot choose on their behalf.
    """
    missing: list[str] = []
    for field in provider.required_fields:
        if field.is_secret:
            if field.name not in stored_secrets:
                missing.append(field.name)
            continue
        value = settings.get(field.name, field.default)
        if value is None or value == "":
            missing.append(field.name)
    return missing
