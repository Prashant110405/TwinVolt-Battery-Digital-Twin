"""Tests for Level 6.5 PrognosticEvaluationEngine.

Verifies end-to-end orchestration across Level 6.2, 6.3, 6.4, and 6.5,
pre-computed prediction consumption, feature extraction, determinism,
input immutability, and diagnostic traceability.
"""

from dataclasses import FrozenInstanceError
import pytest

from src.prognostics.estimators.base import EstimatorConfig
from src.prognostics.evaluation.evaluator import PrognosticEvaluationEngine
from src.prognostics.evaluation.types import (
    EOLAssessment,
    EOLState,
    EvaluationStatus,
    PrognosticEvaluationResult,
)
from src.prognostics.features import DegradationFeatureSet
from src.prognostics.horizon import PrognosticHorizon
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
from src.prognostics.uncertainty.engine import UncertaintyEngineConfig


@pytest.fixture
def eol_capacity_threshold() -> EOLDefinition:
    return EOLDefinition(
        criterion_id="eol_cap_20",
        criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
        threshold_value=2.00,
        comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        unit="Ah",
    )


@pytest.fixture
def linear_degradation_trajectory() -> DegradationTrajectory:
    """Creates a clean synthetic linear degradation trajectory with 10 points."""
    # Capacity starts at 3.00 Ah and drops 0.01 Ah per cycle
    # EOL is at 2.00 Ah (100 cycles total life)
    # At cycle 45, capacity is 2.55 Ah, RUL should be 55 cycles.
    observations = []
    for i in range(10):
        cycle = float(i * 5)  # 0, 5, 10, ..., 45
        cap = 3.00 - 0.01 * cycle  # 3.00, 2.95, ..., 2.55
        obs = DegradationObservation(
            timestamp_ns=(i + 1) * 1_000_000_000,
            created_at_utc=f"2026-09-07T00:00:0{i}Z",
            usable_capacity_ah=PrognosticQuantity(value=cap, unit="Ah", name="usable_capacity_ah"),
            equivalent_full_cycles=PrognosticQuantity(value=cycle, unit="cycles", name="equivalent_full_cycles"),
        )
        observations.append(obs)

    return DegradationTrajectory(
        trajectory_id="traj_linear_001",
        system_id="battery_cell_A1",
        observations=tuple(observations),
    )


