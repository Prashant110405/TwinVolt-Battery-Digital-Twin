"""Unit Tests for Level 6.7 Pipeline Domain Types and Value Objects.

Validates:
- Construction and type safety
- Immutability (frozen dataclasses)
- Non-finite numeric validation (NaN, Inf, negative margin)
- Safety invariant (is_safety_critical_actuation must be False)
- Serialization to dict and JSON round-trip
"""

from dataclasses import FrozenInstanceError
import json
import pytest

from src.prognostics.decision.recommendation import DecisionRecommendation
from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    DecisionStatus,
    PrognosticDecisionResult,
    RecommendationPriority,
    SecondaryAdvisory,
)
from src.prognostics.evaluation.types import (
    EOLAssessment,
    EOLState,
    EvaluationStatus,
    EvaluationValidity,
    PrognosticEvaluationResult,
)
from src.prognostics.pipeline.types import (
    CriterionPrognosticEvaluation,
    LimitingMechanismAssessment,
    LimitingResolutionStatus,
    LimitingResolutionStrategy,
    PipelineStatus,
    PrognosticAssessmentReport,
)
from src.prognostics.prediction import EOLDefinition, RULPredictionResult
from src.prognostics.types import (
    ComparisonOperator,
    EOLCriterionType,
    HorizonDomain,
    PrognosticStatus,
)


def _create_mock_eval_result() -> PrognosticEvaluationResult:
    eol_def = EOLDefinition(
        criterion_id="crit_soh_80",
        criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        threshold_value=0.80,
        unit="ratio",
    )
    pred = RULPredictionResult(
        prediction_id="pred_1",
        system_id="batt_01",
        prediction_timestamp_ns=1_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        status=PrognosticStatus.VALID,
        rul_domain=HorizonDomain.CYCLE,
        rul_unit="cycle",
        rul_value=150.0,
        eol_definition=eol_def,
    )
    eol_ass = EOLAssessment(
        eol_state=EOLState.PROJECTED,
        eol_definition=eol_def,
        threshold_value=0.80,
        comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        unit="ratio",
        quantity_name="capacity_retention_fraction",
        current_value=0.92,
        distance_to_eol=0.12,
    )
    val = EvaluationValidity(
        data_quality=PrognosticStatus.VALID,
        history_sufficiency=PrognosticStatus.VALID,
        domain_validity=PrognosticStatus.VALID,
        eol_validity=True,
        prediction_validity=True,
        is_usable_for_decision=True,
    )
    return PrognosticEvaluationResult(
        evaluation_id="eval_1",
        system_id="batt_01",
        evaluation_timestamp_ns=1_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        evaluation_status=EvaluationStatus.VALID,
        prediction=pred,
        eol_assessment=eol_ass,
        validity=val,
    )


def _create_mock_decision_result() -> PrognosticDecisionResult:
    return PrognosticDecisionResult(
        decision_id="dec_1",
        system_id="batt_01",
        decision_timestamp_ns=1_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        status=DecisionStatus.EVALUATED,
        primary_decision_class=DecisionClass.CONTINUE_MONITORING,
        primary_priority=RecommendationPriority.INFORMATIONAL,
        primary_actionability=Actionability.ADVISORY_ONLY,
        primary_recommendation="Continue standard monitoring.",
        primary_rationale="RUL remains well above intervention thresholds.",
        policy_id="policy_nominal",
        policy_version="1.0.0",
        is_safety_critical_actuation=False,
    )


def test_pipeline_status_enums():
    assert PipelineStatus.SUCCESS.value == "SUCCESS"
    assert PipelineStatus.SUCCESS_WITH_LIMITATIONS.value == "SUCCESS_WITH_LIMITATIONS"
    assert PipelineStatus.PARTIAL_EVALUATION.value == "PARTIAL_EVALUATION"
    assert PipelineStatus.BLOCKED_BY_VALIDITY.value == "BLOCKED_BY_VALIDITY"
    assert PipelineStatus.INDETERMINATE_LIMITING.value == "INDETERMINATE_LIMITING"


def test_limiting_resolution_strategy_enums():
    assert LimitingResolutionStrategy.SHORTEST_RUL.value == "SHORTEST_RUL"
    assert LimitingResolutionStrategy.HIGHEST_DECISION_PRIORITY.value == "HIGHEST_DECISION_PRIORITY"
    assert LimitingResolutionStrategy.NEAREST_EOL_DISTANCE.value == "NEAREST_EOL_DISTANCE"
    assert LimitingResolutionStrategy.EXPLICIT_POLICY_ORDER.value == "EXPLICIT_POLICY_ORDER"


def test_criterion_prognostic_evaluation_immutability():
    eol_def = EOLDefinition(
        criterion_id="crit_soh_80",
        criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        threshold_value=0.80,
        unit="ratio",
    )
    eval_res = _create_mock_eval_result()
    dec_res = _create_mock_decision_result()

    bundle = CriterionPrognosticEvaluation(
        criterion_id="crit_soh_80",
        eol_definition=eol_def,
        evaluation_result=eval_res,
        decision_result=dec_res,
        is_limiting=False,
    )

    assert bundle.criterion_id == "crit_soh_80"
    assert bundle.is_limiting is False

    with pytest.raises(FrozenInstanceError):
        bundle.is_limiting = True  # type: ignore[misc]


