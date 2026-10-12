"""Enumerations and Value Objects for Level 6.7 Prognostic Pipeline and Multi-Criterion Assessment.

Defines strongly-typed, immutable value objects, execution statuses, limiting resolution models,
and the top-level PrognosticAssessmentReport container.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping, Optional, Sequence

from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    PrognosticDecisionResult,
    RecommendationPriority,
    SecondaryAdvisory,
)
from src.prognostics.evaluation.types import (
    PrognosticEvaluationResult,
)
from src.prognostics.features import DegradationFeatureSet
from src.prognostics.prediction import EOLDefinition
from src.prognostics.types import (
    EOLCriterionType,
    HorizonDomain,
)


class PipelineStatus(str, Enum):
    """Execution and assessment status of the end-to-end prognostic pipeline."""

    SUCCESS = "SUCCESS"                                         # All portfolio criteria evaluated and limiting mechanism resolved
    SUCCESS_WITH_LIMITATIONS = "SUCCESS_WITH_LIMITATIONS"       # Evaluated successfully with valid RULs but noted evidence/uncertainty limitations
    PARTIAL_EVALUATION = "PARTIAL_EVALUATION"                   # Some criteria evaluated; others failed validity gating
    BLOCKED_BY_VALIDITY = "BLOCKED_BY_VALIDITY"                 # All criteria blocked by fatal data quality, history, or domain failures
    INDETERMINATE_LIMITING = "INDETERMINATE_LIMITING"           # Criteria evaluated, but limiting mechanism cannot be resolved across incompatible domains
    INCOMPATIBLE_PORTFOLIO = "INCOMPATIBLE_PORTFOLIO"           # Portfolio criteria incompatible with trajectory quantities
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"             # Pipeline configuration failed structural or semantic validation


class LimitingResolutionStatus(str, Enum):
    """Outcome status of the limiting degradation mechanism resolution."""

    RESOLVED = "RESOLVED"                                       # Limiting mechanism successfully identified under configured strategy
    INCOMPATIBLE_DOMAINS = "INCOMPATIBLE_DOMAINS"               # Incompatible horizon domains prevented direct numeric RUL comparison
    INCOMPATIBLE_UNITS = "INCOMPATIBLE_UNITS"                   # Incompatible units prevented direct numeric margin or RUL comparison
    ALL_CRITERIA_UNAVAILABLE = "ALL_CRITERIA_UNAVAILABLE"       # No criteria yielded a valid RUL or usable decision
    NOT_EVALUATED = "NOT_EVALUATED"                             # Limiting resolution was not performed


class LimitingResolutionStrategy(str, Enum):
    """Configurable deterministic strategy for resolving the limiting degradation mechanism."""

    SHORTEST_RUL = "SHORTEST_RUL"                               # Selects the criterion with the lowest numeric RUL value among comparable domains
    HIGHEST_DECISION_PRIORITY = "HIGHEST_DECISION_PRIORITY"     # Selects the criterion producing the most urgent RecommendationPriority / DecisionClass
    NEAREST_EOL_DISTANCE = "NEAREST_EOL_DISTANCE"               # Selects the criterion with the smallest current distance to EOL boundary
    EXPLICIT_POLICY_ORDER = "EXPLICIT_POLICY_ORDER"             # Selects the earliest valid criterion according to portfolio definition order


@dataclass(frozen=True)
class CriterionPrognosticEvaluation:
    """Immutable evaluation bundle combining single-criterion evaluation and decision results."""

    criterion_id: str
    eol_definition: EOLDefinition
    evaluation_result: PrognosticEvaluationResult
    decision_result: PrognosticDecisionResult
    is_limiting: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.criterion_id or not isinstance(self.criterion_id, str):
            raise ValueError("criterion_id must be a non-empty string.")
        if not isinstance(self.eol_definition, EOLDefinition):
            raise TypeError(f"Expected EOLDefinition, got {type(self.eol_definition).__name__}.")
        if not isinstance(self.evaluation_result, PrognosticEvaluationResult):
            raise TypeError(
                f"Expected PrognosticEvaluationResult, got {type(self.evaluation_result).__name__}."
            )
        if not isinstance(self.decision_result, PrognosticDecisionResult):
            raise TypeError(
                f"Expected PrognosticDecisionResult, got {type(self.decision_result).__name__}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes criterion evaluation bundle to dictionary."""
        return {
            "criterion_id": self.criterion_id,
            "eol_definition": self.eol_definition.to_dict(),
            "evaluation_result": self.evaluation_result.to_dict(),
            "decision_result": self.decision_result.to_dict(),
            "is_limiting": self.is_limiting,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class LimitingMechanismAssessment:
    """Immutable assessment identifying the limiting degradation failure mode.

    Strict Scientific Guarantee:
    - Never fabricates cross-domain comparisons.
    - If domains are incompatible, status is set to INCOMPATIBLE_DOMAINS and margin is None.
    """

    status: LimitingResolutionStatus
    resolution_strategy: LimitingResolutionStrategy
    limiting_criterion_id: Optional[str] = None
    limiting_criterion_type: Optional[EOLCriterionType] = None
    limiting_rul_value: Optional[float] = None
    limiting_rul_unit: Optional[str] = None
    limiting_rul_domain: Optional[HorizonDomain] = None
    limiting_decision_class: Optional[DecisionClass] = None
    limiting_priority: Optional[RecommendationPriority] = None
    margin_to_secondary_rul: Optional[float] = None
    secondary_criterion_id: Optional[str] = None
    rationale: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.status, LimitingResolutionStatus):
            raise TypeError(f"Expected LimitingResolutionStatus, got {type(self.status).__name__}.")
        if not isinstance(self.resolution_strategy, LimitingResolutionStrategy):
            raise TypeError(
                f"Expected LimitingResolutionStrategy, got {type(self.resolution_strategy).__name__}."
            )

        if self.limiting_rul_value is not None:
            if (
                not isinstance(self.limiting_rul_value, (int, float))
                or math.isnan(self.limiting_rul_value)
                or math.isinf(self.limiting_rul_value)
            ):
                raise ValueError(
                    f"limiting_rul_value must be a finite float, got {self.limiting_rul_value}."
                )

        if self.margin_to_secondary_rul is not None:
            if (
                not isinstance(self.margin_to_secondary_rul, (int, float))
                or math.isnan(self.margin_to_secondary_rul)
                or math.isinf(self.margin_to_secondary_rul)
            ):
                raise ValueError(
                    f"margin_to_secondary_rul must be a finite float, got {self.margin_to_secondary_rul}."
                )
            if self.margin_to_secondary_rul < 0.0:
                raise ValueError(
                    f"margin_to_secondary_rul must be non-negative, got {self.margin_to_secondary_rul}."
                )

        if self.status == LimitingResolutionStatus.RESOLVED:
            if not self.limiting_criterion_id:
                raise ValueError("limiting_criterion_id cannot be None when status is RESOLVED.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes limiting mechanism assessment to dictionary."""
        return {
            "status": self.status.value,
            "resolution_strategy": self.resolution_strategy.value,
            "limiting_criterion_id": self.limiting_criterion_id,
            "limiting_criterion_type": (
                self.limiting_criterion_type.value if self.limiting_criterion_type else None
            ),
            "limiting_rul_value": (
                round(float(self.limiting_rul_value), 6)
                if self.limiting_rul_value is not None
                else None
            ),
            "limiting_rul_unit": self.limiting_rul_unit,
            "limiting_rul_domain": (
                self.limiting_rul_domain.value if self.limiting_rul_domain else None
            ),
            "limiting_decision_class": (
                self.limiting_decision_class.value if self.limiting_decision_class else None
            ),
            "limiting_priority": (
                self.limiting_priority.value if self.limiting_priority else None
            ),
            "margin_to_secondary_rul": (
                round(float(self.margin_to_secondary_rul), 6)
                if self.margin_to_secondary_rul is not None
                else None
            ),
            "secondary_criterion_id": self.secondary_criterion_id,
            "rationale": self.rationale,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PrognosticAssessmentReport:
    """Immutable top-level structured report consolidating multi-criterion battery prognostics.

    Guarantees:
    1. Zero fabricated confidence percentages or synthetic probabilities.
    2. Strict safety authority separation (physical BMS remains control authority).
    3. Multi-criterion degradation transparency without cross-domain RUL mangling.
    4. Deterministic limiting mechanism resolution with secondary advisory preservation.
    """

    report_id: str
    system_id: str
    report_timestamp_ns: int
    created_at_utc: str
    pipeline_status: PipelineStatus
    limiting_mechanism: LimitingMechanismAssessment
    criteria_evaluations: Mapping[str, CriterionPrognosticEvaluation]
    primary_decision: PrognosticDecisionResult
    feature_set: Optional[DegradationFeatureSet] = None
    consolidated_secondary_advisories: Sequence[SecondaryAdvisory] = field(default_factory=tuple)
    consolidated_validity_limitations: Sequence[str] = field(default_factory=tuple)
    portfolio_id: str = ""
    policy_id: str = ""
    is_safety_critical_actuation: bool = False
    safety_authority: str = "Physical BMS"
    safety_disclaimer: str = (
        "ADVISORY ONLY: TwinVolt analytical decisions do not command physical actuators. "
        "The physical Battery Management System (BMS) remains the sole safety and protection authority."
    )
    reproducibility_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.report_id or not isinstance(self.report_id, str):
            raise ValueError("report_id must be a non-empty string.")
        if not self.system_id or not isinstance(self.system_id, str):
            raise ValueError("system_id must be a non-empty string.")
        if not isinstance(self.report_timestamp_ns, int) or self.report_timestamp_ns < 0:
            raise ValueError(
                f"report_timestamp_ns must be a non-negative integer, got {self.report_timestamp_ns}."
            )
        if not self.created_at_utc or not isinstance(self.created_at_utc, str):
            raise ValueError("created_at_utc must be a non-empty string.")
        if not isinstance(self.pipeline_status, PipelineStatus):
            raise TypeError(f"Expected PipelineStatus, got {type(self.pipeline_status).__name__}.")
        if not isinstance(self.limiting_mechanism, LimitingMechanismAssessment):
            raise TypeError(
                f"Expected LimitingMechanismAssessment, got {type(self.limiting_mechanism).__name__}."
            )
        if not isinstance(self.primary_decision, PrognosticDecisionResult):
            raise TypeError(
                f"Expected PrognosticDecisionResult, got {type(self.primary_decision).__name__}."
            )

        if self.feature_set is not None and not isinstance(self.feature_set, DegradationFeatureSet):
            raise TypeError(
                f"Expected DegradationFeatureSet, got {type(self.feature_set).__name__}."
            )

        # Invariant: Safety actuation flag must never be True
        if self.is_safety_critical_actuation is not False:
            raise ValueError(
                "is_safety_critical_actuation must be False. Digital twin cannot perform physical actuation."
            )

    @property
    def is_actionable(self) -> bool:
        """Returns True if the primary decision represents an actionable operational task."""
        return self.primary_decision.is_actionable

    @property
    def is_valid(self) -> bool:
        """Returns True if the pipeline executed without fatal data quality or portfolio failures."""
        return self.pipeline_status in (
            PipelineStatus.SUCCESS,
            PipelineStatus.SUCCESS_WITH_LIMITATIONS,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializes prognostic assessment report to dictionary."""
        return {
            "report_id": self.report_id,
            "system_id": self.system_id,
            "report_timestamp_ns": self.report_timestamp_ns,
            "created_at_utc": self.created_at_utc,
            "pipeline_status": self.pipeline_status.value,
            "is_valid": self.is_valid,
            "is_actionable": self.is_actionable,
            "limiting_mechanism": self.limiting_mechanism.to_dict(),
            "criteria_evaluations": {k: v.to_dict() for k, v in self.criteria_evaluations.items()},
            "primary_decision": self.primary_decision.to_dict(),
            "feature_set": self.feature_set.to_dict() if self.feature_set else None,
            "consolidated_secondary_advisories": [
                a.to_dict() for a in self.consolidated_secondary_advisories
            ],
            "consolidated_validity_limitations": list(self.consolidated_validity_limitations),
            "portfolio_id": self.portfolio_id,
            "policy_id": self.policy_id,
            "is_safety_critical_actuation": self.is_safety_critical_actuation,
            "safety_authority": self.safety_authority,
            "safety_disclaimer": self.safety_disclaimer,
            "reproducibility_metadata": dict(self.reproducibility_metadata),
        }
