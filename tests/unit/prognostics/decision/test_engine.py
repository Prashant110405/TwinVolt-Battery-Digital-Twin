"""Unit Tests for Prognostic Decision Engine and Deterministic Precedence Resolution.

Validates:
- Pure deterministic evaluation on identical inputs
- Single rule matching and recommendation template synthesis
- Policy default rule fallback when no condition matches
- Multi-rule matching and strict precedence resolution via unique precedence_rank
- Secondary advisory synthesis and preservation
- Policy target domain mismatch handling
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


def _create_eval_result(
    rul_value: float = 30.0,
    domain: HorizonDomain = HorizonDomain.CYCLE,
    eol_state: EOLState = EOLState.PROJECTED,
) -> PrognosticEvaluationResult:
    """Helper to construct evaluation result fixture."""
    eol_def = EOLDefinition(
        criterion_id="eol_cap_80",
        criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        threshold_value=0.80,
        unit="ratio",
    )
    prediction = RULPredictionResult(
        prediction_id="pred_123",
        prediction_timestamp_ns=1_500_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        system_id="pack_alpha",
        status=PrognosticStatus.VALID,
        rul_value=rul_value,
        rul_unit="cycles" if domain == HorizonDomain.CYCLE else "hours",
        rul_domain=domain,
        eol_definition=eol_def,
    )
    eol_assessment = EOLAssessment(
        eol_state=eol_state,
        eol_definition=eol_def,
        threshold_value=0.80,
        comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        unit="ratio",
        quantity_name="capacity_retention",
        current_value=0.82,
        distance_to_eol=0.02,
        projected_crossing_domain_value=130.0,
        is_reached=(eol_state == EOLState.ALREADY_REACHED),
    )
    validity = EvaluationValidity(
        data_quality=PrognosticStatus.VALID,
        history_sufficiency=PrognosticStatus.VALID,
        domain_validity=PrognosticStatus.VALID,
        eol_validity=True,
        prediction_validity=True,
        uncertainty_availability=UncertaintyStatus.STATISTICALLY_SUPPORTED,
        evidence_strength=EvidenceStrength.STRONG,
        limitations=("Statistical uncertainty is limited.",),
        is_usable_for_decision=True,
    )
    evidence = EvidenceAssessment(
        overall_strength=EvidenceStrength.STRONG,
        dimensions={},
        evaluated_dimension_count=0,
        total_dimension_count=4,
        is_sufficient_for_uncertainty=True,
        diagnostic_summary="Evidence strength is STRONG.",
        config_applied=EvidenceEvaluatorConfig(),
    )
    return PrognosticEvaluationResult(
        evaluation_id="eval_123",
        system_id="pack_alpha",
        evaluation_timestamp_ns=1_500_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        evaluation_status=EvaluationStatus.VALID_WITH_LIMITATIONS,
        eol_assessment=eol_assessment,
        validity=validity,
        prediction=prediction,
        evidence=evidence,
    )


class TestDecisionEngine:
    """Test suite for PrognosticDecisionEngine."""

    def test_deterministic_identical_evaluation(self) -> None:
        """Verifies that running evaluation repeatedly with identical inputs yields identical results."""
        engine = PrognosticDecisionEngine()
        cond = DecisionCondition(
            condition_id="c_maint",
            rul_threshold_value=50.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        rule = DecisionRule(
            rule_id="r_maint",
            precedence_rank=1,
            decision_class=DecisionClass.PLAN_MAINTENANCE,
            priority=RecommendationPriority.HIGH,
            actionability=Actionability.ACTIONABLE,
            condition=cond,
            recommendation_template="Overhaul system {system_id} before {rul_value} {rul_unit}.",
            rationale_template="Impending boundary.",
        )
        policy = DecisionPolicy(
            policy_id="pol_det",
            policy_name="Deterministic Policy",
            version="1.0.0",
            rules=(rule,),
        )
        eval_res = _create_eval_result(rul_value=30.0)

        res1 = engine.evaluate(eval_res, policy)
        res2 = engine.evaluate(eval_res, policy)

        assert res1.to_dict() == res2.to_dict()
        assert res1.status == DecisionStatus.EVALUATED
        assert res1.primary_decision_class == DecisionClass.PLAN_MAINTENANCE
        assert "Overhaul system pack_alpha before 30.00 cycles." in res1.primary_recommendation

    def test_default_rule_applied_when_no_match(self) -> None:
        """Verifies fallback to policy default when no rule threshold is satisfied."""
        engine = PrognosticDecisionEngine()
        cond = DecisionCondition(
            condition_id="c_crit",
            rul_threshold_value=10.0,  # RUL=30 will not trigger this
            rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        rule = DecisionRule(
            rule_id="r_crit",
            precedence_rank=1,
            decision_class=DecisionClass.APPROACHING_EOL,
            priority=RecommendationPriority.CRITICAL,
            actionability=Actionability.ACTIONABLE,
            condition=cond,
            recommendation_template="Critical maintenance required.",
            rationale_template="RUL < 10.",
        )
        policy = DecisionPolicy(
            policy_id="pol_default",
            policy_name="Default Policy",
            version="1.0.0",
            rules=(rule,),
            default_decision_class=DecisionClass.CONTINUE_MONITORING,
            default_recommendation="Standard monitoring for {system_id}.",
            default_rationale="Nominal wear rate.",
        )
        eval_res = _create_eval_result(rul_value=30.0)
        res = engine.evaluate(eval_res, policy)

        assert res.status == DecisionStatus.DEFAULT_RULE_APPLIED
        assert res.primary_decision_class == DecisionClass.CONTINUE_MONITORING
        assert res.primary_recommendation == "Standard monitoring for pack_alpha."
        assert res.primary_rule_id is None
        assert len(res.matched_rule_ids) == 0

    def test_multi_rule_precedence_and_secondary_preservation(self) -> None:
        """Verifies that lower precedence rank wins and remaining matches become SecondaryAdvisories."""
        engine = PrognosticDecisionEngine()
        # Rule A: rank 1, RUL <= 50 -> PLAN_MAINTENANCE
        rule_a = DecisionRule(
            rule_id="rule_maint",
            precedence_rank=1,
            decision_class=DecisionClass.PLAN_MAINTENANCE,
            priority=RecommendationPriority.HIGH,
            actionability=Actionability.ACTIONABLE,
            condition=DecisionCondition(
                condition_id="cond_50",
                rul_threshold_value=50.0,
                rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            ),
            recommendation_template="Primary: Plan maintenance at {rul_value} {rul_unit}.",
            rationale_template="RUL is below 50.",
        )
        # Rule B: rank 5, RUL <= 100 -> INCREASE_MONITORING
        rule_b = DecisionRule(
            rule_id="rule_monitor",
            precedence_rank=5,
            decision_class=DecisionClass.INCREASE_MONITORING,
            priority=RecommendationPriority.LOW,
            actionability=Actionability.ADVISORY_ONLY,
            condition=DecisionCondition(
                condition_id="cond_100",
                rul_threshold_value=100.0,
                rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            ),
            recommendation_template="Secondary: Increase monitoring cadence.",
            rationale_template="RUL is below 100.",
        )
        # Rule C: rank 10, EOLState == PROJECTED -> SCHEDULE_INSPECTION
        rule_c = DecisionRule(
            rule_id="rule_inspect",
            precedence_rank=10,
            decision_class=DecisionClass.SCHEDULE_INSPECTION,
            priority=RecommendationPriority.MEDIUM,
            actionability=Actionability.ADVISORY_ONLY,
            condition=DecisionCondition(
                condition_id="cond_projected",
                required_eol_states=(EOLState.PROJECTED,),
            ),
            recommendation_template="Secondary: Schedule visual inspection.",
            rationale_template="EOL crossing is projected.",
        )

        # Policy with rules passed in reverse rank order to prove order-independence
        policy = DecisionPolicy(
            policy_id="pol_precedence",
            policy_name="Precedence Resolution Policy",
            version="1.0.0",
            rules=(rule_c, rule_b, rule_a),  # Ranks 10, 5, 1
        )
        eval_res = _create_eval_result(rul_value=25.0, eol_state=EOLState.PROJECTED)
        res = engine.evaluate(eval_res, policy)

        # All 3 rules match RUL=25 and EOLState=PROJECTED
        assert res.status == DecisionStatus.EVALUATED
        assert res.primary_rule_id == "rule_maint"  # Rank 1 wins
        assert res.primary_decision_class == DecisionClass.PLAN_MAINTENANCE
        assert "Primary: Plan maintenance at 25.00 cycles." in res.primary_recommendation
        assert res.matched_rule_ids == ("rule_maint", "rule_monitor", "rule_inspect")

        # Secondary advisories should contain the remaining 2 matches in rank order
        assert len(res.secondary_advisories) == 2
        assert res.secondary_advisories[0].advisory_id == "adv_rule_monitor"
        assert res.secondary_advisories[0].decision_class == DecisionClass.INCREASE_MONITORING
        assert res.secondary_advisories[1].advisory_id == "adv_rule_inspect"
        assert res.secondary_advisories[1].decision_class == DecisionClass.SCHEDULE_INSPECTION

    def test_target_domain_mismatch_between_policy_and_prediction(self) -> None:
        """Verifies that evaluating a CYCLE prediction with a TIME policy returns INCOMPATIBLE_EVALUATION."""
        engine = PrognosticDecisionEngine()
        cond = DecisionCondition(
            condition_id="c_time",
            rul_threshold_value=500.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        rule = DecisionRule(
            rule_id="r_time",
            precedence_rank=1,
            decision_class=DecisionClass.PLAN_MAINTENANCE,
            priority=RecommendationPriority.HIGH,
            actionability=Actionability.ACTIONABLE,
            condition=cond,
            recommendation_template="Rec",
            rationale_template="Rat",
        )
        policy_time = DecisionPolicy(
            policy_id="pol_time",
            policy_name="Time Domain Policy",
            version="1.0.0",
            target_domain=HorizonDomain.TIME,
            rules=(rule,),
        )
        eval_cycle = _create_eval_result(rul_value=30.0, domain=HorizonDomain.CYCLE)
        res = engine.evaluate(eval_cycle, policy_time)

        assert res.status == DecisionStatus.INCOMPATIBLE_EVALUATION
        assert res.primary_decision_class == DecisionClass.INDETERMINATE_STATE
        assert res.primary_actionability == Actionability.NON_ACTIONABLE
        assert "incompatible with policy target_domain" in res.primary_rationale

    def test_policy_with_empty_rules_applies_default(self) -> None:
        """Verifies that a policy with no rules safely applies the default rule."""
        engine = PrognosticDecisionEngine()
        policy = DecisionPolicy(
            policy_id="pol_empty_rules",
            policy_name="Empty Policy",
            version="1.0.0",
            rules=(),
            default_decision_class=DecisionClass.CONTINUE_MONITORING,
            default_recommendation="Baseline monitoring active.",
        )
        eval_res = _create_eval_result(rul_value=40.0)
        res = engine.evaluate(eval_res, policy)

        assert res.status == DecisionStatus.DEFAULT_RULE_APPLIED
        assert res.primary_decision_class == DecisionClass.CONTINUE_MONITORING
        assert res.primary_recommendation == "Baseline monitoring active."
        assert len(res.secondary_advisories) == 0

    def test_json_serialization_round_trip(self) -> None:
        """Verifies that PrognosticDecisionResult can be serialized to JSON and deserialized."""
        import json

        engine = PrognosticDecisionEngine()
        cond = DecisionCondition(
            condition_id="c_50",
            rul_threshold_value=50.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        rule = DecisionRule(
            rule_id="r_50",
            precedence_rank=1,
            decision_class=DecisionClass.PLAN_MAINTENANCE,
            priority=RecommendationPriority.HIGH,
            actionability=Actionability.ACTIONABLE,
            condition=cond,
            recommendation_template="Plan pack overhaul within {rul_value} {rul_unit}.",
            rationale_template="RUL is below 50 cycles.",
        )
        policy = DecisionPolicy(
            policy_id="pol_json",
            policy_name="JSON Policy",
            version="1.0.0",
            rules=(rule,),
        )
        eval_res = _create_eval_result(rul_value=35.0)
        res = engine.evaluate(eval_res, policy)

        d = res.to_dict()
        json_str = json.dumps(d)
        loaded = json.loads(json_str)

        assert loaded["decision_id"] == res.decision_id
        assert loaded["status"] == "EVALUATED"
        assert loaded["primary_decision_class"] == "PLAN_MAINTENANCE"
        assert loaded["is_actionable"] is True
        assert loaded["is_safety_critical_actuation"] is False