def test_limiting_mechanism_assessment_validation():
    # Valid construction
    assessment = LimitingMechanismAssessment(
        status=LimitingResolutionStatus.RESOLVED,
        resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
        limiting_criterion_id="crit_soh_80",
        limiting_criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        limiting_rul_value=120.0,
        limiting_rul_unit="cycle",
        limiting_rul_domain=HorizonDomain.CYCLE,
        limiting_decision_class=DecisionClass.CONTINUE_MONITORING,
        limiting_priority=RecommendationPriority.INFORMATIONAL,
        margin_to_secondary_rul=30.0,
        secondary_criterion_id="crit_r0_growth",
        rationale="Shortest RUL identified.",
    )
    assert assessment.status == LimitingResolutionStatus.RESOLVED
    assert assessment.margin_to_secondary_rul == 30.0

    # Non-finite RUL rejection
    with pytest.raises(ValueError, match="finite float"):
        LimitingMechanismAssessment(
            status=LimitingResolutionStatus.RESOLVED,
            resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
            limiting_criterion_id="crit_soh_80",
            limiting_rul_value=float("nan"),
        )

    # Negative margin rejection
    with pytest.raises(ValueError, match="non-negative"):
        LimitingMechanismAssessment(
            status=LimitingResolutionStatus.RESOLVED,
            resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
            limiting_criterion_id="crit_soh_80",
            margin_to_secondary_rul=-5.0,
        )

    # Resolved status requires limiting_criterion_id
    with pytest.raises(ValueError, match="limiting_criterion_id cannot be None"):
        LimitingMechanismAssessment(
            status=LimitingResolutionStatus.RESOLVED,
            resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
            limiting_criterion_id=None,
        )


def test_prognostic_assessment_report_immutability_and_safety():
    eol_def = EOLDefinition(
        criterion_id="crit_soh_80",
        criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        threshold_value=0.80,
        unit="ratio",
    )
    eval_res = _create_mock_eval_result()
    dec_res = _create_mock_decision_result()
    bundle = CriterionPrognosticEvaluation(
        criterion_id="crit_soh_80",
        eol_definition=eol_def,
        evaluation_result=eval_res,
        decision_result=dec_res,
        is_limiting=True,
    )
    lim_ass = LimitingMechanismAssessment(
        status=LimitingResolutionStatus.RESOLVED,
        resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
        limiting_criterion_id="crit_soh_80",
        limiting_rul_value=150.0,
        limiting_rul_unit="cycle",
        limiting_rul_domain=HorizonDomain.CYCLE,
    )

    report = PrognosticAssessmentReport(
        report_id="rep_001",
        system_id="batt_01",
        report_timestamp_ns=1_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        pipeline_status=PipelineStatus.SUCCESS,
        limiting_mechanism=lim_ass,
        criteria_evaluations={"crit_soh_80": bundle},
        primary_decision=dec_res,
        portfolio_id="portfolio_main",
        policy_id="policy_nominal",
        is_safety_critical_actuation=False,
    )

    assert report.is_valid is True
    assert report.is_actionable is False
    assert report.safety_authority == "Physical BMS"

    # Immutability
    with pytest.raises(FrozenInstanceError):
        report.system_id = "other_system"  # type: ignore[misc]

    # Invariant: is_safety_critical_actuation must never be True
    with pytest.raises(ValueError, match="is_safety_critical_actuation must be False"):
        PrognosticAssessmentReport(
            report_id="rep_001",
            system_id="batt_01",
            report_timestamp_ns=1_000_000,
            created_at_utc="2026-09-28T00:00:00Z",
            pipeline_status=PipelineStatus.SUCCESS,
            limiting_mechanism=lim_ass,
            criteria_evaluations={"crit_soh_80": bundle},
            primary_decision=dec_res,
            is_safety_critical_actuation=True,  # type: ignore[arg-type]
        )


def test_json_roundtrip_serialization():
    eol_def = EOLDefinition(
        criterion_id="crit_soh_80",
        criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        threshold_value=0.80,
        unit="ratio",
    )
    eval_res = _create_mock_eval_result()
    dec_res = _create_mock_decision_result()
    bundle = CriterionPrognosticEvaluation(
        criterion_id="crit_soh_80",
        eol_definition=eol_def,
        evaluation_result=eval_res,
        decision_result=dec_res,
        is_limiting=True,
    )
    lim_ass = LimitingMechanismAssessment(
        status=LimitingResolutionStatus.RESOLVED,
        resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
        limiting_criterion_id="crit_soh_80",
        limiting_rul_value=150.0,
        limiting_rul_unit="cycle",
        limiting_rul_domain=HorizonDomain.CYCLE,
    )
    report = PrognosticAssessmentReport(
        report_id="rep_001",
        system_id="batt_01",
        report_timestamp_ns=1_000_000,
        created_at_utc="2026-09-28T00:00:00Z",
        pipeline_status=PipelineStatus.SUCCESS,
        limiting_mechanism=lim_ass,
        criteria_evaluations={"crit_soh_80": bundle},
        primary_decision=dec_res,
        portfolio_id="portfolio_main",
        policy_id="policy_nominal",
    )

    d = report.to_dict()
    assert isinstance(d, dict)
    # Ensure JSON serializable
    json_str = json.dumps(d, indent=2)
    assert "rep_001" in json_str
    assert "crit_soh_80" in json_str
    assert "Physical BMS" in json_str
