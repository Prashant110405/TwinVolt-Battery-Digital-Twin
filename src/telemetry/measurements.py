"""Individual Measurement Value Objects for Canonical Telemetry.

Defines granular measurement containers for cells, discrete temperature sensors,
and module-level telemetry aggregations.
"""

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

from src.domain.battery.validation import validate_battery_identifier
from src.telemetry.enums import (
    MeasurementProvenance,
    TelemetryQuality,
)
from src.telemetry.validation import (
    validate_current_telemetry,
    validate_fraction_telemetry,
    validate_non_negative_metric,
    validate_temperature_telemetry,
    validate_voltage_telemetry,
)


@dataclass(frozen=True)
class MeasurementValue:
    """Strongly-typed scalar measurement wrapper with explicit SI units and provenance."""

    value: float
    unit: str
    quality: TelemetryQuality = TelemetryQuality.VALID
    provenance: MeasurementProvenance = MeasurementProvenance.MEASURED
    timestamp_ns: Optional[int] = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Returns True if the measurement quality is VALID or DEGRADED."""
        return self.quality in (TelemetryQuality.VALID, TelemetryQuality.DEGRADED)

    @property
    def is_available(self) -> bool:
        """Returns True if the measurement is not marked UNAVAILABLE."""
        return self.quality != TelemetryQuality.UNAVAILABLE


@dataclass(frozen=True)
class CellTelemetry:
    """Normalized telemetry reading for an individual battery cell."""

    cell_id: str
    voltage_v: Optional[float] = None
    temperature_c: Optional[float] = None
    internal_resistance_mohm: Optional[float] = None
    soc_fraction: Optional[float] = None
    quality: TelemetryQuality = TelemetryQuality.VALID
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_battery_identifier(self.cell_id, "cell_id")
        validate_voltage_telemetry(self.voltage_v, f"Cell {self.cell_id} voltage_v")
        validate_temperature_telemetry(self.temperature_c, f"Cell {self.cell_id} temperature_c")
        validate_non_negative_metric(
            self.internal_resistance_mohm, f"Cell {self.cell_id} internal_resistance_mohm"
        )
        validate_fraction_telemetry(self.soc_fraction, f"Cell {self.cell_id} soc_fraction")

    @property
    def has_voltage(self) -> bool:
        """Returns True if cell voltage measurement is present."""
        return self.voltage_v is not None

    @property
    def has_temperature(self) -> bool:
        """Returns True if cell temperature measurement is present."""
        return self.temperature_c is not None


@dataclass(frozen=True)
class TemperatureSensorTelemetry:
    """Telemetry reading from a discrete physical temperature probe."""

    sensor_id: str
    temperature_c: float
    quality: TelemetryQuality = TelemetryQuality.VALID
    provenance: MeasurementProvenance = MeasurementProvenance.MEASURED

    def __post_init__(self) -> None:
        validate_battery_identifier(self.sensor_id, "sensor_id")
        validate_temperature_telemetry(self.temperature_c, f"Sensor {self.sensor_id} temperature_c")


@dataclass(frozen=True)
class ModuleTelemetry:
    """Telemetry reading for an intermediate module containing multiple cells/sensors."""

    module_id: str
    voltage_v: Optional[float] = None
    temperature_c: Optional[float] = None
    cell_telemetries: Tuple[CellTelemetry, ...] = field(default_factory=tuple)
    temperature_sensors: Tuple[TemperatureSensorTelemetry, ...] = field(default_factory=tuple)
    quality: TelemetryQuality = TelemetryQuality.VALID

    def __post_init__(self) -> None:
        validate_battery_identifier(self.module_id, "module_id")
        validate_voltage_telemetry(self.voltage_v, f"Module {self.module_id} voltage_v")
        validate_temperature_telemetry(self.temperature_c, f"Module {self.module_id} temperature_c")

    @property
    def cell_count(self) -> int:
        """Number of cell telemetry entries in this module."""
        return len(self.cell_telemetries)

    def get_cell(self, cell_id: str) -> Optional[CellTelemetry]:
        """Looks up a cell telemetry entry by its cell_id."""
        for cell in self.cell_telemetries:
            if cell.cell_id == cell_id:
                return cell
        return None

    @property
    def cell_voltages(self) -> Tuple[float, ...]:
        """Returns all present cell voltages in this module."""
        return tuple(c.voltage_v for c in self.cell_telemetries if c.voltage_v is not None)