class TestPrognosticEvaluationEngine:
    """Test suite for PrognosticEvaluationEngine."""

    def test_end_to_end_evaluation_with_linear_estimator(
        self,
        linear_degradation_trajectory: DegradationTrajectory,
        eol_capacity_threshold: EOLDefinition,
    ) -> None:
        """Verifies full prognostic evaluation pipeline from trajectory to decision report."""
        engine = PrognosticEvaluationEngine()
        result = engine.evaluate(
            trajectory=linear_degradation_trajectory,
            eol_definition=eol_capacity_threshold,
            extract_features=False,
        )

        assert isinstance(result, PrognosticEvaluationResult)
        assert result.system_id == "battery_cell_A1"
        assert result.evaluation_status in (EvaluationStatus.VALID, EvaluationStatus.VALID_WITH_LIMITATIONS)
        assert result.prediction.is_valid is True
        assert result.prediction.rul_value is not None
        # Slope is -0.01 Ah/cycle, current cap is 2.55, delta to 2.00 is 0.55 -> RUL = 55 cycles
        assert pytest.approx(result.prediction.rul_value, abs=1e-3) == 55.0

        # EOL Assessment verification
        assert result.eol_assessment.eol_state == EOLState.PROJECTED
        assert result.eol_assessment.is_reached is False
        assert pytest.approx(result.eol_assessment.current_value, abs=1e-3) == 2.55
        assert pytest.approx(result.eol_assessment.distance_to_eol, abs=1e-3) == 0.55
        assert pytest.approx(result.eol_assessment.projected_crossing_domain_value, abs=1e-3) == 100.0

        # Uncertainty & evidence verification
        assert result.uncertainty is not None
        assert result.evidence is not None

        # Validity verification
        assert result.validity.is_usable_for_decision is True
        assert result.validity.eol_validity is True
        assert result.validity.prediction_validity is True

        # Features should be None when extract_features=False
        assert result.feature_set is None

    def test_evaluation_with_feature_extraction(
        self,
        linear_degradation_trajectory: DegradationTrajectory,
        eol_capacity_threshold: EOLDefinition,
    ) -> None:
        """Verifies that extract_features=True populates DegradationFeatureSet."""
        engine = PrognosticEvaluationEngine()
        result = engine.evaluate(
            trajectory=linear_degradation_trajectory,
            eol_definition=eol_capacity_threshold,
            extract_features=True,
        )

        assert isinstance(result.feature_set, DegradationFeatureSet)
        assert result.feature_set.trajectory_id == "traj_linear_001"
        assert len(result.feature_set.features) > 0

    def test_precomputed_prediction_consumption(
        self,
        linear_degradation_trajectory: DegradationTrajectory,
        eol_capacity_threshold: EOLDefinition,
    ) -> None:
        """Verifies that engine seamlessly consumes an externally supplied RULPredictionResult."""
        precomputed = RULPredictionResult(
            prediction_id="pred_custom_99",
            prediction_timestamp_ns=10_000_000_000,
            created_at_utc="2026-09-07T00:00:09Z",
            system_id="battery_cell_A1",
            status=PrognosticStatus.VALID,
            rul_value=50.0,
            rul_unit="cycles",
            rul_domain=HorizonDomain.CYCLE,
            eol_definition=eol_capacity_threshold,
            method_identity=PrognosticMethodIdentity(
                method_id="custom_observer_01",
                method_version="2.1.0",
            ),
            diagnostic_message="Custom observer prediction.",
        )

        engine = PrognosticEvaluationEngine()
        result = engine.evaluate(
            trajectory=linear_degradation_trajectory,
            eol_definition=eol_capacity_threshold,
            precomputed_prediction=precomputed,
        )

        assert result.prediction == precomputed
        assert result.prediction.rul_value == 50.0
        assert result.prediction.method_identity.method_id == "custom_observer_01"

    def test_evaluation_determinism_and_reproducibility(
        self,
        linear_degradation_trajectory: DegradationTrajectory,
        eol_capacity_threshold: EOLDefinition,
    ) -> None:
        """Verifies that consecutive evaluations on identical inputs produce identical calculations."""
        engine = PrognosticEvaluationEngine()
        result1 = engine.evaluate(
            trajectory=linear_degradation_trajectory,
            eol_definition=eol_capacity_threshold,
        )
        result2 = engine.evaluate(
            trajectory=linear_degradation_trajectory,
            eol_definition=eol_capacity_threshold,
        )

        assert result1.evaluation_status == result2.evaluation_status
        assert result1.prediction.rul_value == result2.prediction.rul_value
        assert result1.eol_assessment.projected_crossing_domain_value == result2.eol_assessment.projected_crossing_domain_value
        assert result1.validity.is_usable_for_decision == result2.validity.is_usable_for_decision
        assert result1.validity.limitations == result2.validity.limitations

    def test_input_immutability(
        self,
        linear_degradation_trajectory: DegradationTrajectory,
        eol_capacity_threshold: EOLDefinition,
    ) -> None:
        """Verifies that evaluation results and inputs cannot be modified."""
        engine = PrognosticEvaluationEngine()
        result = engine.evaluate(
            trajectory=linear_degradation_trajectory,
            eol_definition=eol_capacity_threshold,
        )

        with pytest.raises(FrozenInstanceError):
            result.evaluation_status = EvaluationStatus.INDETERMINATE  # type: ignore

        with pytest.raises(FrozenInstanceError):
            result.system_id = "modified_cell"  # type: ignore

    def test_invalid_input_types_raise_type_error(
        self,
        linear_degradation_trajectory: DegradationTrajectory,
        eol_capacity_threshold: EOLDefinition,
    ) -> None:
        """Verifies strict input type validation."""
        engine = PrognosticEvaluationEngine()

        with pytest.raises(TypeError, match="Expected DegradationTrajectory"):
            engine.evaluate(trajectory="invalid_type", eol_definition=eol_capacity_threshold)  # type: ignore

        with pytest.raises(TypeError, match="Expected EOLDefinition"):
            engine.evaluate(trajectory=linear_degradation_trajectory, eol_definition="invalid_type")  # type: ignore

        with pytest.raises(TypeError, match="Expected RULPredictionResult"):
            engine.evaluate(
                trajectory=linear_degradation_trajectory,
                eol_definition=eol_capacity_threshold,
                precomputed_prediction="invalid_prediction",  # type: ignore
            )
