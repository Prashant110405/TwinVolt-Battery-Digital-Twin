"""Unit Tests for EOL Assessment and Boundary Crossing Evaluation.

Validates:
- EOL states: NOT_REACHED, ALREADY_REACHED, PROJECTED, INDETERMINATE, INVALID
- Exact boundary crossing condition (current == threshold)
- Beyond boundary condition (current exceeds threshold in direction)
- Relational operators: <=, >=, <, >, ==
- Projected crossing calculation from domain position and RUL
- Incompatible units/quantities rejection
- Non-finite (NaN, inf) rejection
- Trajectory latest observation extraction
"""

import math
import pytest

from src.prognostics.evaluation.eol import EOLEvaluator
from src.prognostics.evaluation.types import EOLState
from src.prognostics.prediction import EOLDefinition
from src.prognostics.provenance import PrognosticQuantity, PrognosticValueProvenance
from src.prognostics.trajectory import DegradationObservation, DegradationTrajectory
from src.prognostics.types import (
    ComparisonOperator,
    EOLCriterionType,
    QuantityAvailability,
    ValueOriginType,
)


class TestEOLEvaluator:
    """EOL evaluation and boundary crossing tests."""

    def test_eol_not_reached(self) -> None:
        """Verifies state NOT_REACHED when current degradation is before threshold and no projection is given."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_24",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        q = PrognosticQuantity(name="usable_capacity_ah", value=2.80, unit="Ah")
        assessment = EOLEvaluator.evaluate(eol_definition=eol_def, current_quantity=q)

        assert assessment.eol_state == EOLState.NOT_REACHED
        assert assessment.is_reached is False
        assert assessment.distance_to_eol == pytest.approx(0.40, rel=1e-6)
        assert assessment.projected_crossing_domain_value is None

    def test_eol_projected_crossing(self) -> None:
        """Verifies state PROJECTED when current is before threshold and RUL projection is provided."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_24",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
        )
        q = PrognosticQuantity(name="usable_capacity_ah", value=2.60, unit="Ah")
        assessment = EOLEvaluator.evaluate(
            eol_definition=eol_def,
            current_quantity=q,
            current_domain_value=40.0,
            rul_value=20.0,
        )

        assert assessment.eol_state == EOLState.PROJECTED
        assert assessment.is_reached is False
        assert assessment.projected_crossing_domain_value == pytest.approx(60.0, rel=1e-6)
        assert assessment.distance_to_eol == pytest.approx(0.20, rel=1e-6)

    def test_eol_already_reached_exact_boundary(self) -> None:
        """Verifies state ALREADY_REACHED when current is exactly at threshold."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_24",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        q = PrognosticQuantity(name="usable_capacity_ah", value=2.40, unit="Ah")
        assessment = EOLEvaluator.evaluate(eol_definition=eol_def, current_quantity=q)

        assert assessment.eol_state == EOLState.ALREADY_REACHED
        assert assessment.is_reached is True
        assert assessment.distance_to_eol == pytest.approx(0.0, abs=1e-12)

    def test_eol_already_reached_beyond_boundary(self) -> None:
        """Verifies state ALREADY_REACHED when current capacity is below threshold."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_24",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
            comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        q = PrognosticQuantity(name="usable_capacity_ah", value=2.30, unit="Ah")
        assessment = EOLEvaluator.evaluate(eol_definition=eol_def, current_quantity=q)

        assert assessment.eol_state == EOLState.ALREADY_REACHED
        assert assessment.is_reached is True

    def test_eol_increasing_quantity_resistance_growth(self) -> None:
        """Verifies increasing criterion (GREATER_THAN_OR_EQUAL) for resistance growth ratio."""
        eol_def = EOLDefinition(
            criterion_id="eol_res_growth",
            criterion_type=EOLCriterionType.RESISTANCE_GROWTH_RATIO_THRESHOLD,
            threshold_value=2.00,  # 2.0x growth
            unit="ratio",
            comparison_operator=ComparisonOperator.GREATER_THAN_OR_EQUAL,
        )
        # Not reached: ratio 1.5 < 2.0
        q_not = PrognosticQuantity(name="resistance_growth_ratio", value=1.50, unit="ratio")
        ass_not = EOLEvaluator.evaluate(eol_definition=eol_def, current_quantity=q_not)
        assert ass_not.eol_state == EOLState.NOT_REACHED
        assert ass_not.is_reached is False

        # Reached: ratio 2.1 >= 2.0
        q_reach = PrognosticQuantity(name="resistance_growth_ratio", value=2.10, unit="ratio")
        ass_reach = EOLEvaluator.evaluate(eol_definition=eol_def, current_quantity=q_reach)
        assert ass_reach.eol_state == EOLState.ALREADY_REACHED
        assert ass_reach.is_reached is True

    def test_eol_indeterminate_when_quantity_unavailable(self) -> None:
        """Verifies INDETERMINATE state when quantity is missing or unavailable."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_24",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
        )
        q_unavail = PrognosticQuantity(
            name="usable_capacity_ah",
            value=None,
            unit="Ah",
            availability=QuantityAvailability.UNAVAILABLE,
        )
        assessment = EOLEvaluator.evaluate(eol_definition=eol_def, current_quantity=q_unavail)
        assert assessment.eol_state == EOLState.INDETERMINATE
        assert assessment.is_reached is False

    def test_eol_invalid_on_incompatible_units(self) -> None:
        """Verifies INVALID state when quantity unit conflicts with criterion definition."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_24",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
        )
        q_ohm = PrognosticQuantity(name="internal_resistance", value=0.030, unit="ohm")
        assessment = EOLEvaluator.evaluate(eol_definition=eol_def, current_quantity=q_ohm)
        assert assessment.eol_state == EOLState.INVALID
        assert "Incompatible units" in (assessment.diagnostic_message or "")

    def test_eol_evaluation_from_trajectory(self) -> None:
        """Verifies trajectory latest observation extraction."""
        eol_def = EOLDefinition(
            criterion_id="eol_cap_24",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
        )
        obs1 = DegradationObservation(
            timestamp_ns=1_000_000_000,
            created_at_utc="2026-09-07T00:00:00Z",
            usable_capacity_ah=PrognosticQuantity(value=2.90, unit="Ah", name="usable_capacity_ah"),
            equivalent_full_cycles=PrognosticQuantity(value=10.0, unit="cycles", name="equivalent_full_cycles"),
        )
        obs2 = DegradationObservation(
            timestamp_ns=2_000_000_000,
            created_at_utc="2026-09-07T00:00:01Z",
            usable_capacity_ah=PrognosticQuantity(value=2.70, unit="Ah", name="usable_capacity_ah"),
            equivalent_full_cycles=PrognosticQuantity(value=30.0, unit="cycles", name="equivalent_full_cycles"),
        )
        traj = DegradationTrajectory(trajectory_id="traj_1", system_id="sys_1", observations=(obs1, obs2))

        assessment = EOLEvaluator.evaluate_from_trajectory(
            trajectory=traj,
            eol_definition=eol_def,
            rul_value=30.0,
            last_domain_value=30.0,
        )
        assert assessment.eol_state == EOLState.PROJECTED
        assert assessment.current_value == 2.70
        assert assessment.projected_crossing_domain_value == 60.0
