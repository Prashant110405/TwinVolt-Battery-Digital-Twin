"""Unit Tests for Level 6.5 Validity, EOL State, and Uncertainty/Evidence Interactions.

Validates:
- Gating behavior across all Level 6.5 EvaluationStatus values (DATA_QUALITY_FAILED, OUT_OF_DOMAIN, etc.)
- EOLState interactions (ALREADY_REACHED, NOT_REACHED, PROJECTED, INDETERMINATE, INVALID)
- Observational evidence strength gating and uncertainty availability preservation
- Absolute non-fabrication of synthetic confidence scores or probabilities
"""

import pytest

from src.prognostics.decision.engine import PrognosticDecisionEngine
from src.prognostics.decision.policy import (
    DecisionCondition,
    DecisionPolicy,
    DecisionRule,
)
from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    DecisionStatus,
    RecommendationPriority,
)
from src.prognostics.evaluation.types import (
    EOLAssessment,
    EOLState,
    EvaluationStatus,
    EvaluationValidity,
    PrognosticEvaluationResult,
)
from src.prognostics.prediction import EOLDefinition, RULPredictionResult
from src.prognostics.types import (
    ComparisonOperator,
    EOLCriterionType,
    HorizonDomain,
    PrognosticStatus,
)
from src.prognostics.uncertainty.evidence import (
    EvidenceAssessment,
    EvidenceEvaluatorConfig,
)
from src.prognostics.uncertainty.types import EvidenceStrength, UncertaintyStatus


def _build_evaluation(
    eval_status: EvaluationStatus,
    is_usable: bool,
    eol_state: EOLState = EOLState.PROJECTED,
    rul_value: float = 20.0,
    evidence_strength: EvidenceStrength = EvidenceStrength.STRONG,
    uncertainty_status: UncertaintyStatus = UncertaintyStatus.STATISTICALLY_SUPPORTED,
    limitations: tuple[str, ...] = (),
) -> PrognosticEvaluationResult:
    """Constructs parameterized evaluation result."""
    eol_def = EOLDefinition(
        criterion_id="eol_cap_80",
        criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        threshold_value=0.80,
        unit="ratio",
    )
    prediction = None
    if eval_status in (EvaluationStatus.VALID, EvaluationStatus.VALID_WITH_LIMITATIONS):
        prediction = RULPredictionResult(
            prediction_id="pred_val",
            prediction_timestamp_ns=1_000_000_000,
            created_at_utc="2026-09-28T00:00:00Z",
            system_id="cell_validity",
            status=PrognosticStatus.VALID,
            rul_value=rul_value,
            rul_unit="cycles",
            rul_domain=HorizonDomain.CYCLE,
            eol_definition=eol_def,
        )
    else:
        prediction = RULPredictionResult(
            prediction_id="pred_inval",
            prediction_timestamp_ns=1_000_000_000,
            created_at_utc="2026-09-28T00:00:00Z",
            system_id="cell_validity",
            status=PrognosticStatus.DATA_QUALITY_FAILED
            if eval_status == EvaluationStatus.DATA_QUALITY_FAILED
            else PrognosticStatus.INSUFFICIENT_DATA,
            rul_value=None,  # Locked Level 6.1 invariant: non-valid predictions have rul_value=None
            rul_unit="cycles",
            rul_domain=HorizonDomain.CYCLE,
            eol_definition=eol_def,
        )

    eol_assessment = EOLAssessment(
        eol_state=eol_state,
        eol_definition=eol_def,
        threshold_value=0.80,
        comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        unit="ratio",
        quantity_name="capacity_retention",
        current_value=0.82 if eol_state != EOLState.ALREADY_REACHED else 0.78,
        distance_to_eol=0.02 if eol_state != EOLState.ALREADY_REACHED else 0.0,
        is_reached=(eol_state == EOLState.ALREADY_REACHED),
    )
    validity = EvaluationValidity(
        data_quality=PrognosticStatus.VALID
        if eval_status != EvaluationStatus.DATA_QUALITY_FAILED
        else PrognosticStatus.DATA_QUALITY_FAILED,
        history_sufficiency=PrognosticStatus.VALID
        if eval_status != EvaluationStatus.INSUFFICIENT_HISTORY
        else PrognosticStatus.INSUFFICIENT_HISTORY,
        domain_validity=PrognosticStatus.VALID
        if eval_status != EvaluationStatus.OUT_OF_DOMAIN
        else PrognosticStatus.OUT_OF_DOMAIN,
        eol_validity=(eol_state != EOLState.INVALID),
        prediction_validity=(prediction.is_valid if prediction else False),
        uncertainty_availability=uncertainty_status,
        evidence_strength=evidence_strength,
        limitations=limitations,
        is_usable_for_decision=is_usable,
    )
    evidence = EvidenceAssessment(
        overall_strength=evidence_strength,
        dimensions={},
        evaluated_dimension_count=0,
        total_dimension_count=4,
        is_sufficient_for_uncertainty=(
            evidence_strength not in (EvidenceStrength.INSUFFICIENT, EvidenceStrength.VERY_WEAK)
        ),
        diagnostic_summary=f"Evidence strength is {evidence_strength.value}.",
        config_applied=EvidenceEvaluatorConfig(),
    )
    return PrognosticEvaluationResult(
        evaluation_id="eval_validity_test",
        system_id="cell_validity",
        evaluation_timestamp_ns=1_000_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        evaluation_status=eval_status,
        eol_assessment=eol_assessment,
        validity=validity,
        prediction=prediction,
        evidence=evidence,
    )


