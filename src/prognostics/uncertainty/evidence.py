"""Multi-Dimensional Evidence Strength Assessment for Battery Prognostics.

Evaluates and audits observational evidence supporting prognostic projections across
multiple metrological and trajectory dimensions.

Crucial Scientific Principle:
Evidence strength is NOT a probability, a confidence percentage, or a claim of physical
battery RUL correctness. It classifies data density, history depth, temporal coverage,
and mathematical consistency under explicitly configured evaluation rules.
No universal thresholds or arbitrary percentage mappings (e.g. STRONG = 95%) exist.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence

from src.prognostics.prediction import PrognosticOperatingContext
from src.prognostics.trajectory import DegradationTrajectory
from src.prognostics.uncertainty.extrapolation import ExtrapolationMetrics
from src.prognostics.uncertainty.measurement import MeasurementUncertaintyEvaluation
from src.prognostics.uncertainty.trajectory import TrajectoryTrendStatistics
from src.prognostics.uncertainty.types import (
    EvidenceStrength,
    MeasurementUncertaintyAvailability,
    UncertaintyStatus,
)


@dataclass(frozen=True)
class EvidenceDimensionRecord:
    """Immutable audit record for a single evaluated evidence dimension."""

    dimension_name: str
    evaluated: bool
    strength: EvidenceStrength
    input_value: Optional[Any] = None
    threshold_applied: Optional[Any] = None
    rationale: str = ""
    missing_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes dimension record to dictionary."""
        return {
            "dimension_name": self.dimension_name,
            "evaluated": self.evaluated,
            "strength": self.strength.value,
            "input_value": self.input_value,
            "threshold_applied": self.threshold_applied,
            "rationale": self.rationale,
            "missing_reason": self.missing_reason,
        }


@dataclass(frozen=True)
class EvidenceEvaluatorConfig:
    """Configurable evaluation thresholds and aggregation rules for evidence assessment.

    Note: All default thresholds are transparent mathematical heuristics for the linear
    baseline and do not represent universal battery science constants.
    """

    min_observations_moderate: int = 5
    min_observations_strong: int = 15
    min_observations_very_strong: int = 50

    max_extrapolation_ratio_very_strong: float = 0.5
    max_extrapolation_ratio_strong: float = 1.0
    max_extrapolation_ratio_moderate: float = 2.0
    max_extrapolation_ratio_weak: float = 5.0

    min_r2_strong: float = 0.90
    min_r2_moderate: float = 0.70
    min_r2_weak: float = 0.40

    aggregation_policy: str = "MINIMUM_DIMENSION"  # "MINIMUM_DIMENSION", "MAJORITY", "WEIGHTED"

    def to_dict(self) -> dict[str, Any]:
        """Serializes evidence evaluator configuration to dictionary."""
        return {
            "min_observations_moderate": self.min_observations_moderate,
            "min_observations_strong": self.min_observations_strong,
            "min_observations_very_strong": self.min_observations_very_strong,
            "max_extrapolation_ratio_very_strong": self.max_extrapolation_ratio_very_strong,
            "max_extrapolation_ratio_strong": self.max_extrapolation_ratio_strong,
            "max_extrapolation_ratio_moderate": self.max_extrapolation_ratio_moderate,
            "max_extrapolation_ratio_weak": self.max_extrapolation_ratio_weak,
            "min_r2_strong": self.min_r2_strong,
            "min_r2_moderate": self.min_r2_moderate,
            "min_r2_weak": self.min_r2_weak,
            "aggregation_policy": self.aggregation_policy,
        }


