"""Unit Tests for Level 6.6 Decision Policies, Conditions, and Rules.

Validates:
- DecisionCondition predicates, operators, and exact boundary semantics
- DecisionRule integrity, immutability, and precedence rank enforcement
- DecisionPolicy validation: unique rule IDs, strictly unique precedence ranks, and domain compatibility
"""

from dataclasses import FrozenInstanceError
import pytest

from src.prognostics.decision.policy import (
    DecisionCondition,
    DecisionPolicy,
    DecisionRule,
)
from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
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


def _create_sample_evaluation(
    rul_value: float = 45.0,
    domain: HorizonDomain = HorizonDomain.CYCLE,
    eval_status: EvaluationStatus = EvaluationStatus.VALID,
    eol_state: EOLState = EOLState.PROJECTED,
    evidence_strength: EvidenceStrength = EvidenceStrength.MODERATE,
    uncertainty_status: UncertaintyStatus = UncertaintyStatus.STATISTICALLY_SUPPORTED,
    is_usable: bool = True,
    data_quality: PrognosticStatus = PrognosticStatus.VALID,
) -> PrognosticEvaluationResult:
    """Helper to construct a deterministic PrognosticEvaluationResult fixture."""
    eol_def = EOLDefinition(
        criterion_id="eol_cap_80",
        criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        threshold_value=0.80,
        unit="ratio",
        comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
    )
    prediction = RULPredictionResult(
        prediction_id="pred_001",
        prediction_timestamp_ns=1_000_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        system_id="cell_001",
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
        current_value=0.85,
        distance_to_eol=0.05,
        projected_crossing_domain_value=145.0,
        is_reached=(eol_state == EOLState.ALREADY_REACHED),
    )
    validity = EvaluationValidity(
        data_quality=data_quality,
        history_sufficiency=PrognosticStatus.VALID,
        domain_validity=PrognosticStatus.VALID,
        eol_validity=True,
        prediction_validity=True,
        uncertainty_availability=uncertainty_status,
        evidence_strength=evidence_strength,
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
        evaluation_id="eval_test_001",
        system_id="cell_001",
        evaluation_timestamp_ns=1_000_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        evaluation_status=eval_status,
        eol_assessment=eol_assessment,
        validity=validity,
        prediction=prediction,
        evidence=evidence,
    )


