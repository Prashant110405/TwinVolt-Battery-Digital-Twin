"""Tests for Level 6.5 Evaluation Validity Evaluator.

Verifies multidimensional validity evaluation, limitation categorization,
decoupled uncertainty/validity semantics, and diagnostic traceability.
"""

import pytest

from src.prognostics.evaluation.types import (
    EOLAssessment,
    EOLState,
    EvaluationStatus,
    EvaluationValidity,
)
from src.prognostics.evaluation.validity import EvaluationValidityEvaluator
from src.prognostics.prediction import (
    EOLDefinition,
    PredictionUncertainty,
    PrognosticMethodIdentity,
    RULPredictionResult,
)
from src.prognostics.provenance import PrognosticQuantity
from src.prognostics.trajectory import DegradationObservation, DegradationTrajectory
from src.prognostics.types import (
    ComparisonOperator,
    EOLCriterionType,
    HorizonDomain,
    PrognosticStatus,
    UncertaintyType,
)
from src.prognostics.uncertainty.engine import UncertaintyEvaluationResult
from src.prognostics.uncertainty.evidence import (
    EvidenceAssessment,
    EvidenceDimensionRecord,
    EvidenceEvaluatorConfig,
)
from src.prognostics.uncertainty.types import (
    EvidenceStrength,
    UncertaintyBound,
    UncertaintyIntervalType,
    UncertaintyStatus,
)


@pytest.fixture
def base_eol_def() -> EOLDefinition:
    return EOLDefinition(
        criterion_id="eol_cap_24",
        criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
        threshold_value=2.40,
        comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        unit="Ah",
    )


@pytest.fixture
def base_eol_assessment(base_eol_def: EOLDefinition) -> EOLAssessment:
    return EOLAssessment(
        eol_state=EOLState.PROJECTED,
        eol_definition=base_eol_def,
        threshold_value=2.40,
        comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        unit="Ah",
        quantity_name="usable_capacity_ah",
        current_value=2.80,
        distance_to_eol=0.40,
        projected_crossing_domain_value=120.0,
        is_reached=False,
        diagnostic_message="EOL is projected in future domain.",
    )


@pytest.fixture
def valid_rul_prediction(base_eol_def: EOLDefinition) -> RULPredictionResult:
    return RULPredictionResult(
        prediction_id="rul_pred_001",
        prediction_timestamp_ns=1_700_000_000_000_000_000,
        created_at_utc="2026-09-07T00:00:00Z",
        system_id="cell_001",
        status=PrognosticStatus.VALID,
        rul_value=120.0,
        rul_unit="cycles",
        rul_domain=HorizonDomain.CYCLE,
        eol_definition=base_eol_def,
        method_identity=PrognosticMethodIdentity(
            method_id="linear_extrap_01",
            method_version="1.0.0",
        ),
        uncertainty=PredictionUncertainty(
            uncertainty_type=UncertaintyType.CONFIDENCE_BOUNDS,
            lower_bound=100.0,
            upper_bound=140.0,
            unit="cycles",
        ),
        diagnostic_message="Linear extrapolation successful.",
    )


@pytest.fixture
def valid_uncertainty() -> UncertaintyEvaluationResult:
    evidence = EvidenceAssessment(
        overall_strength=EvidenceStrength.STRONG,
        dimensions={
            "sample_count": EvidenceDimensionRecord(
                dimension_name="sample_count",
                evaluated=True,
                strength=EvidenceStrength.STRONG,
                input_value=50,
                rationale="High sample count",
            ),
        },
        evaluated_dimension_count=1,
        total_dimension_count=1,
        is_sufficient_for_uncertainty=True,
        diagnostic_summary="Strong evidence supporting projection.",
        config_applied=EvidenceEvaluatorConfig(),
    )
    return UncertaintyEvaluationResult(
        evaluation_id="eval_unc_001",
        prediction_id="rul_pred_001",
        created_at_utc="2026-09-07T00:00:00Z",
        status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
        prediction_uncertainty=PredictionUncertainty(
            uncertainty_type=UncertaintyType.CONFIDENCE_BOUNDS,
            lower_bound=100.0,
            upper_bound=140.0,
            unit="cycles",
        ),
        rul_value=120.0,
        rul_unit="cycles",
        evidence_assessment=evidence,
        bounds=UncertaintyBound(
            lower=100.0,
            upper=140.0,
            coverage_parameter=2.0,
            interval_type=UncertaintyIntervalType.CONFIDENCE_INTERVAL,
        ),
        diagnostic_message="Statistical uncertainty justified.",
    )