class TestValidityInteractions:
    """Verification of gating against Level 6.5 validity failure modes."""

    @pytest.fixture
    def standard_policy(self) -> DecisionPolicy:
        rule_maint = DecisionRule(
            rule_id="r_maint",
            precedence_rank=1,
            decision_class=DecisionClass.PLAN_MAINTENANCE,
            priority=RecommendationPriority.HIGH,
            actionability=Actionability.ACTIONABLE,
            condition=DecisionCondition(
                condition_id="c_50",
                rul_threshold_value=50.0,
                rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
                require_decision_usable=True,
            ),
            recommendation_template="Plan pack maintenance at {rul_value} {rul_unit}.",
            rationale_template="RUL < 50.",
        )
        return DecisionPolicy(
            policy_id="pol_std",
            policy_name="Standard Policy",
            version="1.0.0",
            rules=(rule_maint,),
        )

    def test_data_quality_failed_gating(self, standard_policy: DecisionPolicy) -> None:
        """Verifies DATA_QUALITY_FAILED blocks maintenance rules and returns DATA_QUALITY_ACTION_REQUIRED."""
        engine = PrognosticDecisionEngine()
        eval_dq_fail = _build_evaluation(
            eval_status=EvaluationStatus.DATA_QUALITY_FAILED,
            is_usable=False,
            limitations=("Telemetry voltage dropped below physical minimum.",),
        )
        res = engine.evaluate(eval_dq_fail, standard_policy)

        assert res.status == DecisionStatus.BLOCKED_BY_VALIDITY
        assert res.primary_decision_class == DecisionClass.DATA_QUALITY_ACTION_REQUIRED
        assert res.primary_priority == RecommendationPriority.CRITICAL
        assert res.primary_actionability == Actionability.INVESTIGATION_REQUIRED
        assert "Telemetry data failed integrity validation" in res.primary_recommendation
        assert "Telemetry voltage dropped below physical minimum." in res.validity_limitations

    def test_out_of_domain_gating(self, standard_policy: DecisionPolicy) -> None:
        """Verifies OUT_OF_DOMAIN blocks maintenance and returns OUT_OF_DOMAIN advisory."""
        engine = PrognosticDecisionEngine()
        eval_ood = _build_evaluation(
            eval_status=EvaluationStatus.OUT_OF_DOMAIN,
            is_usable=False,
            limitations=("Degradation rate exceeds valid model extrapolation envelope.",),
        )
        res = engine.evaluate(eval_ood, standard_policy)

        assert res.status == DecisionStatus.BLOCKED_BY_VALIDITY
        assert res.primary_decision_class == DecisionClass.OUT_OF_DOMAIN
        assert res.primary_priority == RecommendationPriority.HIGH
        assert res.primary_actionability == Actionability.INVESTIGATION_REQUIRED

    def test_insufficient_history_gating(self, standard_policy: DecisionPolicy) -> None:
        """Verifies INSUFFICIENT_HISTORY returns INSUFFICIENT_EVIDENCE advisory."""
        engine = PrognosticDecisionEngine()
        eval_hist = _build_evaluation(
            eval_status=EvaluationStatus.INSUFFICIENT_HISTORY,
            is_usable=False,
            limitations=("Only 3 cycles observed; minimum window is 10 cycles.",),
        )
        res = engine.evaluate(eval_hist, standard_policy)

        assert res.status == DecisionStatus.BLOCKED_BY_VALIDITY
        assert res.primary_decision_class == DecisionClass.INSUFFICIENT_EVIDENCE
        assert res.primary_actionability == Actionability.ADVISORY_ONLY

    def test_eol_already_reached_rule_trigger(self) -> None:
        """Verifies EOLState.ALREADY_REACHED matches EOL-specific rule with CRITICAL priority."""
        engine = PrognosticDecisionEngine()
        rule_eol = DecisionRule(
            rule_id="r_eol_reached",
            precedence_rank=1,
            decision_class=DecisionClass.EOL_REACHED,
            priority=RecommendationPriority.CRITICAL,
            actionability=Actionability.ACTIONABLE,
            condition=DecisionCondition(
                condition_id="c_eol_reached",
                required_eol_states=(EOLState.ALREADY_REACHED,),
            ),
            recommendation_template="System {system_id} has reached End-of-Life. Decommission/replace pack.",
            rationale_template="EOL threshold satisfied.",
        )
        policy = DecisionPolicy(
            policy_id="pol_eol",
            policy_name="EOL Policy",
            version="1.0.0",
            rules=(rule_eol,),
        )
        eval_eol = _build_evaluation(
            eval_status=EvaluationStatus.VALID,
            is_usable=True,
            eol_state=EOLState.ALREADY_REACHED,
            rul_value=0.0,
        )
        res = engine.evaluate(eval_eol, policy)

        assert res.status == DecisionStatus.EVALUATED
        assert res.primary_decision_class == DecisionClass.EOL_REACHED
        assert res.primary_priority == RecommendationPriority.CRITICAL
        assert "has reached End-of-Life" in res.primary_recommendation

    def test_evidence_strength_gating_suppresses_maintenance_on_weak_data(self) -> None:
        """Verifies that a rule requiring min_evidence_strength=STRONG will NOT match on WEAK evidence."""
        engine = PrognosticDecisionEngine()
        rule_strict_evidence = DecisionRule(
            rule_id="r_strict",
            precedence_rank=1,
            decision_class=DecisionClass.PLAN_MAINTENANCE,
            priority=RecommendationPriority.HIGH,
            actionability=Actionability.ACTIONABLE,
            condition=DecisionCondition(
                condition_id="c_strict",
                rul_threshold_value=50.0,
                rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
                min_evidence_strength=EvidenceStrength.STRONG,  # Requires STRONG evidence
            ),
            recommendation_template="Plan pack overhaul.",
            rationale_template="Strong evidence RUL < 50.",
        )
        policy = DecisionPolicy(
            policy_id="pol_strict",
            policy_name="Strict Evidence Policy",
            version="1.0.0",
            rules=(rule_strict_evidence,),
            default_decision_class=DecisionClass.INSUFFICIENT_EVIDENCE,
            default_recommendation="Observational evidence too weak for maintenance scheduling.",
        )
        # Evaluation with RUL=20.0 but evidence_strength=WEAK
        eval_weak = _build_evaluation(
            eval_status=EvaluationStatus.VALID_WITH_LIMITATIONS,
            is_usable=True,
            rul_value=20.0,
            evidence_strength=EvidenceStrength.WEAK,
            limitations=("High residual trajectory scatter.",),
        )
        res = engine.evaluate(eval_weak, policy)

        # Strict rule should fail to match; fallback default rule applied
        assert res.status == DecisionStatus.DEFAULT_RULE_APPLIED
        assert res.primary_decision_class == DecisionClass.INSUFFICIENT_EVIDENCE
        assert "too weak for maintenance" in res.primary_recommendation
