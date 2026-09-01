"""Configuration & Schema Exceptions for TwinVolt.

Defines domain exceptions raised when configuration files, battery profiles,
or telemetry payloads fail schema validation or contain malformed fields.
"""

from typing import Optional

from src.domain.exceptions import TwinVoltDomainError


class ConfigurationError(TwinVoltDomainError):
    """Base exception for all configuration and schema validation errors."""


class ConfigurationValidationError(ConfigurationError):
    """Raised when a declarative schema violates validation constraints or data types."""


class InvalidBatteryProfileError(ConfigurationError):
    """Raised when a battery profile definition is unphysical, inconsistent, or corrupted."""


class InvalidModelConfigurationError(ConfigurationError):
    """Raised when a battery model configuration contains invalid parameters or sampling settings."""


class SchemaVersionMismatchError(ConfigurationError):
    """Raised when a declarative file specifies an unsupported or unmigrated schema version."""