class TestEvaluationValidityEvaluator:
    """Test suite for EvaluationValidityEvaluator."""

    def test_fully_valid_evaluation(
        self,
        valid_rul_prediction: RULPredictionResult,
        base_eol_assessment: EOLAssessment,
        valid_uncertainty: UncertaintyEvaluationResult,
    ) -> None:
        """Verifies that complete and high-quality inputs yield EvaluationStatus.VALID."""
        eval_status, validity = EvaluationValidityEvaluator.evaluate_validity(
            prediction=valid_rul_prediction,
            eol_assessment=base_eol_assessment,
            uncertainty=valid_uncertainty,
            evidence=valid_uncertainty.evidence_assessment,
        )

        assert eval_status == EvaluationStatus.VALID
        assert validity.is_usable_for_decision is True
        assert len(validity.limitations) == 0
        assert validity.data_quality == PrognosticStatus.VALID
        assert validity.history_sufficiency == PrognosticStatus.VALID
        assert validity.eol_validity is True
        assert validity.prediction_validity is True

    def test_decoupled_validity_with_unavailable_uncertainty(
        self,
        valid_rul_prediction: RULPredictionResult,
        base_eol_assessment: EOLAssessment,
    ) -> None:
        """Verifies that valid RUL with unavailable uncertainty evaluates to VALID_WITH_LIMITATIONS."""
        eval_status, validity = EvaluationValidityEvaluator.evaluate_validity(
            prediction=valid_rul_prediction,
            eol_assessment=base_eol_assessment,
            uncertainty=None,
            evidence=None,
        )

        assert eval_status == EvaluationStatus.VALID_WITH_LIMITATIONS
        assert validity.is_usable_for_decision is True
        assert any("Statistical uncertainty is limited or undefined" in lim for lim in validity.limitations)

    def test_decoupled_validity_with_weak_evidence(
        self,
        valid_rul_prediction: RULPredictionResult,
        base_eol_assessment: EOLAssessment,
        valid_uncertainty: UncertaintyEvaluationResult,
    ) -> None:
        """Verifies that weak evidence degrades evaluation to VALID_WITH_LIMITATIONS."""
        weak_evidence = EvidenceAssessment(
            overall_strength=EvidenceStrength.WEAK,
            dimensions={},
            evaluated_dimension_count=0,
            total_dimension_count=1,
            is_sufficient_for_uncertainty=False,
            diagnostic_summary="Weak evidence",
            config_applied=EvidenceEvaluatorConfig(),
        )

        eval_status, validity = EvaluationValidityEvaluator.evaluate_validity(
            prediction=valid_rul_prediction,
            eol_assessment=base_eol_assessment,
            uncertainty=valid_uncertainty,
            evidence=weak_evidence,
        )

        assert eval_status == EvaluationStatus.VALID_WITH_LIMITATIONS
        assert validity.is_usable_for_decision is True
        assert any("Observational evidence strength is WEAK" in lim for lim in validity.limitations)

    def test_insufficient_history_evaluation(
        self,
        base_eol_def: EOLDefinition,
        base_eol_assessment: EOLAssessment,
    ) -> None:
        """Verifies that INSUFFICIENT_HISTORY status propagates to evaluation validity."""
        pred = RULPredictionResult(
            prediction_id="rul_pred_ih",
            prediction_timestamp_ns=1_700_000_000_000_000_000,
            created_at_utc="2026-09-07T00:00:00Z",
            system_id="cell_001",
            status=PrognosticStatus.INSUFFICIENT_HISTORY,
            rul_value=None,
            rul_unit="cycles",
            rul_domain=HorizonDomain.CYCLE,
            eol_definition=base_eol_def,
            diagnostic_message="Need at least 2 points for linear extrapolation.",
        )

        eval_status, validity = EvaluationValidityEvaluator.evaluate_validity(
            prediction=pred,
            eol_assessment=base_eol_assessment,
        )

        assert eval_status == EvaluationStatus.INSUFFICIENT_HISTORY
        assert validity.is_usable_for_decision is False
        assert validity.history_sufficiency == PrognosticStatus.INSUFFICIENT_HISTORY
        assert any("insufficient" in lim.lower() for lim in validity.limitations)

    def test_data_quality_failed_evaluation(
        self,
        base_eol_def: EOLDefinition,
        base_eol_assessment: EOLAssessment,
    ) -> None:
        """Verifies that DATA_QUALITY_FAILED status propagates correctly."""
        pred = RULPredictionResult(
            prediction_id="rul_pred_dqf",
            prediction_timestamp_ns=1_700_000_000_000_000_000,
            created_at_utc="2026-09-07T00:00:00Z",
            system_id="cell_001",
            status=PrognosticStatus.DATA_QUALITY_FAILED,
            rul_value=None,
            rul_unit="cycles",
            rul_domain=HorizonDomain.CYCLE,
            eol_definition=base_eol_def,
            diagnostic_message="Non-monotonic timestamps detected in trajectory.",
        )

        eval_status, validity = EvaluationValidityEvaluator.evaluate_validity(
            prediction=pred,
            eol_assessment=base_eol_assessment,
        )

        assert eval_status == EvaluationStatus.DATA_QUALITY_FAILED
        assert validity.is_usable_for_decision is False
        assert validity.data_quality == PrognosticStatus.DATA_QUALITY_FAILED
        assert any("data quality" in lim.lower() for lim in validity.limitations)

    def test_out_of_domain_evaluation(
        self,
        base_eol_def: EOLDefinition,
        base_eol_assessment: EOLAssessment,
    ) -> None:
        """Verifies that OUT_OF_DOMAIN status is handled."""
        pred = RULPredictionResult(
            prediction_id="rul_pred_ood",
            prediction_timestamp_ns=1_700_000_000_000_000_000,
            created_at_utc="2026-09-07T00:00:00Z",
            system_id="cell_001",
            status=PrognosticStatus.OUT_OF_DOMAIN,
            rul_value=None,
            rul_unit="cycles",
            rul_domain=HorizonDomain.CYCLE,
            eol_definition=base_eol_def,
            diagnostic_message="Operating temperature out of domain.",
        )

        eval_status, validity = EvaluationValidityEvaluator.evaluate_validity(
            prediction=pred,
            eol_assessment=base_eol_assessment,
        )

        assert eval_status == EvaluationStatus.OUT_OF_DOMAIN
        assert validity.is_usable_for_decision is False
        assert validity.domain_validity == PrognosticStatus.OUT_OF_DOMAIN
        assert any("out-of-domain" in lim.lower() for lim in validity.limitations)

    def test_invalid_eol_criterion_evaluation(
        self,
        valid_rul_prediction: RULPredictionResult,
        base_eol_def: EOLDefinition,
    ) -> None:
        """Verifies that invalid EOL criterion results in INVALID_EOL_CRITERION status."""
        invalid_eol = EOLAssessment(
            eol_state=EOLState.INVALID,
            eol_definition=base_eol_def,
            threshold_value=2.40,
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            unit="Ah",
            quantity_name="usable_capacity_ah",
            current_value=None,
            distance_to_eol=None,
            projected_crossing_domain_value=None,
            diagnostic_message="Threshold value must be positive.",
        )

        eval_status, validity = EvaluationValidityEvaluator.evaluate_validity(
            prediction=valid_rul_prediction,
            eol_assessment=invalid_eol,
        )

        assert eval_status == EvaluationStatus.INVALID_EOL_CRITERION
        assert validity.is_usable_for_decision is False
        assert validity.eol_validity is False
        assert any("EOL criterion is invalid" in lim for lim in validity.limitations)

    def test_eol_already_reached_evaluation(
        self,
        base_eol_def: EOLDefinition,
        valid_uncertainty: UncertaintyEvaluationResult,
    ) -> None:
        """Verifies that ALREADY_REACHED EOL state results in VALID status with EOL reached note."""
        eol_reached = EOLAssessment(
            eol_state=EOLState.ALREADY_REACHED,
            eol_definition=base_eol_def,
            threshold_value=2.40,
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            unit="Ah",
            quantity_name="usable_capacity_ah",
            current_value=2.35,
            distance_to_eol=0.0,
            projected_crossing_domain_value=50.0,
            is_reached=True,
            diagnostic_message="EOL threshold already reached.",
        )
        pred = RULPredictionResult(
            prediction_id="rul_pred_eol",
            prediction_timestamp_ns=1_700_000_000_000_000_000,
            created_at_utc="2026-09-07T00:00:00Z",
            system_id="cell_001",
            status=PrognosticStatus.VALID,
            rul_value=0.0,
            rul_unit="cycles",
            rul_domain=HorizonDomain.CYCLE,
            eol_definition=base_eol_def,
            diagnostic_message="EOL already reached, RUL is 0.0.",
        )

        eval_status, validity = EvaluationValidityEvaluator.evaluate_validity(
            prediction=pred,
            eol_assessment=eol_reached,
            uncertainty=valid_uncertainty,
            evidence=valid_uncertainty.evidence_assessment,
        )

        assert eval_status == EvaluationStatus.VALID
        assert validity.is_usable_for_decision is True
        assert any("exceeds configured EOL" in note for note in validity.diagnostic_notes)
