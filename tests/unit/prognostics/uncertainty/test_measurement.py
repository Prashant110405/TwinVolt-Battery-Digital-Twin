"""Unit Tests for Measurement Uncertainty Evaluation.

Validates:
- Explicit extraction from PrognosticQuantity and PrognosticValueProvenance
- Unavailable measurement uncertainty handling without fabrication
- Absolute and relative uncertainty fraction conversions
- Expanded uncertainty with coverage factor k
- Degrees of freedom tracking
- Multi-sample trajectory observation evaluation without false independence assumptions
"""

import pytest

from src.prognostics.provenance import PrognosticQuantity, PrognosticValueProvenance
from src.prognostics.trajectory import DegradationObservation, DegradationTrajectory
from src.prognostics.types import QuantityAvailability, ValueOriginType
from src.prognostics.uncertainty.measurement import (
    MeasurementUncertaintyEvaluator,
)
from src.prognostics.uncertainty.types import (
    MeasurementUncertaintyAvailability,
    UncertaintyRepresentationType,
    UncertaintySourceCategory,
    UncertaintyStatus,
)


class TestMeasurementUncertaintyEvaluator:
    """Measurement uncertainty evaluation tests."""

    def test_quantity_with_no_provenance(self) -> None:
        """Verifies that a quantity with no provenance returns UNAVAILABLE without fabricating numbers."""
        q = PrognosticQuantity(
            value=2.85,
            unit="Ah",
            availability=QuantityAvailability.AVAILABLE,
            provenance=None,
            name="usable_capacity",
        )
        res = MeasurementUncertaintyEvaluator.evaluate_quantity(q)
        assert res.availability == MeasurementUncertaintyAvailability.UNAVAILABLE_MEASUREMENT_UNCERTAINTY
        assert res.status == UncertaintyStatus.UNDEFINED
        assert res.standard_uncertainty is None
        assert res.component is not None
        assert res.component.source_category == UncertaintySourceCategory.MEASUREMENT
        assert res.component.status == UncertaintyStatus.UNDEFINED

    def test_quantity_with_explicit_standard_uncertainty(self) -> None:
        """Verifies evaluation of explicitly provided standard uncertainty."""
        prov = PrognosticValueProvenance(
            origin_type=ValueOriginType.MEASURED,
            source_identifier="laboratory_cycler_ch1",
            measurement_uncertainty=0.005,
            quality_rating="HIGH_PRECISION",
        )
        q = PrognosticQuantity(
            value=3.0,
            unit="Ah",
            availability=QuantityAvailability.AVAILABLE,
            provenance=prov,
            name="usable_capacity",
        )
        res = MeasurementUncertaintyEvaluator.evaluate_quantity(q)
        assert res.availability == MeasurementUncertaintyAvailability.PROVIDED_MEASUREMENT_UNCERTAINTY
        assert res.status == UncertaintyStatus.ESTIMATED
        assert res.standard_uncertainty == 0.005
        assert res.relative_uncertainty == pytest.approx(0.005 / 3.0, rel=1e-6)
        assert res.component is not None
        assert res.component.standard_uncertainty == 0.005

    def test_provenance_with_relative_uncertainty_metadata(self) -> None:
        """Verifies extraction and conversion of relative uncertainty fraction."""
        prov = PrognosticValueProvenance(
            origin_type=ValueOriginType.MEASURED,
            metadata={"relative_uncertainty_fraction": 0.01},  # 1% relative
        )
        res = MeasurementUncertaintyEvaluator.evaluate_provenance(
            provenance=prov,
            nominal_value=2.50,
            unit="Ah",
            quantity_name="capacity",
        )
        assert res.availability == MeasurementUncertaintyAvailability.PROVIDED_MEASUREMENT_UNCERTAINTY
        assert res.relative_uncertainty == 0.01
        assert res.standard_uncertainty == pytest.approx(0.025, rel=1e-6)
        assert res.representation_type == UncertaintyRepresentationType.RELATIVE_FRACTION

    def test_provenance_with_coverage_factor_and_degrees_of_freedom(self) -> None:
        """Verifies expanded uncertainty and STATISTICALLY_SUPPORTED status when df is provided."""
        prov = PrognosticValueProvenance(
            origin_type=ValueOriginType.MEASURED,
            measurement_uncertainty=0.004,
            metadata={"coverage_factor": 2.0, "degrees_of_freedom": 10},
        )
        res = MeasurementUncertaintyEvaluator.evaluate_provenance(
            provenance=prov,
            nominal_value=2.00,
            unit="Ah",
            quantity_name="capacity",
        )
        assert res.status == UncertaintyStatus.STATISTICALLY_SUPPORTED
        assert res.standard_uncertainty == 0.004
        assert res.coverage_factor == 2.0
        assert res.expanded_uncertainty == pytest.approx(0.008, rel=1e-6)
        assert res.degrees_of_freedom == 10

    def test_trajectory_observations_preserves_individual_evaluations(self) -> None:
        """Verifies that trajectory evaluation evaluates each sample and does not assume time independence."""
        prov1 = PrognosticValueProvenance(origin_type=ValueOriginType.MEASURED, measurement_uncertainty=0.01)
        prov2 = PrognosticValueProvenance(origin_type=ValueOriginType.MEASURED, measurement_uncertainty=0.02)

        obs1 = DegradationObservation(
            timestamp_ns=1_000_000_000,
            created_at_utc="2026-09-06T00:00:00Z",
            usable_capacity_ah=PrognosticQuantity(
                name="usable_capacity_ah",
                value=2.90,
                unit="Ah",
                provenance=prov1,
            ),
        )
        obs2 = DegradationObservation(
            timestamp_ns=2_000_000_000,
            created_at_utc="2026-09-06T00:00:01Z",
            usable_capacity_ah=PrognosticQuantity(
                name="usable_capacity_ah",
                value=2.80,
                unit="Ah",
                provenance=prov2,
            ),
        )
        traj = DegradationTrajectory(
            trajectory_id="traj_1",
            system_id="sys_1",
            observations=(obs1, obs2),
        )


        evals = MeasurementUncertaintyEvaluator.evaluate_trajectory_observations(
            trajectory=traj,
            field_name="usable_capacity_ah",
        )
        assert len(evals) == 2
        assert evals[0].standard_uncertainty == 0.01
        assert evals[1].standard_uncertainty == 0.02
        assert evals[0].availability == MeasurementUncertaintyAvailability.PROVIDED_MEASUREMENT_UNCERTAINTY
        assert evals[1].availability == MeasurementUncertaintyAvailability.PROVIDED_MEASUREMENT_UNCERTAINTY
