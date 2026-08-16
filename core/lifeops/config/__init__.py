"""Runtime configuration: provider schemas, validation, and the config service.

Configuration is GUI-driven (BUILD_SPEC section 5). Nothing in this package
requires a developer to hold a user's credential.
"""

from lifeops.config.provider_registry import (
    ProviderCategory,
    ProviderDefinition,
    ProviderField,
    ProviderState,
    all_providers,
    get_provider,
    providers_in_category,
)
from lifeops.config.service import (
    ConfigurationService,
    HealthReport,
    ProviderStatus,
    SecretStatus,
    SystemConfig,
)

__all__ = [
    "ConfigurationService",
    "HealthReport",
    "ProviderCategory",
    "ProviderDefinition",
    "ProviderField",
    "ProviderState",
    "ProviderStatus",
    "SecretStatus",
    "SystemConfig",
    "all_providers",
    "get_provider",
    "providers_in_category",
]
