"""Diagnostic Root-Cause Hypothesis Definitions and Rule Catalog.

Defines the abstract base hypothesis contract and standard built-in hypotheses across
all diagnostic categories: SENSOR, MODEL, ELECTRICAL, THERMAL, CELL, and DEGRADATION.
"""

from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional, Sequence

from src.diagnostics.config import DiagnosticThresholdConfig
from src.diagnostics.evidence import EvidenceScoringEngine
from src.diagnostics.types import (
    DiagnosticCategory,
    DiagnosticEvidenceItem,
    EvidenceEvaluationStatus,
    OperatingContext,
    RootCauseHypothesis,
)
from src.validation.types import SignalProvenance


class AbstractDiagnosticHypothesis(ABC):
    """Abstract base contract for an explainable battery diagnostic root-cause hypothesis."""

    def __init__(
        self,
        hypothesis_id: str,
        title: str,
        category: DiagnosticCategory,
        required_signals: Sequence[str],
        optional_signals: Sequence[str],
        untestable_confounds: Sequence[str],
        suggested_investigations: Sequence[str],
        total_possible_supporting_weight: float = 1.0,
    ) -> None:
        if not hypothesis_id or not isinstance(hypothesis_id, str):
            raise ValueError("hypothesis_id must be a non-empty string.")
        if not title or not isinstance(title, str):
            raise ValueError("title must be a non-empty string.")
        if not isinstance(category, DiagnosticCategory):
            raise TypeError(f"Expected DiagnosticCategory, got {type(category).__name__}.")
        if total_possible_supporting_weight <= 0.0:
            raise ValueError("total_possible_supporting_weight must be strictly positive.")

        self._hypothesis_id = hypothesis_id
        self._title = title
        self._category = category
        self._required_signals = tuple(required_signals)
        self._optional_signals = tuple(optional_signals)
        self._untestable_confounds = tuple(untestable_confounds)
        self._suggested_investigations = tuple(suggested_investigations)
        self._total_possible_supporting_weight = float(total_possible_supporting_weight)

    @property
    def hypothesis_id(self) -> str:
        """Unique identifier of the hypothesis."""
        return self._hypothesis_id

    @property
    def title(self) -> str:
        """Human-readable hypothesis title."""
        return self._title

    @property
    def category(self) -> DiagnosticCategory:
        """Orthogonal diagnostic category."""
        return self._category

    @property
    def required_signals(self) -> tuple[str, ...]:
        """Tuple of canonical signal names required for evaluability."""
        return self._required_signals

    @property
    def optional_signals(self) -> tuple[str, ...]:
        """Tuple of canonical optional signal names."""
        return self._optional_signals

    @property
    def untestable_confounds(self) -> tuple[str, ...]:
        """Physically indistinguishable alternative physical causes."""
        return self._untestable_confounds

    @property
    def suggested_investigations(self) -> tuple[str, ...]:
        """Recommended operator inspection and test steps."""
        return self._suggested_investigations

    @property
    def total_possible_supporting_weight(self) -> float:
        """Configured maximum possible supporting weight."""
        return self._total_possible_supporting_weight

    def evaluate(
        self,
        evidence_items: Sequence[DiagnosticEvidenceItem],
        context: OperatingContext,
        config: Optional[DiagnosticThresholdConfig] = None,
    ) -> RootCauseHypothesis:
        """Evaluates empirical evidence items against this hypothesis rule catalog.

        Args:
            evidence_items: Sequence of evaluated DiagnosticEvidenceItem instances.
            context: Active battery operating context.
            config: Optional threshold configuration.

        Returns:
            RootCauseHypothesis populated with evidence score, coverage, and categorized evidence.
        """
        cfg = config or DiagnosticThresholdConfig()

        score_result = EvidenceScoringEngine.evaluate_evidence(
            evidence_items=evidence_items,
            required_signals=self._required_signals,
            optional_signals=self._optional_signals,
            total_possible_supporting_weight=self._total_possible_supporting_weight,
            config=cfg,
        )

        return RootCauseHypothesis(
            hypothesis_id=self._hypothesis_id,
            title=self._title,
            category=self._category,
            evidence_score=score_result.evidence_score,
            confidence_level=score_result.confidence_level,
            required_signal_coverage=score_result.required_signal_coverage,
            optional_signal_coverage=score_result.optional_signal_coverage,
            supporting_evidence=score_result.supporting_evidence,
            contraindicating_evidence=score_result.contraindicating_evidence,
            untestable_confounds=self._untestable_confounds,
            suggested_investigations=self._suggested_investigations,
        )


