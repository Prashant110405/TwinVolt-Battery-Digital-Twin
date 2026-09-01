"""TwinVolt Canonical Telemetry Package.

Defines the universal, strongly-typed internal contract for battery measurements,
sensor observations, and telemetry snapshots across all hardware and virtual data sources.

Architectural Rule:
Canonical Telemetry is an internal platform contract, NOT a hardware protocol.
All physical and virtual data sources (CAN, MQTT, Serial, Replay, Simulation)
must be normalized into this representation by their respective adapters.
"""

from src.telemetry.enums import (
    CurrentFlowDirection,
    MeasurementProvenance,
    TelemetryQuality,
)
from src.telemetry.exceptions import (
    InvalidTelemetryTimestampError,
    InvalidTelemetryValueError,
    TelemetryError,
    TelemetryValidationError,
)
from src.telemetry.measurements import (
    CellTelemetry,
    MeasurementValue,
    ModuleTelemetry,
    TemperatureSensorTelemetry,
)
from src.telemetry.snapshots import TelemetrySnapshot

__all__ = [
    "TelemetryQuality",
    "MeasurementProvenance",
    "CurrentFlowDirection",
    "TelemetryError",
    "InvalidTelemetryValueError",
    "InvalidTelemetryTimestampError",
    "TelemetryValidationError",
    "MeasurementValue",
    "CellTelemetry",
    "TemperatureSensorTelemetry",
    "ModuleTelemetry",
    "TelemetrySnapshot",
]
