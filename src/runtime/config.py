"""Runtime Configuration and Threshold Parameters.

Defines immutable configuration models for Digital Twin runtime execution,
residual tolerances, anomaly detection thresholds, and synchronizer behavior.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional

from src.runtime.exceptions import RuntimeInitializationError


@dataclass(frozen=True)
class ResidualTolerances:
    """Tolerances for physical observation vs model simulation residuals.

    All units in standard SI:
    - voltage_warning_threshold_v: Maximum expected voltage error before warning (V).
    - voltage_critical_threshold_v: Voltage residual triggering critical alert (V).
    - temperature_warning_threshold_c: Temperature residual warning threshold (°C).
    - temperature_critical_threshold_c: Temperature residual critical alert threshold (°C).
    - soc_warning_threshold: Model vs Estimator SOC fraction discrepancy warning threshold.
    - soc_critical_threshold: Model vs Estimator SOC fraction discrepancy critical threshold.
    - cell_voltage_delta_max_v: Maximum acceptable cell-to-cell voltage dispersion (V).
    """

    voltage_warning_threshold_v: float = 0.05
    voltage_critical_threshold_v: float = 0.15
    temperature_warning_threshold_c: float = 3.0
    temperature_critical_threshold_c: float = 8.0
    soc_warning_threshold: float = 0.05
    soc_critical_threshold: float = 0.15
    cell_voltage_delta_max_v: float = 0.08

    def __post_init__(self) -> None:
        for name, val in [
            ("voltage_warning_threshold_v", self.voltage_warning_threshold_v),
            ("voltage_critical_threshold_v", self.voltage_critical_threshold_v),
            ("temperature_warning_threshold_c", self.temperature_warning_threshold_c),
            ("temperature_critical_threshold_c", self.temperature_critical_threshold_c),
            ("soc_warning_threshold", self.soc_warning_threshold),
            ("soc_critical_threshold", self.soc_critical_threshold),
            ("cell_voltage_delta_max_v", self.cell_voltage_delta_max_v),
        ]:
            if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                raise RuntimeInitializationError(f"{name} must be a finite number, got {val}.")
            if val <= 0.0:
                raise RuntimeInitializationError(f"{name} must be strictly positive, got {val}.")

        if self.voltage_warning_threshold_v >= self.voltage_critical_threshold_v:
            raise RuntimeInitializationError(
                f"voltage_warning_threshold_v ({self.voltage_warning_threshold_v}) must be < "
                f"voltage_critical_threshold_v ({self.voltage_critical_threshold_v})."
            )
        if self.temperature_warning_threshold_c >= self.temperature_critical_threshold_c:
            raise RuntimeInitializationError(
                f"temperature_warning_threshold_c ({self.temperature_warning_threshold_c}) must be < "
                f"temperature_critical_threshold_c ({self.temperature_critical_threshold_c})."
            )
        if self.soc_warning_threshold >= self.soc_critical_threshold:
            raise RuntimeInitializationError(
                f"soc_warning_threshold ({self.soc_warning_threshold}) must be < "
                f"soc_critical_threshold ({self.soc_critical_threshold})."
            )

    def to_dict(self) -> dict[str, float]:
        """Serializes tolerances to dictionary."""
        return {
            "voltage_warning_threshold_v": self.voltage_warning_threshold_v,
            "voltage_critical_threshold_v": self.voltage_critical_threshold_v,
            "temperature_warning_threshold_c": self.temperature_warning_threshold_c,
            "temperature_critical_threshold_c": self.temperature_critical_threshold_c,
            "soc_warning_threshold": self.soc_warning_threshold,
            "soc_critical_threshold": self.soc_critical_threshold,
            "cell_voltage_delta_max_v": self.cell_voltage_delta_max_v,
        }


@dataclass(frozen=True)
class AnomalyThresholds:
    """Thresholds governing physics-informed anomaly and safety fault detection.

    All units in standard SI:
    - critical_thermal_cutoff_c: Absolute thermal limit triggering emergency alert (°C).
    - max_temperature_rate_c_per_s: Maximum allowable rate-of-temperature-rise (°C/s).
    - internal_short_voltage_drop_v: Sudden voltage drop threshold indicating potential internal short (V).
    - sensor_drift_window_size: Number of consecutive samples in rolling window for bias detection.
    - sensor_drift_mean_bias_v: Mean voltage residual bias triggering sensor drift warning (V).
    - min_samples_for_drift_detection: Minimum samples required before evaluating sensor drift.
    """

    critical_thermal_cutoff_c: float = 65.0
    max_temperature_rate_c_per_s: float = 0.5
    internal_short_voltage_drop_v: float = 0.10
    sensor_drift_window_size: int = 10
    sensor_drift_mean_bias_v: float = 0.03
    min_samples_for_drift_detection: int = 5

    def __post_init__(self) -> None:
        if self.critical_thermal_cutoff_c <= 0.0:
            raise RuntimeInitializationError(
                f"critical_thermal_cutoff_c must be positive, got {self.critical_thermal_cutoff_c}."
            )
        if self.max_temperature_rate_c_per_s <= 0.0:
            raise RuntimeInitializationError(
                f"max_temperature_rate_c_per_s must be positive, got {self.max_temperature_rate_c_per_s}."
            )
        if self.internal_short_voltage_drop_v <= 0.0:
            raise RuntimeInitializationError(
                f"internal_short_voltage_drop_v must be positive, got {self.internal_short_voltage_drop_v}."
            )
        if self.sensor_drift_window_size < 2:
            raise RuntimeInitializationError(
                f"sensor_drift_window_size must be >= 2, got {self.sensor_drift_window_size}."
            )
        if self.sensor_drift_mean_bias_v <= 0.0:
            raise RuntimeInitializationError(
                f"sensor_drift_mean_bias_v must be positive, got {self.sensor_drift_mean_bias_v}."
            )
        if self.min_samples_for_drift_detection > self.sensor_drift_window_size:
            raise RuntimeInitializationError(
                f"min_samples_for_drift_detection ({self.min_samples_for_drift_detection}) cannot exceed "
                f"sensor_drift_window_size ({self.sensor_drift_window_size})."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes anomaly thresholds to dictionary."""
        return {
            "critical_thermal_cutoff_c": self.critical_thermal_cutoff_c,
            "max_temperature_rate_c_per_s": self.max_temperature_rate_c_per_s,
            "internal_short_voltage_drop_v": self.internal_short_voltage_drop_v,
            "sensor_drift_window_size": self.sensor_drift_window_size,
            "sensor_drift_mean_bias_v": self.sensor_drift_mean_bias_v,
            "min_samples_for_drift_detection": self.min_samples_for_drift_detection,
        }


