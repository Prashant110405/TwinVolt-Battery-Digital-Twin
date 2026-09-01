"""Telemetry Snapshot Model for Canonical Telemetry.

Defines the top-level immutable TelemetrySnapshot representing a complete,
strongly-typed observation of a battery system at a specific timestamp.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

from src.domain.battery.validation import validate_battery_identifier
from src.telemetry.enums import (
    CurrentFlowDirection,
    TelemetryQuality,
)
from src.telemetry.measurements import (
    CellTelemetry,
    ModuleTelemetry,
    TemperatureSensorTelemetry,
)
from src.telemetry.validation import (
    validate_current_telemetry,
    validate_fraction_telemetry,
    validate_non_negative_metric,
    validate_power_telemetry,
    validate_telemetry_timestamp,
    validate_temperature_telemetry,
    validate_voltage_telemetry,
)


@dataclass(frozen=True)
class TelemetrySnapshot:
    """Canonical, strongly-typed snapshot of battery telemetry at a single point in time.

    Supports partial telemetry (e.g. only voltage/current) or comprehensive multi-cell
    BMS observations. Missing optional measurements are represented as None, NOT zero.
    """

    # Identifiers & Metadata
    snapshot_id: str
    system_id: str
    timestamp_ns: int
    observed_at_ns: Optional[int] = None
    sequence_number: Optional[int] = None

    # Macro Electrical Observations (Optional)
    pack_voltage_v: Optional[float] = None
    pack_current_a: Optional[float] = None
    pack_power_w: Optional[float] = None

    # Macro Thermal Observations (Optional)
    ambient_temperature_c: Optional[float] = None
    max_cell_temperature_c: Optional[float] = None
    min_cell_temperature_c: Optional[float] = None
    avg_cell_temperature_c: Optional[float] = None

    # Macro State & Operational Indicators (Optional)
    soc_fraction: Optional[float] = None
    soh_fraction: Optional[float] = None
    charge_discharge_state: Optional[CurrentFlowDirection] = None
    bms_operational_state: Optional[str] = None

    # Capacity & Energy (Optional)
    remaining_capacity_ah: Optional[float] = None
    available_energy_wh: Optional[float] = None
    cumulative_charge_ah: Optional[float] = None
    cumulative_discharge_ah: Optional[float] = None

    # Hierarchical Structural Telemetry
    modules: Tuple[ModuleTelemetry, ...] = field(default_factory=tuple)
    cell_telemetries: Tuple[CellTelemetry, ...] = field(default_factory=tuple)
    discrete_temperatures: Tuple[TemperatureSensorTelemetry, ...] = field(default_factory=tuple)

    # Telemetry Quality & Metadata
    quality: TelemetryQuality = TelemetryQuality.VALID
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_battery_identifier(self.snapshot_id, "snapshot_id")
        validate_battery_identifier(self.system_id, "system_id")
        validate_telemetry_timestamp(self.timestamp_ns)
        if self.observed_at_ns is not None:
            validate_telemetry_timestamp(self.observed_at_ns)

        # Electrical validation
        validate_voltage_telemetry(self.pack_voltage_v, "pack_voltage_v")
        validate_current_telemetry(self.pack_current_a, "pack_current_a")
        validate_power_telemetry(self.pack_power_w, "pack_power_w")

        # Thermal validation
        validate_temperature_telemetry(self.ambient_temperature_c, "ambient_temperature_c")
        validate_temperature_telemetry(self.max_cell_temperature_c, "max_cell_temperature_c")
        validate_temperature_telemetry(self.min_cell_temperature_c, "min_cell_temperature_c")
        validate_temperature_telemetry(self.avg_cell_temperature_c, "avg_cell_temperature_c")

        # State validation
        validate_fraction_telemetry(self.soc_fraction, "soc_fraction")
        validate_fraction_telemetry(self.soh_fraction, "soh_fraction")

        # Capacity validation
        validate_non_negative_metric(self.remaining_capacity_ah, "remaining_capacity_ah")
        validate_non_negative_metric(self.available_energy_wh, "available_energy_wh")
        validate_non_negative_metric(self.cumulative_charge_ah, "cumulative_charge_ah")
        validate_non_negative_metric(self.cumulative_discharge_ah, "cumulative_discharge_ah")

    @property
    def timestamp_seconds(self) -> float:
        """Returns the measurement timestamp in fractional seconds."""
        return self.timestamp_ns / 1_000_000_000.0

    @property
    def total_cell_count(self) -> int:
        """Returns the total number of cell telemetry entries across direct cells and modules."""
        module_cells = sum(m.cell_count for m in self.modules)
        return len(self.cell_telemetries) + module_cells

    def get_all_cell_voltages(self) -> dict[str, float]:
        """Extracts a flat dictionary mapping cell_id -> voltage_v for all present cell voltages."""
        voltages: dict[str, float] = {}
        for cell in self.cell_telemetries:
            if cell.voltage_v is not None:
                voltages[cell.cell_id] = cell.voltage_v
        for mod in self.modules:
            for cell in mod.cell_telemetries:
                if cell.voltage_v is not None:
                    voltages[cell.cell_id] = cell.voltage_v
        return voltages

    def get_all_cell_temperatures(self) -> dict[str, float]:
        """Extracts a flat dictionary mapping cell_id -> temperature_c for all present cell temps."""
        temps: dict[str, float] = {}
        for cell in self.cell_telemetries:
            if cell.temperature_c is not None:
                temps[cell.cell_id] = cell.temperature_c
        for mod in self.modules:
            for cell in mod.cell_telemetries:
                if cell.temperature_c is not None:
                    temps[cell.cell_id] = cell.temperature_c
        return temps

    def max_cell_voltage(self) -> Optional[float]:
        """Returns the maximum cell voltage among all cell telemetry entries, or None."""
        voltages = [c.voltage_v for c in self.cell_telemetries if c.voltage_v is not None]
        for m in self.modules:
            voltages.extend(c.voltage_v for c in m.cell_telemetries if c.voltage_v is not None)
        return max(voltages) if voltages else None

    def min_cell_voltage(self) -> Optional[float]:
        """Returns the minimum cell voltage among all cell telemetry entries, or None."""
        voltages = [c.voltage_v for c in self.cell_telemetries if c.voltage_v is not None]
        for m in self.modules:
            voltages.extend(c.voltage_v for c in m.cell_telemetries if c.voltage_v is not None)
        return min(voltages) if voltages else None

    def cell_voltage_delta_v(self) -> Optional[float]:
        """Returns the difference between maximum and minimum cell voltages ($V_{max} - V_{min}$)."""
        v_max = self.max_cell_voltage()
        v_min = self.min_cell_voltage()
        if v_max is not None and v_min is not None:
            return v_max - v_min
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serializes the snapshot to a deterministic dictionary of primitive types."""
        return {
            "snapshot_id": self.snapshot_id,
            "system_id": self.system_id,
            "timestamp_ns": self.timestamp_ns,
            "observed_at_ns": self.observed_at_ns,
            "sequence_number": self.sequence_number,
            "pack_voltage_v": self.pack_voltage_v,
            "pack_current_a": self.pack_current_a,
            "pack_power_w": self.pack_power_w,
            "ambient_temperature_c": self.ambient_temperature_c,
            "max_cell_temperature_c": self.max_cell_temperature_c,
            "min_cell_temperature_c": self.min_cell_temperature_c,
            "avg_cell_temperature_c": self.avg_cell_temperature_c,
            "soc_fraction": self.soc_fraction,
            "soh_fraction": self.soh_fraction,
            "charge_discharge_state": (
                self.charge_discharge_state.value if self.charge_discharge_state else None
            ),
            "bms_operational_state": self.bms_operational_state,
            "remaining_capacity_ah": self.remaining_capacity_ah,
            "available_energy_wh": self.available_energy_wh,
            "cumulative_charge_ah": self.cumulative_charge_ah,
            "cumulative_discharge_ah": self.cumulative_discharge_ah,
            "quality": self.quality.value,
            "metadata": dict(self.metadata),
            "direct_cells": [
                {
                    "cell_id": c.cell_id,
                    "voltage_v": c.voltage_v,
                    "temperature_c": c.temperature_c,
                    "internal_resistance_mohm": c.internal_resistance_mohm,
                    "soc_fraction": c.soc_fraction,
                    "quality": c.quality.value,
                }
                for c in self.cell_telemetries
            ],
            "modules": [
                {
                    "module_id": m.module_id,
                    "voltage_v": m.voltage_v,
                    "temperature_c": m.temperature_c,
                    "quality": m.quality.value,
                    "cells": [
                        {
                            "cell_id": c.cell_id,
                            "voltage_v": c.voltage_v,
                            "temperature_c": c.temperature_c,
                            "quality": c.quality.value,
                        }
                        for c in m.cell_telemetries
                    ],
                    "temperature_sensors": [
                        {
                            "sensor_id": s.sensor_id,
                            "temperature_c": s.temperature_c,
                            "quality": s.quality.value,
                        }
                        for s in m.temperature_sensors
                    ],
                }
                for m in self.modules
            ],
            "discrete_temperatures": [
                {
                    "sensor_id": s.sensor_id,
                    "temperature_c": s.temperature_c,
                    "quality": s.quality.value,
                }
                for s in self.discrete_temperatures
            ],
        }
