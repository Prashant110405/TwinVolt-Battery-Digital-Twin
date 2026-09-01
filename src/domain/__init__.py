"""TwinVolt Universal Battery Domain Layer.

This package contains pure domain models, entities, value objects,
enums, and invariant validation for battery systems.

Architectural Rule:
The domain layer is pure Python. It has ZERO dependencies on databases,
APIs, web frameworks, hardware drivers, or specific modeling packages.
"""

from src.domain.exceptions import (
    BatteryDomainError,
    DomainInvariantViolationError,
    InvalidBatteryIdentifierError,
    InvalidBatteryTopologyError,
    InvalidCellConfigurationError,
    InvalidElectricalRatingsError,
    InvalidModuleConfigurationError,
    InvalidPackConfigurationError,
    InvalidThermalLimitsError,
    TwinVoltDomainError,
)

__all__ = [
    "TwinVoltDomainError",
    "BatteryDomainError",
    "InvalidBatteryTopologyError",
    "InvalidElectricalRatingsError",
    "InvalidThermalLimitsError",
    "InvalidBatteryIdentifierError",
    "InvalidCellConfigurationError",
    "InvalidModuleConfigurationError",
    "InvalidPackConfigurationError",
    "DomainInvariantViolationError",
]
