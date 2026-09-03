"""Data types, configuration structures, and immutable report containers for Battery Model Validation.

Defines strongly-typed representations for validation states, signal provenance tiers,
statistical residual metrics, parameter evidence classifications, and validation window reports.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping, Optional, Sequence


class SignalProvenance(str, Enum):
    """Origin and classification of signals evaluated in validation metrics."""

    MEASURED = "MEASURED"                 # Direct physical sensor observation from telemetry
    MODEL_PREDICTED = "MODEL_PREDICTED"   # Output of deterministic physics/ECM simulation
    ESTIMATED = "ESTIMATED"               # Output of state observer (EKF, Coulomb Counter)
    DERIVED = "DERIVED"                   # Mathematically computed from other physical signals (e.g. V * I)
    MISSING = "MISSING"                   # Signal omitted from telemetry or unconfigured in model


class ModelValidationState(str, Enum):
    """Behavioral validation state of the Digital Twin model over an observation window."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"           # Window has < min_samples_per_window
    DATA_QUALITY_FAILED = "DATA_QUALITY_FAILED"       # Monotonicity failure, telemetry gap, invalid sensor
    EXCITATION_STEADY_STATE_ONLY = "EXCITATION_STEADY_STATE_ONLY" # Constant current: R0 evaluable, dynamic branches paused
    VALIDATING = "VALIDATING"                         # Active evaluation window in progress
    VALIDATED = "VALIDATED"                           # Residuals satisfy analytical thresholds under excitation
    DEGRADED = "DEGRADED"                             # Residuals exceed analytical thresholds
    UNAVAILABLE = "UNAVAILABLE"                       # Comparison signal not exposed by model


class ParameterEvidenceTier(str, Enum):
    """Strength of empirical evidence supporting an identified parameter snapshot."""

    EVIDENCE_STRONG = "EVIDENCE_STRONG"       # Meets bounds, low covariance, stable across windows, Delta_RMSE > 0
    EVIDENCE_MODERATE = "EVIDENCE_MODERATE"   # Valid bounds, acceptable covariance, steady-state excitation only
    EVIDENCE_WEAK = "EVIDENCE_WEAK"           # High covariance, parameter drift across windows, or Delta_RMSE <= 0
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED"   # Bound violation or numerical instability


@dataclass(frozen=True)
class ValidationConfig:
    """Configuration options governing behavioral model validation and residual analysis."""

    window_duration_s: float = 60.0                     # Target time duration per validation window [s]
    min_samples_per_window: int = 10                    # Minimum samples required to seal a valid window
    max_samples_per_window: int = 600                   # Maximum buffer limit per window
    max_dt_s: float = 5.0                               # Maximum step interval before gap interruption [s]

    # Analytical Thresholds (Configurable engineering thresholds, NOT universal physical constants)
    voltage_rmse_threshold_v: float = 0.030             # 30 mV target analytical voltage RMSE
    voltage_max_error_threshold_v: float = 0.080        # 80 mV target analytical max voltage error
    temp_rmse_threshold_c: float = 2.0                  # 2.0 °C target analytical temperature RMSE
    min_current_variance: float = 0.01                  # Minimum current variance for dynamic excitation [A^2]
    min_current_a: float = 0.1                          # Minimum current magnitude for ohmic evaluation [A]

    # Parameter Validation Criteria
    max_acceptable_drift_fraction: float = 0.05         # 5% max acceptable parameter drift across windows
    max_parameter_r0_covariance: float = 1.0            # Max acceptable R0 estimation variance

    def __post_init__(self) -> None:
        if self.window_duration_s <= 0.0:
            raise ValueError("window_duration_s must be strictly positive.")
        if self.min_samples_per_window <= 1:
            raise ValueError("min_samples_per_window must be greater than 1.")
        if self.max_samples_per_window < self.min_samples_per_window:
            raise ValueError("max_samples_per_window cannot be less than min_samples_per_window.")
        if self.voltage_rmse_threshold_v <= 0.0:
            raise ValueError("voltage_rmse_threshold_v must be strictly positive.")