# ==============================================================================
# Standard Built-In Hypothesis Implementations
# ==============================================================================

class SensorDriftHypothesis(AbstractDiagnosticHypothesis):
    """Hypothesis evaluating empirical evidence consistent with sensor offset or calibration drift."""

    def __init__(self) -> None:
        super().__init__(
            hypothesis_id="HYP_SENSOR_DRIFT",
            title="Sensor Zero-Point Calibration Drift or Reference Offset",
            category=DiagnosticCategory.SENSOR,
            required_signals=("pack_voltage_v", "pack_current_a"),
            optional_signals=("avg_cell_temperature_c", "ocv_v"),
            untestable_confounds=(
                "Internal chemical self-discharge leakage indistinguishable from voltage sensor offset without external precision multimeter.",
                "Micro-short current leakage indistinguishable from current sensor zero-bias without isolated shunt verification.",
            ),
            suggested_investigations=(
                "Perform resting zero-point verification with calibrated external digital multimeter.",
                "Verify analog-to-digital converter (ADC) reference rail stability on BMS sensing board.",
            ),
            total_possible_supporting_weight=1.0,
        )


class ModelFidelityMismatchHypothesis(AbstractDiagnosticHypothesis):
    """Hypothesis evaluating empirical evidence of mathematical model parameter mismatch or unmodeled dynamics."""

    def __init__(self) -> None:
        super().__init__(
            hypothesis_id="HYP_MODEL_MISMATCH",
            title="Digital Twin ECM Model Fidelity Mismatch or Outdated Baseline Parameters",
            category=DiagnosticCategory.MODEL,
            required_signals=("voltage_residual_v", "model_validation_state"),
            optional_signals=("temp_residual_c", "identified_parameters"),
            untestable_confounds=(
                "High-order electrochemical diffusion relaxation indistinguishable from 1-RC ECM parameter error without laboratory EIS characterization.",
                "Hysteresis overpotential indistinguishable from ohmic resistance shift without reference titration.",
            ),
            suggested_investigations=(
                "Review Level 5.3 prospective residual reduction under Level 5.2 identified parameters.",
                "Perform scheduled laboratory benchmark recalibration if persistent model divergence is observed.",
            ),
            total_possible_supporting_weight=1.0,
        )


class ApparentOhmicResistanceGrowthHypothesis(AbstractDiagnosticHypothesis):
    """Hypothesis evaluating empirical evidence consistent with increased apparent series ohmic resistance."""

    def __init__(self) -> None:
        super().__init__(
            hypothesis_id="HYP_APPARENT_OHMIC_GROWTH",
            title="Empirical Data Consistent with Increased Apparent Ohmic Resistance",
            category=DiagnosticCategory.ELECTRICAL,
            required_signals=("pack_voltage_v", "pack_current_a", "identified_r0_ohm"),
            optional_signals=("r0_drift_fraction", "r0_covariance", "voltage_delta_rmse_v"),
            untestable_confounds=(
                "Electrochemical cell internal ohmic impedance growth indistinguishable from terminal busbar / tab contact resistance from pack-level terminals.",
                "Wiring harness / contactor contact degradation indistinguishable from cell bulk electrolyte resistance growth without Kelvin sensing.",
            ),
            suggested_investigations=(
                "Inspect high-current terminal connections, busbar torque, and contactor contact resistance.",
                "Review Level 5.2 RLS parameter covariance and Level 5.3 prospective validation evidence.",
            ),
            total_possible_supporting_weight=1.0,
        )