class TestDecisionCondition:
    """Predicate matching and boundary tests for DecisionCondition."""

    def test_condition_threshold_operator_validation(self) -> None:
        """Verifies threshold and operator coupling invariants."""
        # Valid condition
        cond = DecisionCondition(
            condition_id="c1",
            rul_threshold_value=50.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        assert cond.condition_id == "c1"

        # Threshold without operator raises ValueError
        with pytest.raises(ValueError, match="rul_comparison_operator is required"):
            DecisionCondition(condition_id="c2", rul_threshold_value=50.0)

        # Operator without threshold raises ValueError
        with pytest.raises(ValueError, match="rul_threshold_value is required"):
            DecisionCondition(
                condition_id="c3",
                rul_comparison_operator=ComparisonOperator.LESS_THAN,
            )

        # Non-finite float raises ValueError
        with pytest.raises(ValueError, match="finite float"):
            DecisionCondition(
                condition_id="c4",
                rul_threshold_value=float("nan"),
                rul_comparison_operator=ComparisonOperator.LESS_THAN,
            )

    def test_condition_operator_boundary_evaluations(self) -> None:
        """Tests exact mathematical boundaries for <, <=, >, >=, ==."""
        # 1. LESS_THAN_OR_EQUAL (<=)
        cond_lte = DecisionCondition(
            condition_id="c_lte",
            rul_threshold_value=50.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        assert cond_lte.matches(_create_sample_evaluation(rul_value=49.9))[0] is True
        assert cond_lte.matches(_create_sample_evaluation(rul_value=50.0))[0] is True
        assert cond_lte.matches(_create_sample_evaluation(rul_value=50.1))[0] is False

        # 2. LESS_THAN (<)
        cond_lt = DecisionCondition(
            condition_id="c_lt",
            rul_threshold_value=50.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN,
        )
        assert cond_lt.matches(_create_sample_evaluation(rul_value=49.9))[0] is True
        assert cond_lt.matches(_create_sample_evaluation(rul_value=50.0))[0] is False

        # 3. GREATER_THAN_OR_EQUAL (>=)
        cond_gte = DecisionCondition(
            condition_id="c_gte",
            rul_threshold_value=50.0,
            rul_comparison_operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        )
        assert cond_gte.matches(_create_sample_evaluation(rul_value=50.0))[0] is True
        assert cond_gte.matches(_create_sample_evaluation(rul_value=50.1))[0] is True
        assert cond_gte.matches(_create_sample_evaluation(rul_value=49.9))[0] is False

        # 4. GREATER_THAN (>)
        cond_gt = DecisionCondition(
            condition_id="c_gt",
            rul_threshold_value=50.0,
            rul_comparison_operator=ComparisonOperator.GREATER_THAN,
        )
        assert cond_gt.matches(_create_sample_evaluation(rul_value=50.1))[0] is True
        assert cond_gt.matches(_create_sample_evaluation(rul_value=50.0))[0] is False

        # 5. EQUALS (==)
        cond_eq = DecisionCondition(
            condition_id="c_eq",
            rul_threshold_value=50.0,
            rul_comparison_operator=ComparisonOperator.EQUALS,
        )
        assert cond_eq.matches(_create_sample_evaluation(rul_value=50.0))[0] is True
        assert cond_eq.matches(_create_sample_evaluation(rul_value=50.0000000001))[0] is True
        assert cond_eq.matches(_create_sample_evaluation(rul_value=50.1))[0] is False

    def test_condition_evidence_strength_filtering(self) -> None:
        """Verifies evidence strength interval gating."""
        cond_min_mod = DecisionCondition(
            condition_id="c_ev",
            min_evidence_strength=EvidenceStrength.MODERATE,
        )
        # Moderate, Strong, Very Strong should match
        assert cond_min_mod.matches(_create_sample_evaluation(evidence_strength=EvidenceStrength.MODERATE))[0] is True
        assert cond_min_mod.matches(_create_sample_evaluation(evidence_strength=EvidenceStrength.STRONG))[0] is True
        assert cond_min_mod.matches(_create_sample_evaluation(evidence_strength=EvidenceStrength.VERY_STRONG))[0] is True
        # Weak, Very Weak, Insufficient should fail
        assert cond_min_mod.matches(_create_sample_evaluation(evidence_strength=EvidenceStrength.WEAK))[0] is False
        assert cond_min_mod.matches(_create_sample_evaluation(evidence_strength=EvidenceStrength.INSUFFICIENT))[0] is False

    def test_condition_domain_matching(self) -> None:
        """Verifies that RUL rules require matching HorizonDomain."""
        cond_cycle = DecisionCondition(
            condition_id="c_cycle",
            rul_threshold_value=50.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            rul_domain=HorizonDomain.CYCLE,
        )
        eval_cycle = _create_sample_evaluation(rul_value=40.0, domain=HorizonDomain.CYCLE)
        eval_time = _create_sample_evaluation(rul_value=40.0, domain=HorizonDomain.TIME)

        assert cond_cycle.matches(eval_cycle)[0] is True
        assert cond_cycle.matches(eval_time)[0] is False


class TestDecisionPolicy:
    """Validation and integrity tests for DecisionRule and DecisionPolicy."""

    def test_valid_policy_creation_and_serialization(self) -> None:
        """Verifies well-formed policy validation and serialization."""
        cond = DecisionCondition(
            condition_id="cond_maint_50",
            rul_threshold_value=50.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            rul_domain=HorizonDomain.CYCLE,
        )
        rule = DecisionRule(
            rule_id="rule_maint",
            precedence_rank=1,
            decision_class=DecisionClass.PLAN_MAINTENANCE,
            priority=RecommendationPriority.HIGH,
            actionability=Actionability.ACTIONABLE,
            condition=cond,
            recommendation_template="Plan pack maintenance within {rul_value} {rul_unit}.",
            rationale_template="RUL reached critical window of 50 cycles.",
        )
        policy = DecisionPolicy(
            policy_id="pol_ev_fleet",
            policy_name="EV Fleet Maintenance Policy",
            version="1.0.0",
            target_domain=HorizonDomain.CYCLE,
            rules=(rule,),
        )

        assert policy.policy_id == "pol_ev_fleet"
        assert len(policy.rules) == 1

        d = policy.to_dict()
        assert d["policy_id"] == "pol_ev_fleet"
        assert d["target_domain"] == "CYCLE"
        assert len(d["rules"]) == 1
        assert d["rules"][0]["rule_id"] == "rule_maint"

    def test_policy_rejects_duplicate_rule_ids(self) -> None:
        """Verifies that duplicate rule IDs are rejected at validation time."""
        cond1 = DecisionCondition(condition_id="c1")
        cond2 = DecisionCondition(condition_id="c2")
        rule1 = DecisionRule(
            rule_id="rule_dup",
            precedence_rank=1,
            decision_class=DecisionClass.SCHEDULE_INSPECTION,
            priority=RecommendationPriority.MEDIUM,
            actionability=Actionability.ACTIONABLE,
            condition=cond1,
            recommendation_template="Rec 1",
            rationale_template="Rat 1",
        )
        rule2 = DecisionRule(
            rule_id="rule_dup",  # Duplicate ID
            precedence_rank=2,
            decision_class=DecisionClass.PLAN_MAINTENANCE,
            priority=RecommendationPriority.HIGH,
            actionability=Actionability.ACTIONABLE,
            condition=cond2,
            recommendation_template="Rec 2",
            rationale_template="Rat 2",
        )
        with pytest.raises(ValueError, match="Duplicate rule_id 'rule_dup'"):
            DecisionPolicy(
                policy_id="pol_bad",
                policy_name="Bad Policy",
                version="1.0.0",
                rules=(rule1, rule2),
            )

    def test_policy_rejects_duplicate_precedence_ranks(self) -> None:
        """Verifies that duplicate precedence ranks are rejected to ensure strict determinism."""
        cond1 = DecisionCondition(condition_id="c1")
        cond2 = DecisionCondition(condition_id="c2")
        rule1 = DecisionRule(
            rule_id="rule_1",
            precedence_rank=5,  # Same rank
            decision_class=DecisionClass.SCHEDULE_INSPECTION,
            priority=RecommendationPriority.MEDIUM,
            actionability=Actionability.ACTIONABLE,
            condition=cond1,
            recommendation_template="Rec 1",
            rationale_template="Rat 1",
        )
        rule2 = DecisionRule(
            rule_id="rule_2",
            precedence_rank=5,  # Same rank
            decision_class=DecisionClass.PLAN_MAINTENANCE,
            priority=RecommendationPriority.HIGH,
            actionability=Actionability.ACTIONABLE,
            condition=cond2,
            recommendation_template="Rec 2",
            rationale_template="Rat 2",
        )
        with pytest.raises(ValueError, match="Duplicate precedence_rank 5"):
            DecisionPolicy(
                policy_id="pol_bad_rank",
                policy_name="Bad Rank Policy",
                version="1.0.0",
                rules=(rule1, rule2),
            )

    def test_policy_rejects_incompatible_rule_domain(self) -> None:
        """Verifies that a rule specifying a domain incompatible with policy target_domain is rejected."""
        cond = DecisionCondition(
            condition_id="c_time",
            rul_threshold_value=100.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN,
            rul_domain=HorizonDomain.TIME,  # TIME rule
        )
        rule = DecisionRule(
            rule_id="rule_time",
            precedence_rank=1,
            decision_class=DecisionClass.PLAN_MAINTENANCE,
            priority=RecommendationPriority.HIGH,
            actionability=Actionability.ACTIONABLE,
            condition=cond,
            recommendation_template="Rec",
            rationale_template="Rat",
        )
        with pytest.raises(ValueError, match="incompatible with policy target_domain 'CYCLE'"):
            DecisionPolicy(
                policy_id="pol_domain_mismatch",
                policy_name="Domain Mismatch Policy",
                version="1.0.0",
                target_domain=HorizonDomain.CYCLE,  # CYCLE policy
                rules=(rule,),
            )
