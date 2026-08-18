"""Configuration service: provider state, secret routing, and validation.

The behaviour these tests protect is BUILD_SPEC section 104: a fresh checkout
boots with every provider unconfigured, the Console reachable, and no developer
ever holding a user credential.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lifeops.config.provider_registry import (
    ProviderState,
    all_providers,
    get_provider,
)
from lifeops.config.service import ConfigurationService
from lifeops.config.validation import validate_update
from lifeops.errors import ConfigurationError, NotFoundError, ValidationError
from lifeops.secrets.local_encrypted import InMemorySecretStore


class TestFreshDeployment:
    def test_no_provider_is_live_on_a_fresh_deployment(
        self, config_service: ConfigurationService
    ) -> None:
        # The invariant behind BUILD_SPEC section 104: a fresh checkout runs
        # with nothing connected and no credential in hand.
        inert = {ProviderState.NOT_CONFIGURED, ProviderState.DISABLED}
        for status in config_service.list_status():
            assert status.state in inert, status.id
            assert not status.enabled, status.id

    def test_providers_needing_a_credential_read_as_not_configured(
        self, config_service: ConfigurationService
    ) -> None:
        # "I have not set this up" — the setup wizard walks the user through
        # these (BUILD_SPEC sections 23 and 104).
        statuses = {s.id: s for s in config_service.list_status()}
        for provider_id in ("deepseek", "elevenlabs", "telegram"):
            assert statuses[provider_id].state is ProviderState.NOT_CONFIGURED
            assert statuses[provider_id].missing_required

    def test_optional_providers_read_their_true_state(
        self, config_service: ConfigurationService
    ) -> None:
        # Section 104's expected list shows Calendar/Email as "Disabled", but
        # this suite already reads Telegram as NOT_CONFIGURED (above) on the
        # grounds that a missing required field is the more informative truth
        # — and calendar/email declare required fields for the same reason:
        # without them, {"enabled": true} with nothing configured reached
        # state CONFIGURED while the factory refused every call. Telephony
        # now speaks Twilio's REST API and needs the same treatment — an
        # account SID/auth token/from number, all required — so it moved
        # out of the "no config needed at all" group browser is still in.
        statuses = {s.id: s for s in config_service.list_status()}
        for provider_id in ("calendar", "email", "telephony"):
            assert statuses[provider_id].state is ProviderState.NOT_CONFIGURED
            assert statuses[provider_id].missing_required
        assert statuses["browser"].state is ProviderState.DISABLED

    def test_the_required_phase_zero_providers_are_registered(self) -> None:
        registered = {p.id for p in all_providers()}
        required = {
            "deepseek",
            "elevenlabs",
            "telegram",
            "calendar",
            "email",
            "browser",
            "telephony",
        }
        assert required <= registered

    def test_no_provider_ships_a_default_credential(self) -> None:
        for provider in all_providers():
            for field in provider.secret_fields:
                assert field.default is None, f"{provider.id}.{field.name}"


class TestProviderLifecycle:
    def test_partial_configuration_stays_not_configured(
        self, config_service: ConfigurationService
    ) -> None:
        config_service.update_provider("deepseek", {"api_key": "sk-test"})
        status = config_service.get_status("deepseek")
        assert status.state is ProviderState.NOT_CONFIGURED
        assert "model" in status.missing_required

    def test_complete_but_disabled_reads_as_disabled(
        self, config_service: ConfigurationService
    ) -> None:
        config_service.update_provider(
            "deepseek", {"api_key": "sk-test", "model": "deepseek-chat"}
        )
        assert config_service.get_status("deepseek").state is ProviderState.DISABLED

    def test_complete_and_enabled_reads_as_configured_until_checked(
        self, config_service: ConfigurationService
    ) -> None:
        config_service.update_provider(
            "deepseek",
            {"api_key": "sk-test", "model": "deepseek-chat", "enabled": True},
        )
        assert config_service.get_status("deepseek").state is ProviderState.CONFIGURED

    def test_health_result_drives_healthy_and_unhealthy(
        self, config_service: ConfigurationService
    ) -> None:
        config_service.update_provider(
            "deepseek",
            {"api_key": "sk-test", "model": "deepseek-chat", "enabled": True},
        )

        config_service.record_health("deepseek", healthy=True, message="ok")
        assert config_service.get_status("deepseek").state is ProviderState.HEALTHY

        config_service.record_health("deepseek", healthy=False, message="401")
        assert config_service.get_status("deepseek").state is ProviderState.UNHEALTHY

    def test_missing_settings_outrank_the_enabled_flag(
        self, config_service: ConfigurationService
    ) -> None:
        # A provider that cannot work should not merely read as "off".
        config_service.update_provider("deepseek", {"enabled": True})
        assert config_service.get_status("deepseek").state is ProviderState.NOT_CONFIGURED


class TestSecretHandling:
    def test_secrets_go_to_the_secret_store_not_the_config_document(
        self, tmp_path: Path, secret_store: InMemorySecretStore
    ) -> None:
        service = ConfigurationService(
            config_dir=tmp_path / "config", secret_store=secret_store
        )
        # Submit a secret alongside a normal setting, so the config document is
        # definitely written and can be inspected for leakage.
        service.update_provider(
            "elevenlabs", {"api_key": "el-secret-key", "speed": 1.1}
        )

        assert secret_store.get("elevenlabs.api_key") == "el-secret-key"
        document = (tmp_path / "config" / "lifeops.config.json").read_text()
        assert "el-secret-key" not in document
        assert "1.1" in document

    def test_reads_never_return_the_secret_value(
        self, config_service: ConfigurationService
    ) -> None:
        config_service.update_provider("elevenlabs", {"api_key": "el-secret-key"})
        status = config_service.get_status("elevenlabs")

        assert status.secrets["api_key"].configured is True
        assert status.secrets["api_key"].fingerprint is not None
        assert "el-secret-key" not in status.model_dump_json()

    def test_empty_secret_clears_it(self, config_service: ConfigurationService) -> None:
        config_service.update_provider("elevenlabs", {"api_key": "el-secret-key"})
        config_service.update_provider("elevenlabs", {"api_key": ""})
        assert config_service.get_status("elevenlabs").secrets["api_key"].configured is False

    def test_updating_another_field_keeps_the_stored_secret(
        self, config_service: ConfigurationService
    ) -> None:
        config_service.update_provider("elevenlabs", {"api_key": "el-secret-key"})
        config_service.update_provider("elevenlabs", {"speed": 1.2})
        status = config_service.get_status("elevenlabs")
        assert status.secrets["api_key"].configured is True
        assert status.settings["speed"] == 1.2

    def test_adapter_can_read_a_secret_deliberately(
        self, config_service: ConfigurationService
    ) -> None:
        config_service.update_provider("elevenlabs", {"api_key": "el-secret-key"})
        assert config_service.get_secret("elevenlabs", "api_key") == "el-secret-key"


class TestValidation:
    def test_unknown_field_is_rejected_by_name(self) -> None:
        provider = get_provider("deepseek")
        assert provider is not None
        with pytest.raises(ValidationError) as exc:
            validate_update(provider, {"not_a_field": "x"})
        assert exc.value.details["unknown_fields"] == ["not_a_field"]

    def test_unknown_provider_raises_not_found(
        self, config_service: ConfigurationService
    ) -> None:
        with pytest.raises(NotFoundError):
            config_service.get_status("no_such_provider")

    def test_number_bounds_are_enforced(
        self, config_service: ConfigurationService
    ) -> None:
        with pytest.raises(ValidationError):
            config_service.update_provider("elevenlabs", {"stability": 5.0})

    def test_select_options_are_enforced(
        self, config_service: ConfigurationService
    ) -> None:
        with pytest.raises(ValidationError):
            config_service.update_provider("elevenlabs", {"output_format": "wav_8bit"})

    def test_boolean_strings_are_coerced(
        self, config_service: ConfigurationService
    ) -> None:
        config_service.update_provider("telegram", {"enabled": "true"})
        assert config_service.get_status("telegram").settings["enabled"] is True

    def test_integer_ports_stay_integers(
        self, config_service: ConfigurationService
    ) -> None:
        config_service.update_provider("email", {"imap_port": "993"})
        assert config_service.get_status("email").settings["imap_port"] == 993

    def test_non_numeric_value_for_a_number_field_is_rejected(
        self, config_service: ConfigurationService
    ) -> None:
        with pytest.raises(ValidationError):
            config_service.update_provider("email", {"imap_port": "not-a-port"})


class TestSystemConfig:
    def test_defaults(self, config_service: ConfigurationService) -> None:
        system = config_service.get_system()
        assert system.setup_completed is False
        assert system.safe_mode is False

    def test_update_persists(self, tmp_path: Path, secret_store: InMemorySecretStore) -> None:
        config_dir = tmp_path / "config"
        ConfigurationService(config_dir=config_dir, secret_store=secret_store).update_system(
            {"display_name": "Gene's LifeOps", "timezone": "America/New_York"}
        )
        reloaded = ConfigurationService(
            config_dir=config_dir, secret_store=secret_store
        ).get_system()
        assert reloaded.display_name == "Gene's LifeOps"
        assert reloaded.timezone == "America/New_York"

    def test_unknown_system_setting_is_rejected(
        self, config_service: ConfigurationService
    ) -> None:
        with pytest.raises(ConfigurationError):
            config_service.update_system({"nonsense": True})
