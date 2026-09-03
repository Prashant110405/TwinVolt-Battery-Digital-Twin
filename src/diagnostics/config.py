"""Configuration models for Battery Diagnostics and Decision Support.

Encapsulates analytical engineering criteria, temporal persistence limits, and
operating-context classification thresholds.
"""

from dataclasses import dataclass
import math
from typing import Any, Mapping

from src.diagnostics.types import DiagnosticCategory


@dataclass(frozen=True)
class DiagnosticThresholdConfig:
    """Configurable analytical criteria governing fault detection, context classification, and hypothesis evaluation.

    IMPORTANT:
    These are analytical criteria for diagnostic hypothesis evaluation.
    They are NOT battery safety limits and must NOT be represented as physical safety cutoffs.
    """

    # Operating Context Classification Limits (Configurable Engineering Criteria)
    rest_current_threshold_a: float = 0.1             # Current magnitude below which system is considered resting [A]
    rest_min_duration_s: float = 10.0                 # Continuous duration below threshold required to confirm REST [s]
    cc_current_variance_threshold_a2: float = 0.01    # Maximum current variance for Constant Current classification [A^2]
    data_gap_threshold_s: float = 5.0                 # Step interval above which data is marked DATA_GAPPED [s]

    # Persistence & Debounce Limits
    persistence_debounce_steps: int = 5               # Steps required to transition ANOMALY_DETECTED -> SUSPECTED
    recovery_hysteresis_steps: int = 10               # Nominal steps required to transition to RECOVERED
    min_evidence_coverage_fraction: float = 0.50      # Minimum optional coverage required for MODERATE/STRONG evidence tier

    # Voltage & Resistance Analytical Criteria (Engineering Defaults)
    voltage_warning_residual_v: float = 0.030         # 30 mV analytical warning threshold [V]
    voltage_critical_residual_v: float = 0.080        # 80 mV analytical critical threshold [V]
    apparent_r0_growth_fraction: float = 0.15         # 15% increase in apparent R0 to support resistance growth hypothesis

    # Thermal Analytical Criteria (Engineering Defaults)
    thermal_rate_threshold_c_per_s: float = 0.05      # 0.05 °C/s temperature rise rate [°C/s]
    thermal_warning_residual_c: float = 2.0           # 2.0 °C thermal model discrepancy threshold [°C]
    thermal_critical_rate_c_per_s: float = 0.20       # 0.20 °C/s analytical critical thermal rise rate [°C/s]

    # Cell-Level Analytical Criteria (Conditional on cell telemetry)
    cell_voltage_imbalance_spread_v: float = 0.050    # 50 mV cell voltage spread during rest/charge [V]

    # Critical Advisory Analytical Criteria (Engineering Defaults)
    critical_evidence_score_threshold: float = 0.75   # Minimum empirical evidence score required for DIAGNOSED_CRITICAL advisory [0.0, 1.0]
    critical_min_corroborating_channels: int = 2      # Minimum distinct corroborating signal channels required
    diagnosis_evidence_score_threshold: float = 0.50  # Minimum empirical evidence score required for DIAGNOSED state [0.0, 1.0]
    critical_eligible_categories: tuple[DiagnosticCategory, ...] = (
        DiagnosticCategory.THERMAL,
        DiagnosticCategory.ELECTRICAL,
        DiagnosticCategory.CELL,
    )
    critical_eligible_hypothesis_ids: tuple[str, ...] = (
        "HYP_THERMAL_IMPAIRMENT",
        "HYP_APPARENT_OHMIC_GROWTH",
        "HYP_CELL_IMBALANCE",
    )

    # Degradation Analytical Criteria
    soh_fade_discrepancy_fraction: float = 0.05       # 5% discrepancy between capacity SOH and cycling model

    def __post_init__(self) -> None:
        # Validate non-NaN/non-Inf
        fields_to_check = (
            ("rest_current_threshold_a", self.rest_current_threshold_a),
            ("rest_min_duration_s", self.rest_min_duration_s),
            ("cc_current_variance_threshold_a2", self.cc_current_variance_threshold_a2),
            ("data_gap_threshold_s", self.data_gap_threshold_s),
            ("min_evidence_coverage_fraction", self.min_evidence_coverage_fraction),
            ("voltage_warning_residual_v", self.voltage_warning_residual_v),
            ("voltage_critical_residual_v", self.voltage_critical_residual_v),
            ("apparent_r0_growth_fraction", self.apparent_r0_growth_fraction),
            ("thermal_rate_threshold_c_per_s", self.thermal_rate_threshold_c_per_s),
            ("thermal_warning_residual_c", self.thermal_warning_residual_c),
            ("thermal_critical_rate_c_per_s", self.thermal_critical_rate_c_per_s),
            ("cell_voltage_imbalance_spread_v", self.cell_voltage_imbalance_spread_v),
            ("critical_evidence_score_threshold", self.critical_evidence_score_threshold),
            ("diagnosis_evidence_score_threshold", self.diagnosis_evidence_score_threshold),
            ("soh_fade_discrepancy_fraction", self.soh_fade_discrepancy_fraction),
        )
        for name, val in fields_to_check:
            if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                raise ValueError(f"{name} must be a finite float, got {val}.")

        # Positive thresholds
        if self.rest_current_threshold_a <= 0.0:
            raise ValueError("rest_current_threshold_a must be strictly positive.")
        if self.rest_min_duration_s <= 0.0:
            raise ValueError("rest_min_duration_s must be strictly positive.")
        if self.cc_current_variance_threshold_a2 <= 0.0:
            raise ValueError("cc_current_variance_threshold_a2 must be strictly positive.")
        if self.data_gap_threshold_s <= 0.0:
            raise ValueError("data_gap_threshold_s must be strictly positive.")
        if self.voltage_warning_residual_v <= 0.0:
            raise ValueError("voltage_warning_residual_v must be strictly positive.")
        if self.thermal_rate_threshold_c_per_s <= 0.0:
            raise ValueError("thermal_rate_threshold_c_per_s must be strictly positive.")
        if self.thermal_warning_residual_c <= 0.0:
            raise ValueError("thermal_warning_residual_c must be strictly positive.")
        if self.cell_voltage_imbalance_spread_v <= 0.0:
            raise ValueError("cell_voltage_imbalance_spread_v must be strictly positive.")

        # Step count and channel count validation
        if not isinstance(self.persistence_debounce_steps, int) or self.persistence_debounce_steps < 1:
            raise ValueError(f"persistence_debounce_steps must be integer >= 1, got {self.persistence_debounce_steps}.")
        if not isinstance(self.recovery_hysteresis_steps, int) or self.recovery_hysteresis_steps < 1:
            raise ValueError(f"recovery_hysteresis_steps must be integer >= 1, got {self.recovery_hysteresis_steps}.")
        if not isinstance(self.critical_min_corroborating_channels, int) or self.critical_min_corroborating_channels < 1:
            raise ValueError(f"critical_min_corroborating_channels must be integer >= 1, got {self.critical_min_corroborating_channels}.")

        # Fraction validation [0.0, 1.0]
        fraction_fields = (
            ("min_evidence_coverage_fraction", self.min_evidence_coverage_fraction),
            ("apparent_r0_growth_fraction", self.apparent_r0_growth_fraction),
            ("critical_evidence_score_threshold", self.critical_evidence_score_threshold),
            ("diagnosis_evidence_score_threshold", self.diagnosis_evidence_score_threshold),
            ("soh_fade_discrepancy_fraction", self.soh_fade_discrepancy_fraction),
        )
        for name, val in fraction_fields:
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{name} must be in range [0.0, 1.0], got {val}.")

        # Relative ordering checks
        if self.voltage_critical_residual_v < self.voltage_warning_residual_v:
            raise ValueError(
                f"voltage_critical_residual_v ({self.voltage_critical_residual_v}) "
                f"cannot be less than voltage_warning_residual_v ({self.voltage_warning_residual_v})."
            )
        if self.thermal_critical_rate_c_per_s < self.thermal_rate_threshold_c_per_s:
            raise ValueError(
                f"thermal_critical_rate_c_per_s ({self.thermal_critical_rate_c_per_s}) "
                f"cannot be less than thermal_rate_threshold_c_per_s ({self.thermal_rate_threshold_c_per_s})."
            )
        if self.critical_evidence_score_threshold < self.diagnosis_evidence_score_threshold:
            raise ValueError(
                f"critical_evidence_score_threshold ({self.critical_evidence_score_threshold}) "
                f"cannot be less than diagnosis_evidence_score_threshold ({self.diagnosis_evidence_score_threshold})."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes threshold configuration to dictionary."""
        return {
            "rest_current_threshold_a": self.rest_current_threshold_a,
            "rest_min_duration_s": self.rest_min_duration_s,
            "cc_current_variance_threshold_a2": self.cc_current_variance_threshold_a2,
            "data_gap_threshold_s": self.data_gap_threshold_s,
            "persistence_debounce_steps": self.persistence_debounce_steps,
            "recovery_hysteresis_steps": self.recovery_hysteresis_steps,
            "min_evidence_coverage_fraction": self.min_evidence_coverage_fraction,
            "voltage_warning_residual_v": self.voltage_warning_residual_v,
            "voltage_critical_residual_v": self.voltage_critical_residual_v,
            "apparent_r0_growth_fraction": self.apparent_r0_growth_fraction,
            "thermal_rate_threshold_c_per_s": self.thermal_rate_threshold_c_per_s,
            "thermal_warning_residual_c": self.thermal_warning_residual_c,
            "thermal_critical_rate_c_per_s": self.thermal_critical_rate_c_per_s,
            "cell_voltage_imbalance_spread_v": self.cell_voltage_imbalance_spread_v,
            "critical_evidence_score_threshold": self.critical_evidence_score_threshold,
            "critical_min_corroborating_channels": self.critical_min_corroborating_channels,
            "diagnosis_evidence_score_threshold": self.diagnosis_evidence_score_threshold,
            "critical_eligible_categories": [c.value for c in self.critical_eligible_categories],
            "critical_eligible_hypothesis_ids": list(self.critical_eligible_hypothesis_ids),
            "soh_fade_discrepancy_fraction": self.soh_fade_discrepancy_fraction,
        }
