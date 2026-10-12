"""Enumerations and Value Objects for Prognostic Uncertainty and Confidence.

Defines strongly-typed, chemistry-agnostic, and hardware-agnostic taxonomies,
statuses, representations, intervals, and immutable containers for metrological
and statistical uncertainty evaluation in battery prognostics.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping, Optional, Sequence


class UncertaintySourceCategory(str, Enum):
    """Explicit taxonomy of uncertainty origins in prognostic estimation."""

    MEASUREMENT = "MEASUREMENT"                 # Sensor or instrumentation measurement uncertainty
    TRAJECTORY_TREND = "TRAJECTORY_TREND"       # Historical degradation rate or slope estimation dispersion
    MODEL_RESIDUAL = "MODEL_RESIDUAL"           # Scatter or residual deviation from historical fitted trajectory
    EXTRAPOLATION = "EXTRAPOLATION"             # Uncertainty arising from projection beyond observed domain span
    INPUT_STATE = "INPUT_STATE"                 # Uncertainty in current operational or degradation baseline state
    COMBINED = "COMBINED"                       # Combined uncertainty aggregated across independent sources
    UNKNOWN = "UNKNOWN"                         # Source category is uncharacterized or unrecorded


class UncertaintyStatus(str, Enum):
    """Availability and mathematical justification status of uncertainty quantification."""

    UNDEFINED = "UNDEFINED"                             # Uncertainty evaluation not requested or not defined
    DETERMINISTIC_ONLY = "DETERMINISTIC_ONLY"           # Point estimate only; no statistical uncertainty evaluated
    ESTIMATED = "ESTIMATED"                             # Heuristic or analytical first-order dispersion estimate
    STATISTICALLY_SUPPORTED = "STATISTICALLY_SUPPORTED" # Statistically justified with verified degrees of freedom
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"     # Data quantity/quality insufficient to support uncertainty
    COMBINATION_UNAVAILABLE = "COMBINATION_UNAVAILABLE" # Multiple components present but covariance/independence unknown


class EvidenceStrength(str, Enum):
    """Categorical classification of observational evidence supporting prognostic projection.

    Note: Evidence strength is NOT a confidence percentage, probability of accuracy,
    or physical truth score. It classifies data coverage, history depth, and consistency.
    """

    INSUFFICIENT = "INSUFFICIENT"   # Missing required channels or below minimum observation threshold
    VERY_WEAK = "VERY_WEAK"         # Sparse data, minimal span, or high scatter
    WEAK = "WEAK"                   # Limited history or notable extrapolation distance
    MODERATE = "MODERATE"           # Adequate observations and acceptable trend consistency
    STRONG = "STRONG"               # Substantial history span, consistent trend, and low residual scatter
    VERY_STRONG = "VERY_STRONG"     # Extensive high-density observations with tightly bounded residuals


class MeasurementUncertaintyAvailability(str, Enum):
    """Explicit classification of whether measurement uncertainty was provided by input provenance."""

    PROVIDED_MEASUREMENT_UNCERTAINTY = "PROVIDED_MEASUREMENT_UNCERTAINTY"
    UNAVAILABLE_MEASUREMENT_UNCERTAINTY = "UNAVAILABLE_MEASUREMENT_UNCERTAINTY"


class UncertaintyRepresentationType(str, Enum):
    """Mathematical form in which an uncertainty component is expressed."""

    ABSOLUTE = "ABSOLUTE"                               # Absolute standard deviation / dispersion in physical units
    RELATIVE_FRACTION = "RELATIVE_FRACTION"             # Dimensionless fraction relative to nominal value
    STANDARD_UNCERTAINTY = "STANDARD_UNCERTAINTY"       # Standard 1-sigma uncertainty
    EXPANDED_UNCERTAINTY = "EXPANDED_UNCERTAINTY"       # Expanded uncertainty with explicit coverage factor k
    UNAVAILABLE = "UNAVAILABLE"                         # Uncertainty representation unavailable


class UncertaintyIntervalType(str, Enum):
    """Semantic classification of an evaluated uncertainty interval.

    Crucial distinction:
    - CONFIDENCE_INTERVAL: Uncertainty around estimated model parameters or mean projected crossing.
    - PREDICTION_INTERVAL: Uncertainty for a future individual observation realization crossing EOL.
    - FIRST_ORDER_PROPAGATION_DISPERSION: First-order analytical dispersion (+/- 1-sigma sensitivity).
    - UNAVAILABLE: Interval could not be mathematically justified under supplied data.
    """

    CONFIDENCE_INTERVAL = "CONFIDENCE_INTERVAL"
    PREDICTION_INTERVAL = "PREDICTION_INTERVAL"
    FIRST_ORDER_PROPAGATION_DISPERSION = "FIRST_ORDER_PROPAGATION_DISPERSION"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class UncertaintyBound:
    """Immutable container for upper and lower uncertainty bounds with constraint tracking."""

    lower: float
    upper: float
    coverage_parameter: Optional[float] = None
    interval_type: UncertaintyIntervalType = UncertaintyIntervalType.CONFIDENCE_INTERVAL
    is_truncated_at_zero: bool = False
    constraint_description: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.lower, (int, float)) or math.isnan(self.lower) or math.isinf(self.lower):
            raise ValueError(f"lower must be a finite float, got {self.lower}.")
        if not isinstance(self.upper, (int, float)) or math.isnan(self.upper) or math.isinf(self.upper):
            raise ValueError(f"upper must be a finite float, got {self.upper}.")
        if self.lower > self.upper:
            raise ValueError(f"lower bound ({self.lower}) cannot exceed upper bound ({self.upper}).")
        if not isinstance(self.interval_type, UncertaintyIntervalType):
            raise TypeError(f"Expected UncertaintyIntervalType, got {type(self.interval_type).__name__}.")
        if self.coverage_parameter is not None:
            if (
                not isinstance(self.coverage_parameter, (int, float))
                or math.isnan(self.coverage_parameter)
                or math.isinf(self.coverage_parameter)
                or self.coverage_parameter <= 0.0
            ):
                raise ValueError(
                    f"coverage_parameter must be a positive finite float, got {self.coverage_parameter}."
                )

    def to_dict(self) -> dict[str, Any]:
        """Serializes uncertainty bounds to dictionary."""
        return {
            "lower": round(float(self.lower), 6),
            "upper": round(float(self.upper), 6),
            "coverage_parameter": (
                round(float(self.coverage_parameter), 4) if self.coverage_parameter is not None else None
            ),
            "interval_type": self.interval_type.value,
            "is_truncated_at_zero": self.is_truncated_at_zero,
            "constraint_description": self.constraint_description,
        }


@dataclass(frozen=True)
class UncertaintyComponent:
    """Immutable record of an individual uncertainty source contribution."""

    source_category: UncertaintySourceCategory
    status: UncertaintyStatus
    standard_uncertainty: Optional[float] = None
    relative_uncertainty: Optional[float] = None
    expanded_uncertainty: Optional[float] = None
    coverage_factor: Optional[float] = None
    degrees_of_freedom: Optional[int] = None
    unit: str = ""
    description: Optional[str] = None
    assumptions: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.source_category, UncertaintySourceCategory):
            raise TypeError(f"Expected UncertaintySourceCategory, got {type(self.source_category).__name__}.")
        if not isinstance(self.status, UncertaintyStatus):
            raise TypeError(f"Expected UncertaintyStatus, got {type(self.status).__name__}.")

        for name, val in [
            ("standard_uncertainty", self.standard_uncertainty),
            ("relative_uncertainty", self.relative_uncertainty),
            ("expanded_uncertainty", self.expanded_uncertainty),
            ("coverage_factor", self.coverage_factor),
        ]:
            if val is not None:
                if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val) or val < 0.0:
                    raise ValueError(f"{name} must be a non-negative finite float, got {val}.")

        if self.degrees_of_freedom is not None:
            if not isinstance(self.degrees_of_freedom, int) or self.degrees_of_freedom < 0:
                raise ValueError(
                    f"degrees_of_freedom must be a non-negative integer, got {self.degrees_of_freedom}."
                )

    def to_dict(self) -> dict[str, Any]:
        """Serializes uncertainty component to dictionary."""
        return {
            "source_category": self.source_category.value,
            "status": self.status.value,
            "standard_uncertainty": (
                round(float(self.standard_uncertainty), 8) if self.standard_uncertainty is not None else None
            ),
            "relative_uncertainty": (
                round(float(self.relative_uncertainty), 6) if self.relative_uncertainty is not None else None
            ),
            "expanded_uncertainty": (
                round(float(self.expanded_uncertainty), 8) if self.expanded_uncertainty is not None else None
            ),
            "coverage_factor": (
                round(float(self.coverage_factor), 4) if self.coverage_factor is not None else None
            ),
            "degrees_of_freedom": self.degrees_of_freedom,
            "unit": self.unit,
            "description": self.description,
            "assumptions": list(self.assumptions),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class UncertaintyCombinationResult:
    """Immutable result of combining multiple uncertainty sources."""

    status: UncertaintyStatus
    combined_standard_uncertainty: Optional[float] = None
    components: Sequence[UncertaintyComponent] = field(default_factory=tuple)
    combination_method: str = "INDEPENDENT_ROOT_SUM_SQUARES"
    assumptions: Sequence[str] = field(default_factory=tuple)
    diagnostic_message: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, UncertaintyStatus):
            raise TypeError(f"Expected UncertaintyStatus, got {type(self.status).__name__}.")
        if self.combined_standard_uncertainty is not None:
            if (
                not isinstance(self.combined_standard_uncertainty, (int, float))
                or math.isnan(self.combined_standard_uncertainty)
                or math.isinf(self.combined_standard_uncertainty)
                or self.combined_standard_uncertainty < 0.0
            ):
                raise ValueError(
                    f"combined_standard_uncertainty must be a non-negative finite float, got {self.combined_standard_uncertainty}."
                )

    def to_dict(self) -> dict[str, Any]:
        """Serializes uncertainty combination result to dictionary."""
        return {
            "status": self.status.value,
            "combined_standard_uncertainty": (
                round(float(self.combined_standard_uncertainty), 8)
                if self.combined_standard_uncertainty is not None
                else None
            ),
            "components": [c.to_dict() for c in self.components],
            "combination_method": self.combination_method,
            "assumptions": list(self.assumptions),
            "diagnostic_message": self.diagnostic_message,
        }
