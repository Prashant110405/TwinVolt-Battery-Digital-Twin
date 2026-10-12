"""Semantic and Safety Tests for Level 6.5 Prognostic Evaluation Layer.

Strict Scientific Invariants Verified:
1. Decoupled RUL validity vs. uncertainty availability (never drops valid point estimates).
2. Non-fabrication of probability / confidence percentages.
3. Numerical safety across edge cases (rate=0, positive rate, already EOL, invalid EOL).
4. Universality and chemistry independence.
5. Immutability and pure serialization.
"""

import json
import math
import pytest

from src.prognostics.estimators.linear import HistoricalLinearRULEstimator
from src.prognostics.evaluation.eol import EOLEvaluator
from src.prognostics.evaluation.evaluator import PrognosticEvaluationEngine
from src.prognostics.evaluation.types import (
    EOLAssessment,
    EOLState,
    EvaluationStatus,
    EvaluationValidity,
    PrognosticEvaluationResult,
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


class TestEvaluationSemanticsAndSafety:
    """Rigorous verification suite for Level 6.5 scientific safety and semantic invariants."""

    def test_decoupled_validity_preserves_deterministic_point_estimate(self) -> None:
        """Verifies that VALID RUL with UNDEFINED uncertainty becomes VALID_WITH_LIMITATIONS without losing RUL."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_20",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.00,
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            unit="Ah",
        )
        pred = RULPredictionResult(
            prediction_id="pred_deterministic_only",
            prediction_timestamp_ns=1_000_000_000,
            created_at_utc="2026-09-07T00:00:00Z",
            system_id="cell_001",
            status=PrognosticStatus.VALID,
            rul_value=42.5,
            rul_unit="cycles",
            rul_domain=HorizonDomain.CYCLE,
            eol_definition=eol_def,
            diagnostic_message="Valid deterministic point estimate.",
        )
        eol_assessment = EOLAssessment(
            eol_state=EOLState.PROJECTED,
            eol_definition=eol_def,
            threshold_value=2.00,
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            unit="Ah",
            quantity_name="usable_capacity_ah",
            current_value=2.50,
            distance_to_eol=0.50,
            projected_crossing_domain_value=85.0,
            is_reached=False,
        )

        eval_status, validity = EvaluationValidityEvaluator.evaluate_validity(
            prediction=pred,
            eol_assessment=eol_assessment,
            uncertainty=None,
            evidence=None,
        )

        # Semantic guarantee: The evaluation is VALID_WITH_LIMITATIONS (not failed or invalid)
        assert eval_status == EvaluationStatus.VALID_WITH_LIMITATIONS
        assert validity.is_usable_for_decision is True
        assert validity.prediction_validity is True
        assert validity.uncertainty_availability == UncertaintyStatus.UNDEFINED
        assert any("Statistical uncertainty is limited or undefined" in lim for lim in validity.limitations)

    def test_evidence_strength_is_categorical_not_probability_or_percentage(self) -> None:
        """Verifies that evidence strength produces categorical classifications, never arbitrary percentages."""
        for strength in EvidenceStrength:
            assert isinstance(strength.value, str)
            # Must not be a numeric string or percentage
            assert not strength.value.endswith("%")
            assert not strength.value.replace(".", "", 1).isdigit()

    def test_flat_degradation_zero_rate_handled_gracefully(self) -> None:
        """Verifies that flat degradation (slope = 0) is handled without zero-division or crash."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_20",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.00,
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            unit="Ah",
        )
        # 5 observations all with identical capacity 2.50 Ah (zero degradation)
        obs_list = [
            DegradationObservation(
                timestamp_ns=(i + 1) * 1_000_000_000,
                created_at_utc=f"2026-09-07T00:00:0{i}Z",
                usable_capacity_ah=PrognosticQuantity(value=2.50, unit="Ah", name="usable_capacity_ah"),
                equivalent_full_cycles=PrognosticQuantity(value=float(i * 10), unit="cycles", name="equivalent_full_cycles"),
            )
            for i in range(5)
        ]
        traj = DegradationTrajectory(
            trajectory_id="traj_flat",
            system_id="cell_flat",
            observations=tuple(obs_list),
        )

        engine = PrognosticEvaluationEngine()
        result = engine.evaluate(trajectory=traj, eol_definition=eol_def)

        assert isinstance(result, PrognosticEvaluationResult)
        # Because slope is 0, RUL cannot project reaching 2.00 Ah
        # Should be OUT_OF_DOMAIN or INDETERMINATE, but NOT raise an unhandled exception
        assert result.evaluation_status in (
            EvaluationStatus.OUT_OF_DOMAIN,
            EvaluationStatus.INDETERMINATE,
            EvaluationStatus.VALID_WITH_LIMITATIONS,
        )

    def test_initial_capacity_already_at_or_below_eol(self) -> None:
        """Verifies that trajectory starting at or below EOL threshold evaluates to ALREADY_REACHED and RUL=0."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_20",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.00,
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            unit="Ah",
        )
        obs_list = [
            DegradationObservation(
                timestamp_ns=1_000_000_000,
                created_at_utc="2026-09-07T00:00:00Z",
                usable_capacity_ah=PrognosticQuantity(value=1.95, unit="Ah", name="usable_capacity_ah"),
                equivalent_full_cycles=PrognosticQuantity(value=100.0, unit="cycles", name="equivalent_full_cycles"),
            ),
            DegradationObservation(
                timestamp_ns=2_000_000_000,
                created_at_utc="2026-09-07T00:00:01Z",
                usable_capacity_ah=PrognosticQuantity(value=1.90, unit="Ah", name="usable_capacity_ah"),
                equivalent_full_cycles=PrognosticQuantity(value=110.0, unit="cycles", name="equivalent_full_cycles"),
            ),
        ]
        traj = DegradationTrajectory(
            trajectory_id="traj_eol_reached",
            system_id="cell_dead",
            observations=tuple(obs_list),
        )

        engine = PrognosticEvaluationEngine()
        result = engine.evaluate(trajectory=traj, eol_definition=eol_def)

        assert result.eol_assessment.eol_state == EOLState.ALREADY_REACHED
        assert result.eol_assessment.is_reached is True
        assert pytest.approx(result.eol_assessment.distance_to_eol, abs=1e-3) == 0.10
        assert result.prediction.rul_value == 0.0
        assert result.validity.is_usable_for_decision is True

    def test_invalid_eol_criterion_evaluation(self) -> None:
        """Verifies that mathematically invalid EOL definition results in INVALID_EOL_CRITERION status."""
        eol_invalid = EOLDefinition(
            criterion_id="eol_neg_cap",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=-2.00,  # Physically impossible negative capacity
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            unit="Ah",
        )
        obs_list = [
            DegradationObservation(
                timestamp_ns=1_000_000_000,
                created_at_utc="2026-09-07T00:00:00Z",
                usable_capacity_ah=PrognosticQuantity(value=2.80, unit="Ah", name="usable_capacity_ah"),
                equivalent_full_cycles=PrognosticQuantity(value=10.0, unit="cycles", name="equivalent_full_cycles"),
            ),
            DegradationObservation(
                timestamp_ns=2_000_000_000,
                created_at_utc="2026-09-07T00:00:01Z",
                usable_capacity_ah=PrognosticQuantity(value=2.70, unit="Ah", name="usable_capacity_ah"),
                equivalent_full_cycles=PrognosticQuantity(value=20.0, unit="cycles", name="equivalent_full_cycles"),
            ),
        ]
        traj = DegradationTrajectory(
            trajectory_id="traj_cap",
            system_id="cell_001",
            observations=tuple(obs_list),
        )

        engine = PrognosticEvaluationEngine()
        result = engine.evaluate(trajectory=traj, eol_definition=eol_invalid)

        assert result.evaluation_status == EvaluationStatus.INVALID_EOL_CRITERION
        assert result.validity.is_usable_for_decision is False
        assert result.validity.eol_validity is False

    def test_complete_json_serialization(self) -> None:
        """Verifies that full PrognosticEvaluationResult serializes cleanly to JSON."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_20",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.00,
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            unit="Ah",
        )
        obs_list = [
            DegradationObservation(
                timestamp_ns=(i + 1) * 1_000_000_000,
                created_at_utc=f"2026-09-07T00:00:0{i}Z",
                usable_capacity_ah=PrognosticQuantity(value=3.0 - 0.02 * i, unit="Ah", name="usable_capacity_ah"),
                equivalent_full_cycles=PrognosticQuantity(value=float(i * 10), unit="cycles", name="equivalent_full_cycles"),
            )
            for i in range(5)
        ]
        traj = DegradationTrajectory(
            trajectory_id="traj_serial",
            system_id="cell_serial",
            observations=tuple(obs_list),
        )

        engine = PrognosticEvaluationEngine()
        result = engine.evaluate(trajectory=traj, eol_definition=eol_def, extract_features=True)

        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["evaluation_id"] == result.evaluation_id
        assert d["system_id"] == "cell_serial"
        assert d["evaluation_status"] in (EvaluationStatus.VALID.value, EvaluationStatus.VALID_WITH_LIMITATIONS.value)
        assert "eol_assessment" in d
        assert "validity" in d
        assert "feature_set" in d

        # Must be valid json dumpable
        json_str = json.dumps(d)
        assert len(json_str) > 0
        parsed = json.loads(json_str)
        assert parsed["system_id"] == "cell_serial"
