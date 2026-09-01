"""Telemetry Exceptions for the TwinVolt Platform.

Defines domain exceptions raised when telemetry values violate physical invariants,
contain invalid timestamps, or fail structural consistency checks.
"""

from typing import Optional

from src.domain.exceptions import TwinVoltDomainError


class TelemetryError(TwinVoltDomainError):
    """Base exception for all telemetry-related errors in TwinVolt."""


class InvalidTelemetryValueError(TelemetryError):
    """Raised when a telemetry measurement value is unphysical (e.g., negative voltage, NaN, Inf)."""


class InvalidTelemetryTimestampError(TelemetryError):
    """Raised when a telemetry timestamp is unphysical, negative, or erroneously far in the future."""


class TelemetryValidationError(TelemetryError):
    """Raised when a telemetry snapshot fails structural consistency or addressing rules."""
