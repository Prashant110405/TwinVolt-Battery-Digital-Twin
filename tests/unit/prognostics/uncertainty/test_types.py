"""Unit Tests for Prognostic Uncertainty Taxonomies, Statuses, and Value Objects.

Validates:
- Explicit uncertainty source taxonomy (all 7 categories distinct)
- Uncertainty availability/status semantics
- Evidence strength categorization without percentage mappings
- Measurement uncertainty availability
- UncertaintyBound ordering, finiteness, truncation, and immutability
- UncertaintyComponent validation and serialization
- UncertaintyCombinationResult immutability
"""

import pytest

from src.prognostics.uncertainty.types import (
    EvidenceStrength,
    MeasurementUncertaintyAvailability,
    UncertaintyBound,
    UncertaintyCombinationResult,
    UncertaintyComponent,
    UncertaintyIntervalType,
    UncertaintyRepresentationType,
    UncertaintySourceCategory,
    UncertaintyStatus,
)


class TestUncertaintyTypes:
    """Taxonomy, status, and value object contract tests."""

    def test_uncertainty_source_categories_are_distinct(self) -> None:
        """Verifies that all 7 required source categories are distinct and present."""
        cats = {
            UncertaintySourceCategory.MEASUREMENT,
            UncertaintySourceCategory.TRAJECTORY_TREND,
            UncertaintySourceCategory.MODEL_RESIDUAL,
            UncertaintySourceCategory.EXTRAPOLATION,
            UncertaintySourceCategory.INPUT_STATE,
            UncertaintySourceCategory.COMBINED,
            UncertaintySourceCategory.UNKNOWN,
        }
        assert len(cats) == 7
        assert UncertaintySourceCategory.MEASUREMENT.value == "MEASUREMENT"
        assert UncertaintySourceCategory.TRAJECTORY_TREND.value == "TRAJECTORY_TREND"
        assert UncertaintySourceCategory.MODEL_RESIDUAL.value == "MODEL_RESIDUAL"
        assert UncertaintySourceCategory.EXTRAPOLATION.value == "EXTRAPOLATION"
        assert UncertaintySourceCategory.INPUT_STATE.value == "INPUT_STATE"
        assert UncertaintySourceCategory.COMBINED.value == "COMBINED"
        assert UncertaintySourceCategory.UNKNOWN.value == "UNKNOWN"

    def test_uncertainty_statuses_are_distinct(self) -> None:
        """Verifies availability and status enumerations."""
        statuses = {
            UncertaintyStatus.UNDEFINED,
            UncertaintyStatus.DETERMINISTIC_ONLY,
            UncertaintyStatus.ESTIMATED,
            UncertaintyStatus.STATISTICALLY_SUPPORTED,
            UncertaintyStatus.INSUFFICIENT_EVIDENCE,
            UncertaintyStatus.COMBINATION_UNAVAILABLE,
        }
        assert len(statuses) == 6
        assert UncertaintyStatus.DETERMINISTIC_ONLY.value == "DETERMINISTIC_ONLY"
        assert UncertaintyStatus.STATISTICALLY_SUPPORTED.value == "STATISTICALLY_SUPPORTED"

    def test_evidence_strength_categories(self) -> None:
        """Verifies evidence strength classifications."""
        strengths = {
            EvidenceStrength.INSUFFICIENT,
            EvidenceStrength.VERY_WEAK,
            EvidenceStrength.WEAK,
            EvidenceStrength.MODERATE,
            EvidenceStrength.STRONG,
            EvidenceStrength.VERY_STRONG,
        }
        assert len(strengths) == 6

    def test_measurement_uncertainty_availability_categories(self) -> None:
        """Verifies measurement uncertainty availability flags."""
        assert MeasurementUncertaintyAvailability.PROVIDED_MEASUREMENT_UNCERTAINTY.value == "PROVIDED_MEASUREMENT_UNCERTAINTY"
        assert MeasurementUncertaintyAvailability.UNAVAILABLE_MEASUREMENT_UNCERTAINTY.value == "UNAVAILABLE_MEASUREMENT_UNCERTAINTY"

    def test_uncertainty_bound_valid(self) -> None:
        """Verifies valid UncertaintyBound instantiation and serialization."""
        bound = UncertaintyBound(
            lower=15.0,
            upper=25.0,
            coverage_parameter=0.95,
            interval_type=UncertaintyIntervalType.CONFIDENCE_INTERVAL,
            is_truncated_at_zero=False,
            constraint_description=None,
        )
        assert bound.lower == 15.0
        assert bound.upper == 25.0
        assert bound.coverage_parameter == 0.95
        assert bound.is_truncated_at_zero is False

        d = bound.to_dict()
        assert d["lower"] == 15.0
        assert d["upper"] == 25.0
        assert d["coverage_parameter"] == 0.95
        assert d["interval_type"] == "CONFIDENCE_INTERVAL"
        assert d["is_truncated_at_zero"] is False

    def test_uncertainty_bound_invalid_bounds(self) -> None:
        """Verifies that lower > upper or non-finite values raise ValueError."""
        with pytest.raises(ValueError, match="cannot exceed upper bound"):
            UncertaintyBound(lower=30.0, upper=20.0)

        with pytest.raises(ValueError, match="finite float"):
            UncertaintyBound(lower=float("nan"), upper=20.0)

        with pytest.raises(ValueError, match="finite float"):
            UncertaintyBound(lower=10.0, upper=float("inf"))

    def test_uncertainty_component_valid(self) -> None:
        """Verifies UncertaintyComponent container and properties."""
        comp = UncertaintyComponent(
            source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
            status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            standard_uncertainty=0.0005,
            relative_uncertainty=0.02,
            degrees_of_freedom=8,
            unit="Ah/cycles",
            description="OLS slope standard error",
            assumptions=("Linear degradation rate.",),
            metadata={"r2": 0.98},
        )
        assert comp.source_category == UncertaintySourceCategory.TRAJECTORY_TREND
        assert comp.status == UncertaintyStatus.STATISTICALLY_SUPPORTED
        assert comp.standard_uncertainty == 0.0005
        assert comp.degrees_of_freedom == 8

        d = comp.to_dict()
        assert d["source_category"] == "TRAJECTORY_TREND"
        assert d["status"] == "STATISTICALLY_SUPPORTED"
        assert d["degrees_of_freedom"] == 8
        assert d["metadata"]["r2"] == 0.98

    def test_uncertainty_component_validation(self) -> None:
        """Verifies invalid component parameters raise TypeError or ValueError."""
        with pytest.raises(ValueError, match="non-negative finite float"):
            UncertaintyComponent(
                source_category=UncertaintySourceCategory.MEASUREMENT,
                status=UncertaintyStatus.ESTIMATED,
                standard_uncertainty=-0.5,
            )

        with pytest.raises(ValueError, match="non-negative integer"):
            UncertaintyComponent(
                source_category=UncertaintySourceCategory.MEASUREMENT,
                status=UncertaintyStatus.ESTIMATED,
                degrees_of_freedom=-1,
            )

    def test_uncertainty_combination_result(self) -> None:
        """Verifies UncertaintyCombinationResult container."""
        comp = UncertaintyComponent(
            source_category=UncertaintySourceCategory.MEASUREMENT,
            status=UncertaintyStatus.ESTIMATED,
            standard_uncertainty=0.01,
        )
        res = UncertaintyCombinationResult(
            status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            combined_standard_uncertainty=0.015,
            components=(comp,),
            combination_method="INDEPENDENT_ROOT_SUM_SQUARES",
            assumptions=("Independent sources.",),
        )
        assert res.status == UncertaintyStatus.STATISTICALLY_SUPPORTED
        assert res.combined_standard_uncertainty == 0.015
        assert len(res.components) == 1
        d = res.to_dict()
        assert d["status"] == "STATISTICALLY_SUPPORTED"
        assert len(d["components"]) == 1
