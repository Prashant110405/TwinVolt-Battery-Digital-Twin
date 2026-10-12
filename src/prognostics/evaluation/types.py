"""Enumerations and Value Objects for Prognostic Evaluation and Decision Layer.

Defines strongly-typed, immutable value objects and statuses for comprehensive
evaluation results, End-of-Life (EOL) assessment, and multi-dimensional validity records.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping, Optional, Sequence

from src.prognostics.features import DegradationFeatureSet
from src.prognostics.prediction import EOLDefinition, RULPredictionResult
from src.prognostics.types import (
    ComparisonOperator,
    PrognosticStatus,
)
from src.prognostics.uncertainty.engine import UncertaintyEvaluationResult
from src.prognostics.uncertainty.evidence import EvidenceAssessment
from src.prognostics.uncertainty.types import EvidenceStrength, UncertaintyStatus


class EvaluationStatus(str, Enum):
    """Overall execution and validity status of a prognostic evaluation."""

    VALID = "VALID"                                         # Prediction, EOL assessment, and evidence are valid
    VALID_WITH_LIMITATIONS = "VALID_WITH_LIMITATIONS"       # Valid RUL point estimate, but with noted evidence/uncertainty limits
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"                 # Missing required degradation or domain channels
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"           # Historical window too short for confident projection
    DATA_QUALITY_FAILED = "DATA_QUALITY_FAILED"             # Telemetry or observation data violated integrity/physical invariants
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"                         # Operating profile or rate of change outside extrapolation domain
    INVALID_EOL_CRITERION = "INVALID_EOL_CRITERION"         # Configured EOL definition is incompatible or malformed
    INDETERMINATE = "INDETERMINATE"                         # State cannot be determined from available data


class EOLState(str, Enum):
    """Metrological classification of system degradation state relative to EOL boundary."""

    NOT_REACHED = "NOT_REACHED"             # Current degradation is strictly before EOL threshold
    ALREADY_REACHED = "ALREADY_REACHED"     # Current degradation currently satisfies or exceeds EOL threshold
    PROJECTED = "PROJECTED"                 # Current is before EOL and projected crossing point was calculated
    INDETERMINATE = "INDETERMINATE"         # Current degradation value is missing or uncharacterized
    INVALID = "INVALID"                     # EOL criterion is mathematically invalid or quantity is incompatible


@dataclass(frozen=True)
class EOLAssessment:
    """Immutable assessment of current and projected degradation relative to an EOL threshold."""

    eol_state: EOLState
    eol_definition: EOLDefinition
    threshold_value: float
    comparison_operator: ComparisonOperator
    unit: str
    quantity_name: str
    current_value: Optional[float] = None
    distance_to_eol: Optional[float] = None
    projected_crossing_domain_value: Optional[float] = None
    is_reached: bool = False
    diagnostic_message: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.eol_state, EOLState):
            raise TypeError(f"Expected EOLState, got {type(self.eol_state).__name__}.")
        if not isinstance(self.eol_definition, EOLDefinition):
            raise TypeError(f"Expected EOLDefinition, got {type(self.eol_definition).__name__}.")
        if not isinstance(self.comparison_operator, ComparisonOperator):
            raise TypeError(f"Expected ComparisonOperator, got {type(self.comparison_operator).__name__}.")
        if not self.unit or not isinstance(self.unit, str):
            raise ValueError("unit must be a non-empty string.")
        if not self.quantity_name or not isinstance(self.quantity_name, str):
            raise ValueError("quantity_name must be a non-empty string.")

        for name, val in [
            ("threshold_value", self.threshold_value),
            ("current_value", self.current_value),
            ("distance_to_eol", self.distance_to_eol),
            ("projected_crossing_domain_value", self.projected_crossing_domain_value),
        ]:
            if val is not None:
                if not isinstance(val, (int, float)) or math.isnan(val) or math.isinf(val):
                    raise ValueError(f"{name} must be a finite float, got {val}.")

        if self.distance_to_eol is not None and self.distance_to_eol < 0.0:
            raise ValueError(f"distance_to_eol must be non-negative, got {self.distance_to_eol}.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes EOL assessment to dictionary."""
        return {
            "eol_state": self.eol_state.value,
            "eol_definition": self.eol_definition.to_dict(),
            "threshold_value": round(float(self.threshold_value), 6),
            "comparison_operator": self.comparison_operator.value,
            "unit": self.unit,
            "quantity_name": self.quantity_name,
            "current_value": round(float(self.current_value), 6) if self.current_value is not None else None,
            "distance_to_eol": (
                round(float(self.distance_to_eol), 6) if self.distance_to_eol is not None else None
            ),
            "projected_crossing_domain_value": (
                round(float(self.projected_crossing_domain_value), 6)
                if self.projected_crossing_domain_value is not None
                else None
            ),
            "is_reached": self.is_reached,
            "diagnostic_message": self.diagnostic_message,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class EvaluationValidity:
    """Immutable multi-dimensional evaluation validity and limitation audit."""

    data_quality: PrognosticStatus = PrognosticStatus.VALID
    history_sufficiency: PrognosticStatus = PrognosticStatus.VALID
    domain_validity: PrognosticStatus = PrognosticStatus.VALID
    eol_validity: bool = True
    prediction_validity: bool = True
    uncertainty_availability: UncertaintyStatus = UncertaintyStatus.UNDEFINED
    evidence_strength: EvidenceStrength = EvidenceStrength.INSUFFICIENT
    limitations: Sequence[str] = field(default_factory=tuple)
    diagnostic_notes: Sequence[str] = field(default_factory=tuple)
    is_usable_for_decision: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.data_quality, PrognosticStatus):
            raise TypeError(f"Expected PrognosticStatus for data_quality, got {type(self.data_quality).__name__}.")
        if not isinstance(self.history_sufficiency, PrognosticStatus):
            raise TypeError(
                f"Expected PrognosticStatus for history_sufficiency, got {type(self.history_sufficiency).__name__}."
            )
        if not isinstance(self.domain_validity, PrognosticStatus):
            raise TypeError(
                f"Expected PrognosticStatus for domain_validity, got {type(self.domain_validity).__name__}."
            )
        if not isinstance(self.uncertainty_availability, UncertaintyStatus):
            raise TypeError(
                f"Expected UncertaintyStatus for uncertainty_availability, got {type(self.uncertainty_availability).__name__}."
            )
        if not isinstance(self.evidence_strength, EvidenceStrength):
            raise TypeError(
                f"Expected EvidenceStrength for evidence_strength, got {type(self.evidence_strength).__name__}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes evaluation validity to dictionary."""
        return {
            "data_quality": self.data_quality.value,
            "history_sufficiency": self.history_sufficiency.value,
            "domain_validity": self.domain_validity.value,
            "eol_validity": self.eol_validity,
            "prediction_validity": self.prediction_validity,
            "uncertainty_availability": self.uncertainty_availability.value,
            "evidence_strength": self.evidence_strength.value,
            "limitations": list(self.limitations),
            "diagnostic_notes": list(self.diagnostic_notes),
            "is_usable_for_decision": self.is_usable_for_decision,
        }


@dataclass(frozen=True)
class PrognosticEvaluationResult:
    """Immutable top-level structured evaluation result for battery prognostics.

    Combines trajectories, deterministic RUL prediction, EOL assessment,
    uncertainty analysis, evidence auditing, and multi-dimensional validity.
    """

    evaluation_id: str
    system_id: str
    evaluation_timestamp_ns: int
    created_at_utc: str
    evaluation_status: EvaluationStatus
    eol_assessment: EOLAssessment
    validity: EvaluationValidity
    prediction: Optional[RULPredictionResult] = None
    uncertainty: Optional[UncertaintyEvaluationResult] = None
    evidence: Optional[EvidenceAssessment] = None
    feature_set: Optional[DegradationFeatureSet] = None
    diagnostics: Sequence[str] = field(default_factory=tuple)
    reproducibility_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evaluation_id or not isinstance(self.evaluation_id, str):
            raise ValueError("evaluation_id must be a non-empty string.")
        if not self.system_id or not isinstance(self.system_id, str):
            raise ValueError("system_id must be a non-empty string.")
        if not isinstance(self.evaluation_timestamp_ns, int) or self.evaluation_timestamp_ns < 0:
            raise ValueError(
                f"evaluation_timestamp_ns must be a non-negative integer, got {self.evaluation_timestamp_ns}."
            )
        if not self.created_at_utc or not isinstance(self.created_at_utc, str):
            raise ValueError("created_at_utc must be a non-empty string.")
        if not isinstance(self.evaluation_status, EvaluationStatus):
            raise TypeError(f"Expected EvaluationStatus, got {type(self.evaluation_status).__name__}.")
        if not isinstance(self.eol_assessment, EOLAssessment):
            raise TypeError(f"Expected EOLAssessment, got {type(self.eol_assessment).__name__}.")
        if not isinstance(self.validity, EvaluationValidity):
            raise TypeError(f"Expected EvaluationValidity, got {type(self.validity).__name__}.")

        if self.prediction is not None and not isinstance(self.prediction, RULPredictionResult):
            raise TypeError(f"Expected RULPredictionResult, got {type(self.prediction).__name__}.")
        if self.uncertainty is not None and not isinstance(self.uncertainty, UncertaintyEvaluationResult):
            raise TypeError(f"Expected UncertaintyEvaluationResult, got {type(self.uncertainty).__name__}.")
        if self.evidence is not None and not isinstance(self.evidence, EvidenceAssessment):
            raise TypeError(f"Expected EvidenceAssessment, got {type(self.evidence).__name__}.")
        if self.feature_set is not None and not isinstance(self.feature_set, DegradationFeatureSet):
            raise TypeError(f"Expected DegradationFeatureSet, got {type(self.feature_set).__name__}.")

    @property
    def is_valid(self) -> bool:
        """Returns True if evaluation succeeded without fatal data quality or history failures."""
        return self.evaluation_status in (
            EvaluationStatus.VALID,
            EvaluationStatus.VALID_WITH_LIMITATIONS,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializes prognostic evaluation result to dictionary."""
        return {
            "evaluation_id": self.evaluation_id,
            "system_id": self.system_id,
            "evaluation_timestamp_ns": self.evaluation_timestamp_ns,
            "created_at_utc": self.created_at_utc,
            "evaluation_status": self.evaluation_status.value,
            "is_valid": self.is_valid,
            "eol_assessment": self.eol_assessment.to_dict(),
            "validity": self.validity.to_dict(),
            "prediction": self.prediction.to_dict() if self.prediction else None,
            "uncertainty": self.uncertainty.to_dict() if self.uncertainty else None,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "feature_set": self.feature_set.to_dict() if self.feature_set else None,
            "diagnostics": list(self.diagnostics),
            "reproducibility_metadata": dict(self.reproducibility_metadata),
        }