@dataclass(frozen=True)
class SignalResidualMetrics:
    """Statistical residual tracking metrics computed for a paired physical signal over a window."""

    signal_name: str
    provenance_a: SignalProvenance
    provenance_b: SignalProvenance
    sample_count: int
    rmse: float
    mae: float
    max_error: float
    mean_bias_error: float
    std_dev: float
    r_squared: Optional[float] = None
    r_squared_diagnostic: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes signal residual metrics to dictionary."""
        return {
            "signal_name": self.signal_name,
            "provenance_a": self.provenance_a.value,
            "provenance_b": self.provenance_b.value,
            "sample_count": self.sample_count,
            "rmse": round(self.rmse, 6),
            "mae": round(self.mae, 6),
            "max_error": round(self.max_error, 6),
            "mean_bias_error": round(self.mean_bias_error, 6),
            "std_dev": round(self.std_dev, 6),
            "r_squared": round(self.r_squared, 6) if self.r_squared is not None else None,
            "r_squared_diagnostic": self.r_squared_diagnostic,
        }


@dataclass(frozen=True)
class ParameterValidationEvidence:
    """Multi-dimensional evidence evaluation for a candidate online identified parameter set."""

    timestamp_ns: int
    system_id: str
    tier: ParameterEvidenceTier
    bounds_satisfied: bool
    excitation_sufficient: bool
    covariance_acceptable: bool
    cross_window_drift_fraction: Optional[float] = None
    prospective_rmse_v: Optional[float] = None
    nominal_rmse_v: Optional[float] = None
    delta_rmse_v: Optional[float] = None
    evaluated_sample_count: int = 0
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes parameter validation evidence to dictionary."""
        return {
            "timestamp_ns": self.timestamp_ns,
            "system_id": self.system_id,
            "tier": self.tier.value,
            "bounds_satisfied": self.bounds_satisfied,
            "excitation_sufficient": self.excitation_sufficient,
            "covariance_acceptable": self.covariance_acceptable,
            "cross_window_drift_fraction": (
                round(self.cross_window_drift_fraction, 6)
                if self.cross_window_drift_fraction is not None
                else None
            ),
            "prospective_rmse_v": (
                round(self.prospective_rmse_v, 6) if self.prospective_rmse_v is not None else None
            ),
            "nominal_rmse_v": (
                round(self.nominal_rmse_v, 6) if self.nominal_rmse_v is not None else None
            ),
            "delta_rmse_v": (
                round(self.delta_rmse_v, 6) if self.delta_rmse_v is not None else None
            ),
            "evaluated_sample_count": self.evaluated_sample_count,
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(frozen=True)
class ValidationWindowReport:
    """Aggregated validation report representing a single observation window."""

    window_id: str
    system_id: str
    start_timestamp_ns: int
    end_timestamp_ns: int
    duration_s: float
    sample_count: int
    state: ModelValidationState
    voltage_metrics: Optional[SignalResidualMetrics] = None
    temperature_metrics: Optional[SignalResidualMetrics] = None
    soc_discrepancy_metrics: Optional[SignalResidualMetrics] = None
    current_consistency_max_a: Optional[float] = None
    power_consistency_max_w: Optional[float] = None
    parameter_evidence: Optional[ParameterValidationEvidence] = None
    data_quality_flags: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes validation window report to dictionary."""
        return {
            "window_id": self.window_id,
            "system_id": self.system_id,
            "start_timestamp_ns": self.start_timestamp_ns,
            "end_timestamp_ns": self.end_timestamp_ns,
            "duration_s": round(self.duration_s, 3),
            "sample_count": self.sample_count,
            "state": self.state.value,
            "voltage_metrics": self.voltage_metrics.to_dict() if self.voltage_metrics else None,
            "temperature_metrics": self.temperature_metrics.to_dict() if self.temperature_metrics else None,
            "soc_discrepancy_metrics": (
                self.soc_discrepancy_metrics.to_dict() if self.soc_discrepancy_metrics else None
            ),
            "current_consistency_max_a": (
                round(self.current_consistency_max_a, 6)
                if self.current_consistency_max_a is not None
                else None
            ),
            "power_consistency_max_w": (
                round(self.power_consistency_max_w, 4)
                if self.power_consistency_max_w is not None
                else None
            ),
            "parameter_evidence": (
                self.parameter_evidence.to_dict() if self.parameter_evidence else None
            ),
            "data_quality_flags": list(self.data_quality_flags),
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(frozen=True)
class ModelValidationReport:
    """Overall digital twin behavioral validation status including active and completed windows."""

    system_id: str
    timestamp_ns: int
    active_window: ValidationWindowReport
    latest_completed_window: Optional[ValidationWindowReport] = None
    parameter_evidence: Optional[ParameterValidationEvidence] = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes model validation report to dictionary."""
        return {
            "system_id": self.system_id,
            "timestamp_ns": self.timestamp_ns,
            "active_window": self.active_window.to_dict(),
            "latest_completed_window": (
                self.latest_completed_window.to_dict() if self.latest_completed_window else None
            ),
            "parameter_evidence": (
                self.parameter_evidence.to_dict() if self.parameter_evidence else None
            ),
        }
