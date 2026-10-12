"""Declarative Decision Policy and Condition Contracts for Battery Prognostics.

Defines immutable, strongly-typed domain policies, conditions, and rules for evaluating
prognostic results deterministically without hardcoded battery constants or hidden thresholds.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence

from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    RecommendationPriority,
)
from src.prognostics.evaluation.types import (
    EOLState,
    EvaluationStatus,
    PrognosticEvaluationResult,
)
from src.prognostics.types import (
    ComparisonOperator,
    HorizonDomain,
    PrognosticStatus,
)
from src.prognostics.uncertainty.types import EvidenceStrength, UncertaintyStatus

# Ordered hierarchy of evidence strength for interval comparisons
_EVIDENCE_STRENGTH_ORDER = [
    EvidenceStrength.INSUFFICIENT,
    EvidenceStrength.VERY_WEAK,
    EvidenceStrength.WEAK,
    EvidenceStrength.MODERATE,
    EvidenceStrength.STRONG,
    EvidenceStrength.VERY_STRONG,
]


@dataclass(frozen=True)
class DecisionCondition:
    """Immutable declarative matching condition for a prognostic decision rule.

    All configured criteria are evaluated with logical AND conjunction.
    Unspecified (None) fields place zero constraints on matching.
    """

    condition_id: str
    required_evaluation_statuses: Optional[Sequence[EvaluationStatus]] = None
    forbidden_evaluation_statuses: Optional[Sequence[EvaluationStatus]] = None
    required_eol_states: Optional[Sequence[EOLState]] = None
    rul_threshold_value: Optional[float] = None
    rul_comparison_operator: Optional[ComparisonOperator] = None
    rul_domain: Optional[HorizonDomain] = None
    rul_unit: Optional[str] = None
    required_uncertainty_statuses: Optional[Sequence[UncertaintyStatus]] = None
    min_evidence_strength: Optional[EvidenceStrength] = None
    max_evidence_strength: Optional[EvidenceStrength] = None
    require_valid_data_quality: bool = False
    require_decision_usable: bool = False
    description: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.condition_id or not isinstance(self.condition_id, str):
            raise ValueError("condition_id must be a non-empty string.")

        if self.required_evaluation_statuses is not None:
            for s in self.required_evaluation_statuses:
                if not isinstance(s, EvaluationStatus):
                    raise TypeError(f"Expected EvaluationStatus, got {type(s).__name__}.")

        if self.forbidden_evaluation_statuses is not None:
            for s in self.forbidden_evaluation_statuses:
                if not isinstance(s, EvaluationStatus):
                    raise TypeError(f"Expected EvaluationStatus, got {type(s).__name__}.")

        if self.required_eol_states is not None:
            for s in self.required_eol_states:
                if not isinstance(s, EOLState):
                    raise TypeError(f"Expected EOLState, got {type(s).__name__}.")

        if self.rul_threshold_value is not None:
            if (
                not isinstance(self.rul_threshold_value, (int, float))
                or math.isnan(self.rul_threshold_value)
                or math.isinf(self.rul_threshold_value)
            ):
                raise ValueError(
                    f"rul_threshold_value must be a finite float, got {self.rul_threshold_value}."
                )
            if self.rul_comparison_operator is None:
                raise ValueError(
                    "rul_comparison_operator is required when rul_threshold_value is specified."
                )
            if not isinstance(self.rul_comparison_operator, ComparisonOperator):
                raise TypeError(
                    f"Expected ComparisonOperator, got {type(self.rul_comparison_operator).__name__}."
                )
        elif self.rul_comparison_operator is not None:
            raise ValueError(
                "rul_threshold_value is required when rul_comparison_operator is specified."
            )

        if self.rul_domain is not None and not isinstance(self.rul_domain, HorizonDomain):
            raise TypeError(f"Expected HorizonDomain, got {type(self.rul_domain).__name__}.")

        if self.required_uncertainty_statuses is not None:
            for s in self.required_uncertainty_statuses:
                if not isinstance(s, UncertaintyStatus):
                    raise TypeError(f"Expected UncertaintyStatus, got {type(s).__name__}.")

        if self.min_evidence_strength is not None and not isinstance(
            self.min_evidence_strength, EvidenceStrength
        ):
            raise TypeError(
                f"Expected EvidenceStrength for min_evidence_strength, got {type(self.min_evidence_strength).__name__}."
            )

        if self.max_evidence_strength is not None and not isinstance(
            self.max_evidence_strength, EvidenceStrength
        ):
            raise TypeError(
                f"Expected EvidenceStrength for max_evidence_strength, got {type(self.max_evidence_strength).__name__}."
            )

    def matches(self, evaluation: PrognosticEvaluationResult) -> tuple[bool, list[str]]:
        """Evaluates whether the given PrognosticEvaluationResult satisfies this condition.

        Returns:
            (is_matched, reasons): Boolean match indicator and list of satisfied condition clauses.
        """
        if not isinstance(evaluation, PrognosticEvaluationResult):
            raise TypeError(f"Expected PrognosticEvaluationResult, got {type(evaluation).__name__}.")

        reasons: list[str] = []

        # 1. Evaluation Status check
        if self.required_evaluation_statuses is not None:
            if evaluation.evaluation_status not in self.required_evaluation_statuses:
                return False, []
            reasons.append(f"Evaluation status is {evaluation.evaluation_status.value}")

        if self.forbidden_evaluation_statuses is not None:
            if evaluation.evaluation_status in self.forbidden_evaluation_statuses:
                return False, []

        # 2. Usability gate
        if self.require_decision_usable and not evaluation.validity.is_usable_for_decision:
            return False, []

        # 3. Data quality gate
        if self.require_valid_data_quality and evaluation.validity.data_quality != PrognosticStatus.VALID:
            return False, []

        # 4. EOL State check
        if self.required_eol_states is not None:
            if evaluation.eol_assessment.eol_state not in self.required_eol_states:
                return False, []
            reasons.append(f"EOL state is {evaluation.eol_assessment.eol_state.value}")

        # 5. Uncertainty status check
        if self.required_uncertainty_statuses is not None:
            unc_status = (
                evaluation.uncertainty.status if evaluation.uncertainty else UncertaintyStatus.UNDEFINED
            )
            if unc_status not in self.required_uncertainty_statuses:
                return False, []
            reasons.append(f"Uncertainty status is {unc_status.value}")

        # 6. Evidence strength check
        if self.min_evidence_strength is not None or self.max_evidence_strength is not None:
            ev_strength = (
                evaluation.evidence.overall_strength
                if evaluation.evidence
                else EvidenceStrength.INSUFFICIENT
            )
            current_idx = _EVIDENCE_STRENGTH_ORDER.index(ev_strength)

            if self.min_evidence_strength is not None:
                min_idx = _EVIDENCE_STRENGTH_ORDER.index(self.min_evidence_strength)
                if current_idx < min_idx:
                    return False, []
                reasons.append(
                    f"Evidence strength ({ev_strength.value}) meets minimum ({self.min_evidence_strength.value})"
                )

            if self.max_evidence_strength is not None:
                max_idx = _EVIDENCE_STRENGTH_ORDER.index(self.max_evidence_strength)
                if current_idx > max_idx:
                    return False, []
                reasons.append(
                    f"Evidence strength ({ev_strength.value}) within maximum ({self.max_evidence_strength.value})"
                )

        # 7. Numerical RUL Threshold check
        if self.rul_threshold_value is not None:
            if not evaluation.prediction or evaluation.prediction.rul_value is None:
                return False, []

            # Domain verification
            if self.rul_domain is not None and evaluation.prediction.rul_domain != self.rul_domain:
                return False, []

            # Unit verification if configured
            if self.rul_unit is not None and evaluation.prediction.rul_unit != self.rul_unit:
                return False, []

            val = evaluation.prediction.rul_value
            thresh = self.rul_threshold_value
            op = self.rul_comparison_operator

            matched = False
            if op == ComparisonOperator.LESS_THAN_OR_EQUAL:
                matched = val <= thresh
            elif op == ComparisonOperator.LESS_THAN:
                matched = val < thresh
            elif op == ComparisonOperator.GREATER_THAN_OR_EQUAL:
                matched = val >= thresh
            elif op == ComparisonOperator.GREATER_THAN:
                matched = val > thresh
            elif op == ComparisonOperator.EQUALS:
                matched = math.isclose(val, thresh, abs_tol=1e-9)

            if not matched:
                return False, []
            reasons.append(
                f"RUL ({val:.2f} {evaluation.prediction.rul_unit}) {op.value} {thresh:.2f}"
            )

        return True, reasons

    def to_dict(self) -> dict[str, Any]:
        """Serializes decision condition to dictionary."""
        return {
            "condition_id": self.condition_id,
            "required_evaluation_statuses": (
                [s.value for s in self.required_evaluation_statuses]
                if self.required_evaluation_statuses is not None
                else None
            ),
            "forbidden_evaluation_statuses": (
                [s.value for s in self.forbidden_evaluation_statuses]
                if self.forbidden_evaluation_statuses is not None
                else None
            ),
            "required_eol_states": (
                [s.value for s in self.required_eol_states]
                if self.required_eol_states is not None
                else None
            ),
            "rul_threshold_value": (
                round(float(self.rul_threshold_value), 6)
                if self.rul_threshold_value is not None
                else None
            ),
            "rul_comparison_operator": (
                self.rul_comparison_operator.value
                if self.rul_comparison_operator is not None
                else None
            ),
            "rul_domain": self.rul_domain.value if self.rul_domain is not None else None,
            "rul_unit": self.rul_unit,
            "required_uncertainty_statuses": (
                [s.value for s in self.required_uncertainty_statuses]
                if self.required_uncertainty_statuses is not None
                else None
            ),
            "min_evidence_strength": (
                self.min_evidence_strength.value
                if self.min_evidence_strength is not None
                else None
            ),
            "max_evidence_strength": (
                self.max_evidence_strength.value
                if self.max_evidence_strength is not None
                else None
            ),
            "require_valid_data_quality": self.require_valid_data_quality,
            "require_decision_usable": self.require_decision_usable,
            "description": self.description,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class DecisionRule:
    """Immutable rule entity binding a condition to a concrete operational decision."""

    rule_id: str
    precedence_rank: int
    decision_class: DecisionClass
    priority: RecommendationPriority
    actionability: Actionability
    condition: DecisionCondition
    recommendation_template: str
    rationale_template: str
    rule_name: str = ""
    description: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rule_id or not isinstance(self.rule_id, str):
            raise ValueError("rule_id must be a non-empty string.")
        if not isinstance(self.precedence_rank, int) or self.precedence_rank < 0:
            raise ValueError(
                f"precedence_rank must be a non-negative integer, got {self.precedence_rank}."
            )
        if not isinstance(self.decision_class, DecisionClass):
            raise TypeError(f"Expected DecisionClass, got {type(self.decision_class).__name__}.")
        if not isinstance(self.priority, RecommendationPriority):
            raise TypeError(f"Expected RecommendationPriority, got {type(self.priority).__name__}.")
        if not isinstance(self.actionability, Actionability):
            raise TypeError(f"Expected Actionability, got {type(self.actionability).__name__}.")
        if not isinstance(self.condition, DecisionCondition):
            raise TypeError(f"Expected DecisionCondition, got {type(self.condition).__name__}.")
        if not self.recommendation_template or not isinstance(self.recommendation_template, str):
            raise ValueError("recommendation_template must be a non-empty string.")
        if not self.rationale_template or not isinstance(self.rationale_template, str):
            raise ValueError("rationale_template must be a non-empty string.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes decision rule to dictionary."""
        return {
            "rule_id": self.rule_id,
            "precedence_rank": self.precedence_rank,
            "decision_class": self.decision_class.value,
            "priority": self.priority.value,
            "actionability": self.actionability.value,
            "condition": self.condition.to_dict(),
            "recommendation_template": self.recommendation_template,
            "rationale_template": self.rationale_template,
            "rule_name": self.rule_name,
            "description": self.description,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class DecisionPolicy:
    """Immutable, auditable decision policy for prognostic recommendation synthesis.

    Enforces strict uniqueness of rule IDs and precedence ranks to ensure 100% deterministic tie-breaking.
    """

    policy_id: str
    policy_name: str
    version: str
    rules: Sequence[DecisionRule]
    target_domain: Optional[HorizonDomain] = None
    default_decision_class: DecisionClass = DecisionClass.CONTINUE_MONITORING
    default_priority: RecommendationPriority = RecommendationPriority.INFORMATIONAL
    default_actionability: Actionability = Actionability.ADVISORY_ONLY
    default_recommendation: str = "Continue standard operational monitoring cadence."
    default_rationale: str = "Operating metrics within nominal degradation bounds; no condition threshold triggered."
    description: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.policy_id or not isinstance(self.policy_id, str):
            raise ValueError("policy_id must be a non-empty string.")
        if not self.policy_name or not isinstance(self.policy_name, str):
            raise ValueError("policy_name must be a non-empty string.")
        if not self.version or not isinstance(self.version, str):
            raise ValueError("version must be a non-empty string.")
        if self.target_domain is not None and not isinstance(self.target_domain, HorizonDomain):
            raise TypeError(f"Expected HorizonDomain, got {type(self.target_domain).__name__}.")
        if not isinstance(self.default_decision_class, DecisionClass):
            raise TypeError(
                f"Expected DecisionClass for default_decision_class, got {type(self.default_decision_class).__name__}."
            )
        if not isinstance(self.default_priority, RecommendationPriority):
            raise TypeError(
                f"Expected RecommendationPriority for default_priority, got {type(self.default_priority).__name__}."
            )
        if not isinstance(self.default_actionability, Actionability):
            raise TypeError(
                f"Expected Actionability for default_actionability, got {type(self.default_actionability).__name__}."
            )
        if not self.default_recommendation or not isinstance(self.default_recommendation, str):
            raise ValueError("default_recommendation must be a non-empty string.")
        if not self.default_rationale or not isinstance(self.default_rationale, str):
            raise ValueError("default_rationale must be a non-empty string.")

        # Execute comprehensive validation
        self.validate()

    def validate(self) -> None:
        """Validates internal consistency, uniqueness, and domain compatibility of the policy."""
        rule_ids: set[str] = set()
        ranks: set[int] = set()

        for rule in self.rules:
            if not isinstance(rule, DecisionRule):
                raise TypeError(f"Expected DecisionRule, got {type(rule).__name__}.")

            # 1. Enforce unique rule_ids
            if rule.rule_id in rule_ids:
                raise ValueError(f"Duplicate rule_id '{rule.rule_id}' in policy '{self.policy_id}'.")
            rule_ids.add(rule.rule_id)

            # 2. Enforce strictly unique precedence_rank for deterministic ordering
            if rule.precedence_rank in ranks:
                raise ValueError(
                    f"Duplicate precedence_rank {rule.precedence_rank} in policy '{self.policy_id}'. "
                    f"Rule ranks must be strictly unique to guarantee deterministic tie-breaking."
                )
            ranks.add(rule.precedence_rank)

            # 3. Domain compatibility validation
            if self.target_domain is not None and rule.condition.rul_domain is not None:
                if rule.condition.rul_domain != self.target_domain:
                    raise ValueError(
                        f"Rule '{rule.rule_id}' specifies domain '{rule.condition.rul_domain.value}' "
                        f"incompatible with policy target_domain '{self.target_domain.value}'."
                    )

    def to_dict(self) -> dict[str, Any]:
        """Serializes decision policy to dictionary."""
        return {
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "version": self.version,
            "target_domain": self.target_domain.value if self.target_domain is not None else None,
            "rules": [r.to_dict() for r in self.rules],
            "default_decision_class": self.default_decision_class.value,
            "default_priority": self.default_priority.value,
            "default_actionability": self.default_actionability.value,
            "default_recommendation": self.default_recommendation,
            "default_rationale": self.default_rationale,
            "description": self.description,
            "metadata": dict(self.metadata),
        }