class ThermalDissipationImpairmentHypothesis(AbstractDiagnosticHypothesis):
    """Hypothesis evaluating empirical evidence consistent with thermal dissipation impairment."""

    def __init__(self) -> None:
        super().__init__(
            hypothesis_id="HYP_THERMAL_IMPAIRMENT",
            title="Empirical Data Consistent with Impaired Heat Dissipation or Elevated Thermal Rate",
            category=DiagnosticCategory.THERMAL,
            required_signals=("avg_cell_temperature_c", "pack_current_a"),
            optional_signals=("ambient_temperature_c", "thermal_residual_c", "temp_rate_c_s"),
            untestable_confounds=(
                "Increased internal joule heating indistinguishable from external cooling system / fan degradation if ambient temperature and coolant flow are uninstrumented.",
                "Thermal interface material (TIM) degradation indistinguishable from cell core impedance growth without localized thermal flux sensors.",
            ),
            suggested_investigations=(
                "Inspect cooling airflow channels, fan operation, and thermal interface materials.",
                "Verify ambient temperature sensor continuity and cooling fluid circulation rate.",
            ),
            total_possible_supporting_weight=1.0,
        )


class CellDispersionImbalanceHypothesis(AbstractDiagnosticHypothesis):
    """Hypothesis evaluating empirical evidence of cell-to-cell voltage dispersion imbalance (conditional on cell telemetry)."""

    def __init__(self) -> None:
        super().__init__(
            hypothesis_id="HYP_CELL_IMBALANCE",
            title="Cell-to-Cell Voltage or State Dispersion Imbalance",
            category=DiagnosticCategory.CELL,
            required_signals=("cell_voltages_v",),
            optional_signals=("cell_temperatures_c", "pack_current_a"),
            untestable_confounds=(
                "State-of-charge imbalance indistinguishable from cell capacity mismatch without full charge/discharge coulometric titration.",
                "Localized thermal gradient dispersion indistinguishable from intrinsic cell degradation without uniform isothermal testing.",
            ),
            suggested_investigations=(
                "Evaluate cell balancing circuit activity and individual cell voltage settling at full rest.",
                "Perform low-rate constant-current conditioning cycle to equalize cell state of charge.",
            ),
            total_possible_supporting_weight=1.0,
        )


class ThroughputAcceleratedFadeHypothesis(AbstractDiagnosticHypothesis):
    """Hypothesis evaluating empirical evidence of throughput-driven capacity degradation."""

    def __init__(self) -> None:
        super().__init__(
            hypothesis_id="HYP_THROUGHPUT_ACCELERATED_FADE",
            title="Accelerated Capacity Fade Relative to Nominal Baseline Cycling Model",
            category=DiagnosticCategory.DEGRADATION,
            required_signals=("soh_capacity_fraction", "equivalent_full_cycles"),
            optional_signals=("energy_throughput_wh", "total_throughput_ah"),
            untestable_confounds=(
                "Active lithium loss (SEI growth) indistinguishable from loss of active material without differential voltage analysis (dQ/dV).",
                "High-rate discharge polarization cutoff indistinguishable from true capacity fade without low-rate C/20 reference capacity test.",
            ),
            suggested_investigations=(
                "Perform controlled laboratory reference capacity measurement (C/10 or C/20 full cycle).",
                "Review historical operating temperature profiles and cumulative high-rate cycling exposure.",
            ),
            total_possible_supporting_weight=1.0,
        )


def create_standard_hypotheses() -> tuple[AbstractDiagnosticHypothesis, ...]:
    """Factory function creating the standard diagnostic hypothesis catalog."""
    return (
        SensorDriftHypothesis(),
        ModelFidelityMismatchHypothesis(),
        ApparentOhmicResistanceGrowthHypothesis(),
        ThermalDissipationImpairmentHypothesis(),
        CellDispersionImbalanceHypothesis(),
        ThroughputAcceleratedFadeHypothesis(),
    )