@dataclass(frozen=True)
class RuntimeConfig:
    """Master configuration container for a DigitalTwinInstance execution environment."""

    system_id: str = "twin_system"
    default_dt_s: float = 1.0
    min_dt_s: float = 0.0001
    max_dt_s: float = 60.0
    strict_monotonicity: bool = True
    max_clock_skew_future_s: float = 10.0
    stale_timeout_s: float = 300.0
    auto_publish_events: bool = True
    auto_persist_records: bool = True
    enable_anomaly_detection: bool = True
    tolerances: ResidualTolerances = field(default_factory=ResidualTolerances)
    anomaly_thresholds: AnomalyThresholds = field(default_factory=AnomalyThresholds)

    def __post_init__(self) -> None:
        if not isinstance(self.system_id, str) or not self.system_id.strip():
            raise RuntimeInitializationError("system_id must be a non-empty string.")
        if self.default_dt_s <= 0.0:
            raise RuntimeInitializationError(
                f"default_dt_s must be strictly positive, got {self.default_dt_s}."
            )
        if self.min_dt_s <= 0.0:
            raise RuntimeInitializationError(
                f"min_dt_s must be strictly positive, got {self.min_dt_s}."
            )
        if self.max_dt_s <= self.min_dt_s:
            raise RuntimeInitializationError(
                f"max_dt_s ({self.max_dt_s}) must be greater than min_dt_s ({self.min_dt_s})."
            )
        if self.max_clock_skew_future_s < 0.0:
            raise RuntimeInitializationError(
                f"max_clock_skew_future_s cannot be negative, got {self.max_clock_skew_future_s}."
            )
        if self.stale_timeout_s <= 0.0:
            raise RuntimeInitializationError(
                f"stale_timeout_s must be strictly positive, got {self.stale_timeout_s}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes configuration to dictionary."""
        return {
            "system_id": self.system_id,
            "default_dt_s": self.default_dt_s,
            "min_dt_s": self.min_dt_s,
            "max_dt_s": self.max_dt_s,
            "strict_monotonicity": self.strict_monotonicity,
            "max_clock_skew_future_s": self.max_clock_skew_future_s,
            "stale_timeout_s": self.stale_timeout_s,
            "auto_publish_events": self.auto_publish_events,
            "auto_persist_records": self.auto_persist_records,
            "enable_anomaly_detection": self.enable_anomaly_detection,
            "tolerances": self.tolerances.to_dict(),
            "anomaly_thresholds": self.anomaly_thresholds.to_dict(),
        }
