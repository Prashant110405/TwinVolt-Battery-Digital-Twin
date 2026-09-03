"""Physics-Informed Anomaly Detection and Safety Monitoring.

Analyzes physical residuals, rate-of-rise signatures, cell dispersion, and sensor bias
to identify battery anomalies, sensor drift, and safety precursors in real time.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence

from src.runtime.config import RuntimeConfig
from src.runtime.synchronizer import TwinSyncOutput

SEVERITY_ORDER = {
    "NONE": 0,
    "INFO": 1,
    "WARNING": 2,
    "CRITICAL": 3,
    "EMERGENCY": 4,
}


@dataclass(frozen=True)
class DetectedAnomaly:
    """Strongly-typed container representing a single identified physical anomaly."""

    anomaly_type: str
    severity: str
    observed_value: float
    expected_value: float
    residual: float
    description: str
    timestamp_ns: int
    cell_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes detected anomaly to dictionary."""
        return {
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "observed_value": self.observed_value,
            "expected_value": self.expected_value,
            "residual": self.residual,
            "description": self.description,
            "timestamp_ns": self.timestamp_ns,
            "cell_id": self.cell_id,
        }


@dataclass(frozen=True)
class AnomalyReport:
    """Comprehensive anomaly assessment produced for a single Digital Twin cycle."""

    anomalies: tuple[DetectedAnomaly, ...] = field(default_factory=tuple)
    max_severity: str = "NONE"

    @property
    def has_anomalies(self) -> bool:
        """True if one or more anomalies were detected."""
        return len(self.anomalies) > 0

    def to_dict(self) -> dict[str, Any]:
        """Serializes anomaly report to dictionary."""
        return {
            "has_anomalies": self.has_anomalies,
            "max_severity": self.max_severity,
            "anomalies": [a.to_dict() for a in self.anomalies],
        }


