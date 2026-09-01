"""TwinVolt Configuration & Data Schemas Package.

Defines strongly-typed declarative schemas, profile validation,
safe YAML/JSON loaders, and materialization factories into domain entities.
"""

from src.schemas.battery_profile import (
    BalancingConfigSchema,
    BatteryProfileSchema,
    CellProfileSchema,
    CurrentLimitsSchema,
    RatingsSchema,
    ThermalLimitsSchema,
    TopologySchema,
    VoltageLimitsSchema,
)
from src.schemas.exceptions import (
    ConfigurationError,
    ConfigurationValidationError,
    InvalidBatteryProfileError,
    InvalidModelConfigurationError,
    SchemaVersionMismatchError,
)
from src.schemas.loader import (
    BatteryProfileLoader,
    ModelConfigurationLoader,
)
from src.schemas.model_profile import (
    ECMParametersSchema,
    ModelConfigurationSchema,
    SamplingConfigSchema,
)
from src.schemas.telemetry_schema import (
    TelemetryPayloadSchema,
    validate_telemetry_payload,
)

__all__ = [
    "ConfigurationError",
    "ConfigurationValidationError",
    "InvalidBatteryProfileError",
    "InvalidModelConfigurationError",
    "SchemaVersionMismatchError",
    "TopologySchema",
    "CellProfileSchema",
    "RatingsSchema",
    "VoltageLimitsSchema",
    "CurrentLimitsSchema",
    "ThermalLimitsSchema",
    "BalancingConfigSchema",
    "BatteryProfileSchema",
    "SamplingConfigSchema",
    "ECMParametersSchema",
    "ModelConfigurationSchema",
    "TelemetryPayloadSchema",
    "validate_telemetry_payload",
    "BatteryProfileLoader",
    "ModelConfigurationLoader",
]
