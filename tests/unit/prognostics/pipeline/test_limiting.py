"""Unit Tests for LimitingMechanismResolver and Multi-Criterion Strategies.

Validates:
- Shortest RUL resolution within comparable domains
- Incompatible domain comparison protection (CYCLE vs TIME)
- Cross-domain fallback to priority when configured
- Incompatible units protection
- Margin calculation and domain compatibility gating
- Highest decision priority strategy
- Nearest EOL distance strategy
- Explicit policy order strategy
- Deterministic tie-breaking by criterion_id
- All criteria unavailable handling
"""

import pytest

from src.prognostics.decision.recommendation import DecisionRecommendation
from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    DecisionStatus,
    PrognosticDecisionResult,
    RecommendationPriority,
)
from src.prognostics.evaluation.types import (
    EOLAssessment,
    EOLState,
    EvaluationStatus,
    EvaluationValidity,
    PrognosticEvaluationResult,
)
from src.prognostics.pipeline.limiting import LimitingMechanismResolver
from src.prognostics.pipeline.types import (
    CriterionPrognosticEvaluation,
    LimitingResolutionStatus,
    LimitingResolutionStrategy,
)
from src.prognostics.prediction import EOLDefinition, RULPredictionResult
from src.prognostics.types import (
    ComparisonOperator,
    EOLCriterionType,
    HorizonDomain,
    PrognosticStatus,
)


def _create_candidate(
    crit_id: str,
    rul_value: float,
    domain: HorizonDomain = HorizonDomain.CYCLE,
    unit: str = "cycle",
    distance_to_eol: float = 0.10,
    priority: RecommendationPriority = RecommendationPriority.MEDIUM,
    decision_class: DecisionClass = DecisionClass.PLAN_MAINTENANCE,
    evaluation_status: EvaluationStatus = EvaluationStatus.VALID,
) -> CriterionPrognosticEvaluation:
    eol_def = EOLDefinition(
        criterion_id=crit_id,
        criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        threshold_value=0.80,
        unit="ratio",
    )
    is_valid = evaluation_status == EvaluationStatus.VALID
    pred = RULPredictionResult(
        prediction_id=f"pred_{crit_id}",
        system_id="batt_01",
        prediction_timestamp_ns=1_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        status=PrognosticStatus.VALID if is_valid else PrognosticStatus.DATA_QUALITY_FAILED,
        rul_domain=domain,
        rul_unit=unit,
        rul_value=rul_value if is_valid else None,
        eol_definition=eol_def,
    )
    eol_ass = EOLAssessment(
        eol_state=EOLState.PROJECTED,
        eol_definition=eol_def,
        threshold_value=0.80,
        comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        unit="ratio",
        quantity_name="capacity_retention_fraction",
        current_value=0.90,
        distance_to_eol=distance_to_eol,
    )
    val = EvaluationValidity(
        data_quality=PrognosticStatus.VALID if is_valid else PrognosticStatus.DATA_QUALITY_FAILED,
        history_sufficiency=PrognosticStatus.VALID,
        domain_validity=PrognosticStatus.VALID,
        eol_validity=True,
        prediction_validity=is_valid,
        is_usable_for_decision=is_valid,
    )
    eval_res = PrognosticEvaluationResult(
        evaluation_id=f"eval_{crit_id}",
        system_id="batt_01",
        evaluation_timestamp_ns=1_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        evaluation_status=evaluation_status,
        prediction=pred,
        eol_assessment=eol_ass,
        validity=val,
    )
    dec_res = PrognosticDecisionResult(
        decision_id=f"dec_{crit_id}",
        system_id="batt_01",
        decision_timestamp_ns=1_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        status=DecisionStatus.EVALUATED,
        primary_decision_class=decision_class,
        primary_priority=priority,
        primary_actionability=Actionability.ACTIONABLE,
        primary_recommendation=f"Decision for {crit_id}",
        primary_rationale="Triggered operational threshold.",
        policy_id="policy_test",
        policy_version="1.0.0",
        is_safety_critical_actuation=False,
    )
    return CriterionPrognosticEvaluation(
        criterion_id=crit_id,
        eol_definition=eol_def,
        evaluation_result=eval_res,
        decision_result=dec_res,
    )


def test_shortest_rul_same_domain():
    c1 = _create_candidate("crit_soh", rul_value=120.0, domain=HorizonDomain.CYCLE)
    c2 = _create_candidate("crit_r0", rul_value=200.0, domain=HorizonDomain.CYCLE)

    lim = LimitingMechanismResolver.resolve(
        criteria_evaluations=[c1, c2],
        strategy=LimitingResolutionStrategy.SHORTEST_RUL,
    )

    assert lim.status == LimitingResolutionStatus.RESOLVED
    assert lim.limiting_criterion_id == "crit_soh"
    assert lim.limiting_rul_value == 120.0
    assert lim.secondary_criterion_id == "crit_r0"
    assert lim.margin_to_secondary_rul == 80.0