class PhysicsAnomalyDetector:
    """Physics-Informed Residual and Safety Anomaly Detection Engine.

    Evaluates dual-track co-simulation residuals, thermal rate-of-rise ($dT/dt$),
    cell dispersion, and rolling statistical bias to identify anomalies.
    """

    def __init__(self, config: Optional[RuntimeConfig] = None) -> None:
        self._config = config or RuntimeConfig()
        self._voltage_residuals: list[float] = []
        self._prev_temp_c: Optional[float] = None
        self._prev_temp_ts_ns: Optional[int] = None

    @property
    def config(self) -> RuntimeConfig:
        """Attached runtime configuration."""
        return self._config

    def evaluate(self, sync_output: TwinSyncOutput) -> AnomalyReport:
        """Evaluates a completed synchronization cycle for physical anomalies and faults.

        Args:
            sync_output: Output from TwinSynchronizer containing observations, states, and residuals.

        Returns:
            AnomalyReport containing any detected anomalies and maximum severity level.
        """
        if not isinstance(sync_output, TwinSyncOutput):
            raise TypeError(f"Expected TwinSyncOutput, got {type(sync_output).__name__}.")

        anomalies: list[DetectedAnomaly] = []
        ts_ns = sync_output.timestamp_ns
        tolerances = self._config.tolerances
        thresholds = self._config.anomaly_thresholds

        # ----------------------------------------------------------------------
        # 1. Terminal Voltage Residual Divergence
        # ----------------------------------------------------------------------
        res_v = sync_output.residuals.get("voltage_residual_v")
        if res_v is not None and not (math.isnan(res_v) or math.isinf(res_v)):
            abs_res_v = abs(res_v)
            obs_v = sync_output.telemetry.pack_voltage_v or 0.0
            exp_v = sync_output.model_output.terminal_voltage_v

            if abs_res_v >= tolerances.voltage_critical_threshold_v:
                anomalies.append(
                    DetectedAnomaly(
                        anomaly_type="VOLTAGE_DIVERGENCE",
                        severity="CRITICAL",
                        observed_value=obs_v,
                        expected_value=exp_v,
                        residual=res_v,
                        description=(
                            f"Critical terminal voltage residual: |{res_v:.4f}V| >= "
                            f"{tolerances.voltage_critical_threshold_v:.4f}V."
                        ),
                        timestamp_ns=ts_ns,
                    )
                )
            elif abs_res_v >= tolerances.voltage_warning_threshold_v:
                anomalies.append(
                    DetectedAnomaly(
                        anomaly_type="VOLTAGE_DIVERGENCE",
                        severity="WARNING",
                        observed_value=obs_v,
                        expected_value=exp_v,
                        residual=res_v,
                        description=(
                            f"Terminal voltage residual warning: |{res_v:.4f}V| >= "
                            f"{tolerances.voltage_warning_threshold_v:.4f}V."
                        ),
                        timestamp_ns=ts_ns,
                    )
                )

            # Record rolling voltage residual for sensor drift evaluation
            self._voltage_residuals.append(res_v)
            if len(self._voltage_residuals) > thresholds.sensor_drift_window_size:
                self._voltage_residuals.pop(0)

        # ----------------------------------------------------------------------
        # 2. Temperature Residual Divergence
        # ----------------------------------------------------------------------
        res_t = sync_output.residuals.get("temp_residual_c")
        if res_t is not None and not (math.isnan(res_t) or math.isinf(res_t)):
            abs_res_t = abs(res_t)
            obs_t = (
                sync_output.telemetry.avg_cell_temperature_c
                if sync_output.telemetry.avg_cell_temperature_c is not None
                else (sync_output.telemetry.max_cell_temperature_c or 0.0)
            )
            exp_t = sync_output.model_output.state.temperature_c

            if abs_res_t >= tolerances.temperature_critical_threshold_c:
                anomalies.append(
                    DetectedAnomaly(
                        anomaly_type="THERMAL_DIVERGENCE",
                        severity="CRITICAL",
                        observed_value=obs_t,
                        expected_value=exp_t,
                        residual=res_t,
                        description=(
                            f"Critical thermal residual: |{res_t:.2f}°C| >= "
                            f"{tolerances.temperature_critical_threshold_c:.2f}°C."
                        ),
                        timestamp_ns=ts_ns,
                    )
                )
            elif abs_res_t >= tolerances.temperature_warning_threshold_c:
                anomalies.append(
                    DetectedAnomaly(
                        anomaly_type="THERMAL_DIVERGENCE",
                        severity="WARNING",
                        observed_value=obs_t,
                        expected_value=exp_t,
                        residual=res_t,
                        description=(
                            f"Thermal residual warning: |{res_t:.2f}°C| >= "
                            f"{tolerances.temperature_warning_threshold_c:.2f}°C."
                        ),
                        timestamp_ns=ts_ns,
                    )
                )

        # ----------------------------------------------------------------------
        # 3. Critical Thermal Safety & Thermal Runaway Precursors
        # ----------------------------------------------------------------------
        max_t = (
            sync_output.telemetry.max_cell_temperature_c
            if sync_output.telemetry.max_cell_temperature_c is not None
            else sync_output.telemetry.avg_cell_temperature_c
        )
        if max_t is not None and not (math.isnan(max_t) or math.isinf(max_t)):
            # Absolute temperature threshold check
            if max_t >= thresholds.critical_thermal_cutoff_c:
                anomalies.append(
                    DetectedAnomaly(
                        anomaly_type="THERMAL_RUNAWAY_PRECURSOR",
                        severity="EMERGENCY",
                        observed_value=max_t,
                        expected_value=thresholds.critical_thermal_cutoff_c,
                        residual=max_t - thresholds.critical_thermal_cutoff_c,
                        description=(
                            f"Battery temperature ({max_t:.1f}°C) exceeded critical emergency "
                            f"cutoff threshold ({thresholds.critical_thermal_cutoff_c:.1f}°C)."
                        ),
                        timestamp_ns=ts_ns,
                    )
                )

            # Thermal rate-of-rise check (dT/dt)
            if self._prev_temp_c is not None and self._prev_temp_ts_ns is not None:
                dt_temp_s = (ts_ns - self._prev_temp_ts_ns) / 1_000_000_000.0
                if dt_temp_s > 0:
                    dt_rate = (max_t - self._prev_temp_c) / dt_temp_s
                    if dt_rate >= thresholds.max_temperature_rate_c_per_s:
                        anomalies.append(
                            DetectedAnomaly(
                                anomaly_type="THERMAL_RUNAWAY_PRECURSOR",
                                severity="CRITICAL",
                                observed_value=dt_rate,
                                expected_value=thresholds.max_temperature_rate_c_per_s,
                                residual=dt_rate - thresholds.max_temperature_rate_c_per_s,
                                description=(
                                    f"Rapid temperature rise rate ({dt_rate:.3f}°C/s) exceeded "
                                    f"safety threshold ({thresholds.max_temperature_rate_c_per_s:.3f}°C/s)."
                                ),
                                timestamp_ns=ts_ns,
                            )
                        )

            self._prev_temp_c = max_t
            self._prev_temp_ts_ns = ts_ns

        # ----------------------------------------------------------------------
        # 4. Multi-Cell Voltage Imbalance Dispersion
        # ----------------------------------------------------------------------
        delta_v = sync_output.telemetry.cell_voltage_delta_v()
        if delta_v is not None and not (math.isnan(delta_v) or math.isinf(delta_v)):
            if delta_v >= tolerances.cell_voltage_delta_max_v:
                anomalies.append(
                    DetectedAnomaly(
                        anomaly_type="CELL_IMBALANCE_DIVERGENCE",
                        severity="WARNING",
                        observed_value=delta_v,
                        expected_value=tolerances.cell_voltage_delta_max_v,
                        residual=delta_v - tolerances.cell_voltage_delta_max_v,
                        description=(
                            f"Cell voltage dispersion ({delta_v * 1000.0:.1f}mV) exceeded "
                            f"maximum threshold ({tolerances.cell_voltage_delta_max_v * 1000.0:.1f}mV)."
                        ),
                        timestamp_ns=ts_ns,
                    )
                )

        # ----------------------------------------------------------------------
        # 5. Sensor Drift / Continuous Residual Bias
        # ----------------------------------------------------------------------
        if len(self._voltage_residuals) >= thresholds.min_samples_for_drift_detection:
            mean_bias = sum(self._voltage_residuals) / len(self._voltage_residuals)
            if abs(mean_bias) >= thresholds.sensor_drift_mean_bias_v:
                anomalies.append(
                    DetectedAnomaly(
                        anomaly_type="SENSOR_DRIFT",
                        severity="WARNING",
                        observed_value=mean_bias,
                        expected_value=0.0,
                        residual=mean_bias,
                        description=(
                            f"Persistent voltage measurement bias detected: mean error = {mean_bias:.4f}V "
                            f"over {len(self._voltage_residuals)} samples."
                        ),
                        timestamp_ns=ts_ns,
                    )
                )

        # ----------------------------------------------------------------------
        # 6. State of Charge Discrepancy
        # ----------------------------------------------------------------------
        soc_disc = sync_output.residuals.get("soc_discrepancy")
        if soc_disc is not None and not (math.isnan(soc_disc) or math.isinf(soc_disc)):
            abs_soc_disc = abs(soc_disc)
            if abs_soc_disc >= tolerances.soc_critical_threshold:
                anomalies.append(
                    DetectedAnomaly(
                        anomaly_type="SOC_DIVERGENCE",
                        severity="CRITICAL",
                        observed_value=sync_output.model_output.state.soc_fraction,
                        expected_value=(
                            sync_output.estimation_output.state.soc_fraction
                            if sync_output.estimation_output
                            else 0.0
                        ),
                        residual=soc_disc,
                        description=(
                            f"Critical SOC divergence between model and estimator: |{soc_disc * 100.0:.1f}%| >= "
                            f"{tolerances.soc_critical_threshold * 100.0:.1f}%."
                        ),
                        timestamp_ns=ts_ns,
                    )
                )
            elif abs_soc_disc >= tolerances.soc_warning_threshold:
                anomalies.append(
                    DetectedAnomaly(
                        anomaly_type="SOC_DIVERGENCE",
                        severity="WARNING",
                        observed_value=sync_output.model_output.state.soc_fraction,
                        expected_value=(
                            sync_output.estimation_output.state.soc_fraction
                            if sync_output.estimation_output
                            else 0.0
                        ),
                        residual=soc_disc,
                        description=(
                            f"SOC divergence warning between model and estimator: |{soc_disc * 100.0:.1f}%| >= "
                            f"{tolerances.soc_warning_threshold * 100.0:.1f}%."
                        ),
                        timestamp_ns=ts_ns,
                    )
                )

        # Calculate max severity
        max_sev = "NONE"
        max_score = 0
        for a in anomalies:
            score = SEVERITY_ORDER.get(a.severity, 0)
            if score > max_score:
                max_score = score
                max_sev = a.severity

        return AnomalyReport(anomalies=tuple(anomalies), max_severity=max_sev)

    def reset(self) -> None:
        """Resets rolling statistical buffers and previous temperature tracking."""
        self._voltage_residuals.clear()
        self._prev_temp_c = None
        self._prev_temp_ts_ns = None