@dataclass(frozen=True)
class EvidenceAssessment:
    """Immutable multi-dimensional evidence assessment report."""

    overall_strength: EvidenceStrength
    dimensions: Mapping[str, EvidenceDimensionRecord]
    evaluated_dimension_count: int
    total_dimension_count: int
    is_sufficient_for_uncertainty: bool
    diagnostic_summary: str
    config_applied: EvidenceEvaluatorConfig
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes evidence assessment report to dictionary."""
        return {
            "overall_strength": self.overall_strength.value,
            "dimensions": {k: v.to_dict() for k, v in self.dimensions.items()},
            "evaluated_dimension_count": self.evaluated_dimension_count,
            "total_dimension_count": self.total_dimension_count,
            "is_sufficient_for_uncertainty": self.is_sufficient_for_uncertainty,
            "diagnostic_summary": self.diagnostic_summary,
            "config_applied": self.config_applied.to_dict(),
            "metadata": dict(self.metadata),
        }


class EvidenceEvaluator:
    """Evaluates multi-dimensional evidence strength transparently."""

    _STRENGTH_ORDER: list[EvidenceStrength] = [
        EvidenceStrength.INSUFFICIENT,
        EvidenceStrength.VERY_WEAK,
        EvidenceStrength.WEAK,
        EvidenceStrength.MODERATE,
        EvidenceStrength.STRONG,
        EvidenceStrength.VERY_STRONG,
    ]

    @classmethod
    def evaluate(
        cls,
        trajectory: Optional[DegradationTrajectory] = None,
        trend_stats: Optional[TrajectoryTrendStatistics] = None,
        extrapolation_metrics: Optional[ExtrapolationMetrics] = None,
        measurement_eval: Optional[MeasurementUncertaintyEvaluation] = None,
        operating_context: Optional[PrognosticOperatingContext] = None,
        config: Optional[EvidenceEvaluatorConfig] = None,
    ) -> EvidenceAssessment:
        """Evaluates evidence strength across all supplied dimensions."""
        cfg = config or EvidenceEvaluatorConfig()
        dim_records: dict[str, EvidenceDimensionRecord] = {}

        # 1. Dimension: Observation Count
        if trend_stats is not None:
            n = trend_stats.sample_count
            if n < 2:
                s = EvidenceStrength.INSUFFICIENT
                r = f"Sample count {n} is below minimum 2 required."
            elif n == 2:
                s = EvidenceStrength.VERY_WEAK
                r = "Only 2 points present (endpoint secant line)."
            elif n < cfg.min_observations_moderate:
                s = EvidenceStrength.WEAK
                r = f"Sample count {n} < moderate threshold ({cfg.min_observations_moderate})."
            elif n < cfg.min_observations_strong:
                s = EvidenceStrength.MODERATE
                r = f"Sample count {n} meets moderate threshold ({cfg.min_observations_moderate})."
            elif n < cfg.min_observations_very_strong:
                s = EvidenceStrength.STRONG
                r = f"Sample count {n} meets strong threshold ({cfg.min_observations_strong})."
            else:
                s = EvidenceStrength.VERY_STRONG
                r = f"Sample count {n} meets very strong threshold ({cfg.min_observations_very_strong})."

            dim_records["observation_count"] = EvidenceDimensionRecord(
                dimension_name="observation_count",
                evaluated=True,
                strength=s,
                input_value=n,
                threshold_applied={
                    "moderate": cfg.min_observations_moderate,
                    "strong": cfg.min_observations_strong,
                    "very_strong": cfg.min_observations_very_strong,
                },
                rationale=r,
            )
        else:
            dim_records["observation_count"] = EvidenceDimensionRecord(
                dimension_name="observation_count",
                evaluated=False,
                strength=EvidenceStrength.INSUFFICIENT,
                missing_reason="Trajectory trend statistics not provided.",
            )

        # 2. Dimension: History Span
        if extrapolation_metrics is not None:
            span = extrapolation_metrics.observed_history_span
            if span <= 0.0:
                s = EvidenceStrength.INSUFFICIENT
                r = f"History span is non-positive ({span:.2f})."
            elif span < 10.0:
                s = EvidenceStrength.WEAK
                r = f"Short history span ({span:.2f} {extrapolation_metrics.domain_unit})."
            else:
                s = EvidenceStrength.STRONG
                r = f"Positive history span ({span:.2f} {extrapolation_metrics.domain_unit})."

            dim_records["history_span"] = EvidenceDimensionRecord(
                dimension_name="history_span",
                evaluated=True,
                strength=s,
                input_value=round(span, 4),
                rationale=r,
            )
        else:
            dim_records["history_span"] = EvidenceDimensionRecord(
                dimension_name="history_span",
                evaluated=False,
                strength=EvidenceStrength.INSUFFICIENT,
                missing_reason="Extrapolation metrics not provided.",
            )

        # 3. Dimension: Explanatory Fit R²
        if trend_stats is not None and trend_stats.r_squared is not None:
            r2 = trend_stats.r_squared
            if trend_stats.sample_count <= 2:
                s = EvidenceStrength.WEAK
                r = "R² = 1.0 is trivial for <= 2 observation points."
            elif r2 >= cfg.min_r2_strong:
                s = EvidenceStrength.STRONG
                r = f"Descriptive R² ({r2:.4f}) >= strong threshold ({cfg.min_r2_strong})."
            elif r2 >= cfg.min_r2_moderate:
                s = EvidenceStrength.MODERATE
                r = f"Descriptive R² ({r2:.4f}) >= moderate threshold ({cfg.min_r2_moderate})."
            elif r2 >= cfg.min_r2_weak:
                s = EvidenceStrength.WEAK
                r = f"Descriptive R² ({r2:.4f}) >= weak threshold ({cfg.min_r2_weak})."
            else:
                s = EvidenceStrength.VERY_WEAK
                r = f"Descriptive R² ({r2:.4f}) indicates notable historical scatter."

            dim_records["explanatory_fit_r2"] = EvidenceDimensionRecord(
                dimension_name="explanatory_fit_r2",
                evaluated=True,
                strength=s,
                input_value=round(r2, 4),
                threshold_applied={
                    "weak": cfg.min_r2_weak,
                    "moderate": cfg.min_r2_moderate,
                    "strong": cfg.min_r2_strong,
                },
                rationale=r,
            )
        else:
            dim_records["explanatory_fit_r2"] = EvidenceDimensionRecord(
                dimension_name="explanatory_fit_r2",
                evaluated=False,
                strength=EvidenceStrength.INSUFFICIENT,
                missing_reason="R² not evaluated (df < 1 or stats missing).",
            )

        # 4. Dimension: Extrapolation Ratio
        if extrapolation_metrics is not None:
            ratio = extrapolation_metrics.extrapolation_ratio
            if math.isinf(ratio):
                s = EvidenceStrength.INSUFFICIENT
                r = "Extrapolation ratio is infinite."
            elif ratio <= cfg.max_extrapolation_ratio_very_strong:
                s = EvidenceStrength.VERY_STRONG
                r = f"Extrapolation ratio ({ratio:.2f}x) is very low (<= {cfg.max_extrapolation_ratio_very_strong})."
            elif ratio <= cfg.max_extrapolation_ratio_strong:
                s = EvidenceStrength.STRONG
                r = f"Extrapolation ratio ({ratio:.2f}x) <= strong threshold ({cfg.max_extrapolation_ratio_strong})."
            elif ratio <= cfg.max_extrapolation_ratio_moderate:
                s = EvidenceStrength.MODERATE
                r = f"Extrapolation ratio ({ratio:.2f}x) <= moderate threshold ({cfg.max_extrapolation_ratio_moderate})."
            elif ratio <= cfg.max_extrapolation_ratio_weak:
                s = EvidenceStrength.WEAK
                r = f"Extrapolation ratio ({ratio:.2f}x) <= weak threshold ({cfg.max_extrapolation_ratio_weak})."
            else:
                s = EvidenceStrength.VERY_WEAK
                r = f"Extrapolation ratio ({ratio:.2f}x) exceeds weak threshold ({cfg.max_extrapolation_ratio_weak})."

            dim_records["extrapolation_ratio"] = EvidenceDimensionRecord(
                dimension_name="extrapolation_ratio",
                evaluated=True,
                strength=s,
                input_value=round(ratio, 4) if not math.isinf(ratio) else "infinity",
                threshold_applied={
                    "very_strong": cfg.max_extrapolation_ratio_very_strong,
                    "strong": cfg.max_extrapolation_ratio_strong,
                    "moderate": cfg.max_extrapolation_ratio_moderate,
                    "weak": cfg.max_extrapolation_ratio_weak,
                },
                rationale=r,
            )
        else:
            dim_records["extrapolation_ratio"] = EvidenceDimensionRecord(
                dimension_name="extrapolation_ratio",
                evaluated=False,
                strength=EvidenceStrength.INSUFFICIENT,
                missing_reason="Extrapolation metrics not provided.",
            )

        # 5. Dimension: Measurement Uncertainty Availability
        if measurement_eval is not None:
            if measurement_eval.availability == MeasurementUncertaintyAvailability.PROVIDED_MEASUREMENT_UNCERTAINTY:
                s = EvidenceStrength.STRONG
                r = f"Measurement uncertainty explicitly provided by input provenance (std_u = {measurement_eval.standard_uncertainty})."
            else:
                s = EvidenceStrength.WEAK
                r = "No measurement uncertainty was supplied in input provenance."

            dim_records["measurement_uncertainty_availability"] = EvidenceDimensionRecord(
                dimension_name="measurement_uncertainty_availability",
                evaluated=True,
                strength=s,
                input_value=measurement_eval.availability.value,
                rationale=r,
            )
        else:
            dim_records["measurement_uncertainty_availability"] = EvidenceDimensionRecord(
                dimension_name="measurement_uncertainty_availability",
                evaluated=False,
                strength=EvidenceStrength.INSUFFICIENT,
                missing_reason="Measurement uncertainty evaluation not provided.",
            )

        # 6. Dimension: Operating Context Coverage
        if operating_context is not None:
            avail_count = sum(
                1
                for q in (
                    operating_context.ambient_temperature_c,
                    operating_context.cell_temperature_c,
                    operating_context.c_rate,
                    operating_context.soc_fraction,
                    operating_context.pack_voltage_v,
                    operating_context.pack_current_a,
                )
                if q is not None and not math.isnan(q) and not math.isinf(q)
            )
            if avail_count >= 3:
                s = EvidenceStrength.STRONG
                r = f"Operating context has {avail_count} verified environmental/cycler channels."

            elif avail_count >= 1:
                s = EvidenceStrength.MODERATE
                r = f"Operating context has {avail_count} verified channels."
            else:
                s = EvidenceStrength.WEAK
                r = "Operating context channels uncharacterized or unavailable."

            dim_records["operating_context_coverage"] = EvidenceDimensionRecord(
                dimension_name="operating_context_coverage",
                evaluated=True,
                strength=s,
                input_value=avail_count,
                rationale=r,
            )
        else:
            dim_records["operating_context_coverage"] = EvidenceDimensionRecord(
                dimension_name="operating_context_coverage",
                evaluated=False,
                strength=EvidenceStrength.WEAK,
                missing_reason="No operating context attached.",
            )

        # Aggregate Overall Evidence Strength
        evaluated_dims = [d for d in dim_records.values() if d.evaluated]
        eval_count = len(evaluated_dims)
        tot_count = len(dim_records)

        if eval_count == 0 or any(d.strength == EvidenceStrength.INSUFFICIENT for d in evaluated_dims):
            overall = EvidenceStrength.INSUFFICIENT
            diag = "Evidence is insufficient: one or more critical dimensions failed evaluation."
            is_sufficient = False
        else:
            # Policy aggregation
            if cfg.aggregation_policy == "MINIMUM_DIMENSION":
                # Find minimum strength among evaluated dimensions
                min_idx = min(cls._STRENGTH_ORDER.index(d.strength) for d in evaluated_dims)
                overall = cls._STRENGTH_ORDER[min_idx]
                diag = f"Overall evidence aggregated as MINIMUM evaluated dimension ({overall.value})."
            else:
                # Average index
                avg_idx = int(round(sum(cls._STRENGTH_ORDER.index(d.strength) for d in evaluated_dims) / eval_count))
                overall = cls._STRENGTH_ORDER[min_idx if avg_idx < 0 else min(avg_idx, len(cls._STRENGTH_ORDER) - 1)]
                diag = f"Overall evidence aggregated via {cfg.aggregation_policy} policy ({overall.value})."

            is_sufficient = overall not in (EvidenceStrength.INSUFFICIENT, EvidenceStrength.VERY_WEAK)

        return EvidenceAssessment(
            overall_strength=overall,
            dimensions=dim_records,
            evaluated_dimension_count=eval_count,
            total_dimension_count=tot_count,
            is_sufficient_for_uncertainty=is_sufficient,
            diagnostic_summary=diag,
            config_applied=cfg,
            metadata={
                "aggregation_policy": cfg.aggregation_policy,
                "dimension_names": list(dim_records.keys()),
            },
        )