def test_shortest_rul_incompatible_domains_protection():
    # Criterion 1 is 120 cycles; Criterion 2 is 50 hours (TIME domain)
    c1 = _create_candidate("crit_soh", rul_value=120.0, domain=HorizonDomain.CYCLE, unit="cycle")
    c2 = _create_candidate("crit_time", rul_value=50.0, domain=HorizonDomain.TIME, unit="hour")

    lim = LimitingMechanismResolver.resolve(
        criteria_evaluations=[c1, c2],
        strategy=LimitingResolutionStrategy.SHORTEST_RUL,
        allow_cross_domain_fallback_to_priority=False,
    )

    assert lim.status == LimitingResolutionStatus.INCOMPATIBLE_DOMAINS
    assert lim.limiting_criterion_id is None
    assert lim.margin_to_secondary_rul is None
    assert "Incompatible horizon domains" in lim.rationale


def test_cross_domain_fallback_to_priority():
    c1 = _create_candidate(
        "crit_soh", rul_value=120.0, domain=HorizonDomain.CYCLE, priority=RecommendationPriority.MEDIUM
    )
    c2 = _create_candidate(
        "crit_time", rul_value=50.0, domain=HorizonDomain.TIME, priority=RecommendationPriority.CRITICAL
    )

    lim = LimitingMechanismResolver.resolve(
        criteria_evaluations=[c1, c2],
        strategy=LimitingResolutionStrategy.SHORTEST_RUL,
        allow_cross_domain_fallback_to_priority=True,
    )

    assert lim.status == LimitingResolutionStatus.RESOLVED
    assert lim.limiting_criterion_id == "crit_time"
    assert lim.limiting_priority == RecommendationPriority.CRITICAL
    # Margin must be None across different domains
    assert lim.margin_to_secondary_rul is None


def test_highest_decision_priority_strategy():
    c1 = _create_candidate(
        "crit_low", rul_value=10.0, priority=RecommendationPriority.LOW, decision_class=DecisionClass.INCREASE_MONITORING
    )
    c2 = _create_candidate(
        "crit_crit", rul_value=50.0, priority=RecommendationPriority.CRITICAL, decision_class=DecisionClass.EOL_REACHED
    )

    lim = LimitingMechanismResolver.resolve(
        criteria_evaluations=[c1, c2],
        strategy=LimitingResolutionStrategy.HIGHEST_DECISION_PRIORITY,
    )

    assert lim.status == LimitingResolutionStatus.RESOLVED
    assert lim.limiting_criterion_id == "crit_crit"


def test_nearest_eol_distance_strategy():
    c1 = _create_candidate("crit_far", rul_value=200.0, distance_to_eol=0.25)
    c2 = _create_candidate("crit_close", rul_value=150.0, distance_to_eol=0.04)

    lim = LimitingMechanismResolver.resolve(
        criteria_evaluations=[c1, c2],
        strategy=LimitingResolutionStrategy.NEAREST_EOL_DISTANCE,
    )

    assert lim.status == LimitingResolutionStatus.RESOLVED
    assert lim.limiting_criterion_id == "crit_close"
    assert lim.secondary_criterion_id == "crit_far"
    assert pytest.approx(lim.margin_to_secondary_rul, rel=1e-5) == 0.21


def test_explicit_policy_order_strategy():
    c1 = _create_candidate("crit_first", rul_value=300.0)
    c2 = _create_candidate("crit_second", rul_value=50.0)

    lim = LimitingMechanismResolver.resolve(
        criteria_evaluations=[c1, c2],
        strategy=LimitingResolutionStrategy.EXPLICIT_POLICY_ORDER,
    )

    assert lim.status == LimitingResolutionStatus.RESOLVED
    assert lim.limiting_criterion_id == "crit_first"


def test_deterministic_tie_breaking():
    # Identical RUL values
    c1 = _create_candidate("crit_b", rul_value=100.0)
    c2 = _create_candidate("crit_a", rul_value=100.0)

    lim = LimitingMechanismResolver.resolve(
        criteria_evaluations=[c1, c2],
        strategy=LimitingResolutionStrategy.SHORTEST_RUL,
    )

    assert lim.status == LimitingResolutionStatus.RESOLVED
    # Deterministic alphabetical tie-break
    assert lim.limiting_criterion_id == "crit_a"
    assert lim.margin_to_secondary_rul == 0.0


def test_all_criteria_unavailable():
    c1 = _create_candidate("crit_failed", rul_value=100.0, evaluation_status=EvaluationStatus.DATA_QUALITY_FAILED)
    dec = PrognosticDecisionResult(
        decision_id="dec_indet",
        system_id="batt_01",
        decision_timestamp_ns=1_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        status=DecisionStatus.BLOCKED_BY_VALIDITY,
        primary_decision_class=DecisionClass.INDETERMINATE_STATE,
        primary_priority=RecommendationPriority.INFORMATIONAL,
        primary_actionability=Actionability.NON_ACTIONABLE,
        primary_recommendation="Indeterminate: Data quality failed",
        primary_rationale="Data quality failed",
        policy_id="policy_test",
        policy_version="1.0.0",
        is_safety_critical_actuation=False,
    )
    c1_blocked = CriterionPrognosticEvaluation(
        criterion_id="crit_failed",
        eol_definition=c1.eol_definition,
        evaluation_result=c1.evaluation_result,
        decision_result=dec,
    )

    lim = LimitingMechanismResolver.resolve(
        criteria_evaluations=[c1_blocked],
        strategy=LimitingResolutionStrategy.SHORTEST_RUL,
    )

    assert lim.status == LimitingResolutionStatus.ALL_CRITERIA_UNAVAILABLE
