"""Data types and immutable containers for battery degradation and State of Health (SOH).

Defines strongly-typed representations of cumulative stress accumulation, parametric
degradation metrics, and multi-dimensional battery health states.
"""

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Mapping, Optional


class CalibrationStatus(str, Enum):
    """Provenance and validation status of battery degradation and health models."""

    UNCALIBRATED_PARAMETRIC_MODEL = "UNCALIBRATED_PARAMETRIC_MODEL"
    CALIBRATED_LAB_REFERENCE = "CALIBRATED_LAB_REFERENCE"
    ONLINE_OBSERVER_ESTIMATED = "ONLINE_OBSERVER_ESTIMATED"


@dataclass(frozen=True)
class StressAccumulatorState:
    """Immutable snapshot of accumulated physical throughput and cyclic stress."""

    total_throughput_ah: float = 0.0
    charge_throughput_ah: float = 0.0
    discharge_throughput_ah: float = 0.0
    energy_throughput_wh: float = 0.0
    equivalent_full_cycles: float = 0.0
    total_elapsed_time_s: float = 0.0
    sample_count: int = 0
    last_timestamp_ns: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes stress metrics to dictionary."""
        return {
            "total_throughput_ah": round(self.total_throughput_ah, 4),
            "charge_throughput_ah": round(self.charge_throughput_ah, 4),
            "discharge_throughput_ah": round(self.discharge_throughput_ah, 4),
            "energy_throughput_wh": round(self.energy_throughput_wh, 4),
            "equivalent_full_cycles": round(self.equivalent_full_cycles, 4),
            "total_elapsed_time_s": round(self.total_elapsed_time_s, 2),
            "sample_count": self.sample_count,
            "last_timestamp_ns": self.last_timestamp_ns,
        }


@dataclass(frozen=True)
class DegradationMetrics:
    """Modeled capacity fade and internal resistance growth fractions."""

    calendar_capacity_fade_fraction: float = 0.0
    cycling_capacity_fade_fraction: float = 0.0
    total_capacity_fade_fraction: float = 0.0
    resistance_growth_fraction: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serializes degradation metrics to dictionary."""
        return {
            "calendar_capacity_fade_fraction": round(self.calendar_capacity_fade_fraction, 6),
            "cycling_capacity_fade_fraction": round(self.cycling_capacity_fade_fraction, 6),
            "total_capacity_fade_fraction": round(self.total_capacity_fade_fraction, 6),
            "resistance_growth_fraction": round(self.resistance_growth_fraction, 6),
        }


@dataclass(frozen=True)
class BatteryHealthState:
    """Comprehensive battery State of Health (SOH) representation.

    Distinguishes measured throughput, modeled capacity fade, and resistance degradation.
    """

    timestamp_ns: int
    system_id: str
    soh_capacity_fraction: float
    soh_resistance_fraction: Optional[float]
    soh_unified_fraction: float
    cumulative_throughput_ah: float
    cumulative_energy_throughput_wh: float
    equivalent_full_cycles: float
    estimated_capacity_ah: float
    estimated_series_resistance_ohm: Optional[float]
    capacity_fade_fraction: float
    resistance_growth_fraction: float
    calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED_PARAMETRIC_MODEL
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes health state to dictionary for REST and WebSocket serialization."""
        return {
            "timestamp_ns": self.timestamp_ns,
            "system_id": self.system_id,
            "soh_capacity_fraction": round(self.soh_capacity_fraction, 4),
            "soh_resistance_fraction": round(self.soh_resistance_fraction, 4) if self.soh_resistance_fraction is not None else None,
            "soh_unified_fraction": round(self.soh_unified_fraction, 4),
            "cumulative_throughput_ah": round(self.cumulative_throughput_ah, 4),
            "cumulative_energy_throughput_wh": round(self.cumulative_energy_throughput_wh, 4),
            "equivalent_full_cycles": round(self.equivalent_full_cycles, 4),
            "estimated_capacity_ah": round(self.estimated_capacity_ah, 4),
            "estimated_series_resistance_ohm": round(self.estimated_series_resistance_ohm, 6) if self.estimated_series_resistance_ohm is not None else None,
            "capacity_fade_fraction": round(self.capacity_fade_fraction, 6),
            "resistance_growth_fraction": round(self.resistance_growth_fraction, 6),
            "calibration_status": self.calibration_status.value,
            "metadata": dict(self.metadata),
        }
