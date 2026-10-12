"""Unit Tests for Evaluation Types, Enums, and Value Objects.

Validates:
- EvaluationStatus and EOLState enumerations
- EOLAssessment immutability, validation, and serialization
- EvaluationValidity immutability, validation, and serialization
- PrognosticEvaluationResult container, validation, and serialization
"""

import pytest

from src.prognostics.evaluation.types import (
    EOLAssessment,
    EOLState,
    EvaluationStatus,
    EvaluationValidity,
    PrognosticEvaluationResult,
)
from src.prognostics.prediction import EOLDefinition
from src.prognostics.types import (
    ComparisonOperator,
    EOLCriterionType,
    PrognosticStatus,
)
from src.prognostics.uncertainty.types import EvidenceStrength, UncertaintyStatus


class TestEvaluationTypes:
    """Contract and immutability tests for Level 6.5 types."""

    def test_evaluation_status_enum_distinctness(self) -> None:
        """Verifies EvaluationStatus members are distinct."""
        statuses = {
            EvaluationStatus.VALID,
            EvaluationStatus.VALID_WITH_LIMITATIONS,
            EvaluationStatus.INSUFFICIENT_DATA,
            EvaluationStatus.INSUFFICIENT_HISTORY,
            EvaluationStatus.DATA_QUALITY_FAILED,
            EvaluationStatus.OUT_OF_DOMAIN,
            EvaluationStatus.INVALID_EOL_CRITERION,
            EvaluationStatus.INDETERMINATE,
        }
        assert len(statuses) == 8
        assert EvaluationStatus.VALID.value == "VALID"
        assert EvaluationStatus.VALID_WITH_LIMITATIONS.value == "VALID_WITH_LIMITATIONS"

    def test_eol_state_enum_distinctness(self) -> None:
        """Verifies EOLState members are distinct."""
        states = {
            EOLState.NOT_REACHED,
            EOLState.ALREADY_REACHED,
            EOLState.PROJECTED,
            EOLState.INDETERMINATE,
            EOLState.INVALID,
        }
        assert len(states) == 5

    def test_eol_assessment_valid_instantiation_and_serialization(self) -> None:
        """Verifies EOLAssessment properties and dictionary serialization."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_24",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        assessment = EOLAssessment(
            eol_state=EOLState.PROJECTED,
            eol_definition=eol_def,
            threshold_value=2.40,
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            unit="Ah",
            quantity_name="usable_capacity_ah",
            current_value=2.60,
            distance_to_eol=0.20,
            projected_crossing_domain_value=60.0,
            is_reached=False,
            diagnostic_message="Projected crossing at 60.0 cycles.",
        )
        assert assessment.eol_state == EOLState.PROJECTED
        assert assessment.current_value == 2.60
        assert assessment.distance_to_eol == 0.20
        assert assessment.is_reached is False

        d = assessment.to_dict()
        assert d["eol_state"] == "PROJECTED"
        assert d["current_value"] == 2.60
        assert d["distance_to_eol"] == 0.20
        assert d["is_reached"] is False
        assert d["eol_definition"]["criterion_id"] == "eol_cap_24"

    def test_eol_assessment_invalid_inputs(self) -> None:
        """Verifies type and finite float enforcement on EOLAssessment."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_24",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
        )
        with pytest.raises(TypeError):
            EOLAssessment(
                eol_state="INVALID_STRING",  # type: ignore
                eol_definition=eol_def,
                threshold_value=2.40,
                comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
                unit="Ah",
                quantity_name="cap",
            )

        with pytest.raises(ValueError, match="finite float"):
            EOLAssessment(
                eol_state=EOLState.PROJECTED,
                eol_definition=eol_def,
                threshold_value=float("nan"),
                comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
                unit="Ah",
                quantity_name="cap",
            )

    def test_evaluation_validity_instantiation_and_serialization(self) -> None:
        """Verifies EvaluationValidity container and serialization."""
        validity = EvaluationValidity(
            data_quality=PrognosticStatus.VALID,
            history_sufficiency=PrognosticStatus.VALID,
            domain_validity=PrognosticStatus.VALID,
            eol_validity=True,
            prediction_validity=True,
            uncertainty_availability=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            evidence_strength=EvidenceStrength.STRONG,
            limitations=("Minor extrapolation ratio 1.2x.",),
            diagnostic_notes=("Trend is monotonic.",),
            is_usable_for_decision=True,
        )
        assert validity.data_quality == PrognosticStatus.VALID
        assert validity.is_usable_for_decision is True
        assert len(validity.limitations) == 1

        d = validity.to_dict()
        assert d["data_quality"] == "VALID"
        assert d["evidence_strength"] == "STRONG"
        assert d["is_usable_for_decision"] is True
        assert d["limitations"] == ["Minor extrapolation ratio 1.2x."]

    def test_prognostic_evaluation_result_properties(self) -> None:
        """Verifies top-level PrognosticEvaluationResult container."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_24",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
        )
        eol_ass = EOLAssessment(
            eol_state=EOLState.PROJECTED,
            eol_definition=eol_def,
            threshold_value=2.40,
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
            unit="Ah",
            quantity_name="usable_capacity_ah",
            current_value=2.60,
        )
        validity = EvaluationValidity(
            data_quality=PrognosticStatus.VALID,
            prediction_validity=True,
            is_usable_for_decision=True,
        )
        res = PrognosticEvaluationResult(
            evaluation_id="eval_001",
            system_id="cell_01",
            evaluation_timestamp_ns=1_000_000_000,
            created_at_utc="2026-09-07T00:00:00Z",
            evaluation_status=EvaluationStatus.VALID,
            eol_assessment=eol_ass,
            validity=validity,
            diagnostics=("Evaluation successful.",),
        )
        assert res.evaluation_id == "eval_001"
        assert res.is_valid is True
        assert res.evaluation_status == EvaluationStatus.VALID

        d = res.to_dict()
        assert d["evaluation_id"] == "eval_001"
        assert d["evaluation_status"] == "VALID"
        assert d["is_valid"] is True
        assert d["eol_assessment"]["eol_state"] == "PROJECTED"
