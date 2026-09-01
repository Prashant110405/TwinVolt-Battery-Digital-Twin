"""Domain Exception Hierarchy for TwinVolt.

Defines the specialized exception classes for battery domain invariant
violations, physical configuration errors, and topology mismatches.
"""

from typing import Optional


class TwinVoltDomainError(Exception):
    """Base exception for all domain-level errors in TwinVolt."""

    def __init__(self, message: str, details: Optional[dict[str, object]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BatteryDomainError(TwinVoltDomainError):
    """Base exception for battery entity and configuration domain errors."""


class InvalidBatteryIdentifierError(BatteryDomainError):
    """Raised when a battery, module, or cell identifier is malformed or invalid."""


class InvalidBatteryTopologyError(BatteryDomainError):
    """Raised when a series/parallel battery topology definition is invalid or unphysical."""


class InvalidElectricalRatingsError(BatteryDomainError):
    """Raised when voltage, current, or capacity ratings violate physical or logical constraints."""


class InvalidThermalLimitsError(BatteryDomainError):
    """Raised when thermal limits are contradictory or physically impossible."""


class InvalidCellConfigurationError(BatteryDomainError):
    """Raised when a cell-level configuration violates physical parameters or chemistry constraints."""


class InvalidModuleConfigurationError(BatteryDomainError):
    """Raised when a module configuration is inconsistent with its constituent cells or topology."""


class InvalidPackConfigurationError(BatteryDomainError):
    """Raised when a pack configuration is inconsistent with its modules or operational limits."""


class DomainInvariantViolationError(BatteryDomainError):
    """Raised when a fundamental domain invariant is violated during runtime state transitions."""
