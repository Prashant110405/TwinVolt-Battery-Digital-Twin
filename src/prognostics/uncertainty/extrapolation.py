"""Extrapolation Metrics and Evidence Evaluation for Battery Prognostics.

Tracks extrapolation distance, extrapolation ratio relative to observed history span,
and preserves slope and residual uncertainty dimensions.

Crucial Scientific Principle:
Extrapolation ratio is an evidentiary dimension of structural projection risk.
It is NOT automatically a mathematical uncertainty multiplier. No ad-hoc formula
such as (uncertainty = ratio * constant) is implemented.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional

from src.prognostics.uncertainty.types import (
    UncertaintyComponent,
    UncertaintySourceCategory,
    UncertaintyStatus,
)


@dataclass(frozen=True)
class ExtrapolationMetrics:
    """Immutable metrological record of prognostic extrapolation beyond historical domain."""

    observed_history_span: float
    extrapolation_distance: float
    extrapolation_ratio: float
    sample_count: int
    is_extrapolating: bool
    slope_standard_error: Optional[float] = None
    residual_standard_error: Optional[float] = None
    domain_unit: str = "cycles"
    component: Optional[UncertaintyComponent] = None
    diagnostic_message: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, val in [
            ("observed_history_span", self.observed_history_span),
            ("extrapolation_distance", self.extrapolation_distance),
        ]:
            if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                raise ValueError(f"{name} must be a finite float, got {val}.")

        if not isinstance(self.extrapolation_ratio, (int, float)) or math.isnan(self.extrapolation_ratio):
            raise ValueError(f"extrapolation_ratio must be a float (may be inf), got {self.extrapolation_ratio}.")

        if not isinstance(self.sample_count, int) or self.sample_count < 0:
            raise ValueError(f"sample_count must be a non-negative integer, got {self.sample_count}.")


    def to_dict(self) -> dict[str, Any]:
        """Serializes extrapolation metrics to dictionary."""
        return {
            "observed_history_span": round(float(self.observed_history_span), 6),
            "extrapolation_distance": round(float(self.extrapolation_distance), 6),
            "extrapolation_ratio": round(float(self.extrapolation_ratio), 4),
            "sample_count": self.sample_count,
            "is_extrapolating": self.is_extrapolating,
            "slope_standard_error": (
                round(float(self.slope_standard_error), 8)
                if self.slope_standard_error is not None
                else None
            ),
            "residual_standard_error": (
                round(float(self.residual_standard_error), 8)
                if self.residual_standard_error is not None
                else None
            ),
            "domain_unit": self.domain_unit,
            "component": self.component.to_dict() if self.component else None,
            "diagnostic_message": self.diagnostic_message,
            "metadata": dict(self.metadata),
        }


class ExtrapolationEvaluator:
    """Deterministic evaluator for prognostic extrapolation metrics."""

    @classmethod
    def evaluate(
        cls,
        observed_history_span: float,
        extrapolation_distance: float,
        sample_count: int,
        slope_standard_error: Optional[float] = None,
        residual_standard_error: Optional[float] = None,
        domain_unit: str = "cycles",
    ) -> ExtrapolationMetrics:
        """Evaluates extrapolation metrics and packages an extrapolation uncertainty record."""
        if not isinstance(observed_history_span, (int, float)) or math.isnan(observed_history_span) or math.isinf(observed_history_span):
            raise ValueError(f"observed_history_span must be a finite float, got {observed_history_span}.")
        if not isinstance(extrapolation_distance, (int, float)) or math.isnan(extrapolation_distance) or math.isinf(extrapolation_distance):
            raise ValueError(f"extrapolation_distance must be a finite float, got {extrapolation_distance}.")

        history_span = float(observed_history_span)
        extrap_dist = float(extrapolation_distance)

        if history_span > 0.0:
            ratio = extrap_dist / history_span
        else:
            ratio = 0.0 if extrap_dist == 0.0 else float("inf")

        is_extrapolating = extrap_dist > 0.0

        # Status: ESTIMATED when extrapolating, DETERMINISTIC_ONLY if zero extrapolation distance
        if extrap_dist == 0.0:
            status = UncertaintyStatus.DETERMINISTIC_ONLY
            diag = "No extrapolation beyond history; system is at or beyond EOL boundary."
        elif math.isinf(ratio):
            status = UncertaintyStatus.INSUFFICIENT_EVIDENCE
            diag = "Infinite extrapolation ratio due to zero historical observation span."
        else:
            status = UncertaintyStatus.ESTIMATED
            diag = f"Extrapolation distance is {extrap_dist:.2f} {domain_unit} ({ratio:.2f}x historical span)."

        comp = UncertaintyComponent(
            source_category=UncertaintySourceCategory.EXTRAPOLATION,
            status=status,
            unit=domain_unit,
            description=(
                f"Extrapolation of {extrap_dist:.4f} {domain_unit} beyond {history_span:.4f} "
                f"{domain_unit} historical baseline (ratio={ratio:.4f})."
            ),
            assumptions=(
                "First-order trajectory projection assumes operating conditions and degradation rate "
                "remain invariant across the entire extrapolation domain.",
                "Extrapolation ratio is preserved as an evidence dimension; no ad-hoc multiplier was applied.",
            ),
            metadata={
                "observed_history_span": round(history_span, 6),
                "extrapolation_distance": round(extrap_dist, 6),
                "extrapolation_ratio": round(ratio, 4) if not math.isinf(ratio) else "infinity",
                "sample_count": sample_count,
            },
        )

        return ExtrapolationMetrics(
            observed_history_span=history_span,
            extrapolation_distance=extrap_dist,
            extrapolation_ratio=ratio,
            sample_count=sample_count,
            is_extrapolating=is_extrapolating,
            slope_standard_error=slope_standard_error,
            residual_standard_error=residual_standard_error,
            domain_unit=domain_unit,
            component=comp,
            diagnostic_message=diag,
            metadata={
                "history_span": history_span,
                "extrapolation_distance": extrap_dist,
                "extrapolation_ratio": ratio,
            },
        )
