"""Unit Tests for Analytical RUL Uncertainty Propagation and Interval Evaluation.

Validates:
- First-order analytical Taylor sensitivity derivatives (df/dr = -RUL/r, df/dy = 1/r)
- Propagation of degradation rate uncertainty: sigma_RUL = |RUL/r| * sigma_r
- Propagation of state uncertainty: sigma_RUL = (1/r) * sigma_y
- Combined independent uncertainty via root-sum-of-squares (RSS)
- Status COMBINATION_UNAVAILABLE when independence is not assumed and covariance is uncharacterized
- Flat/zero rate handling returning INSUFFICIENT_EVIDENCE
- Confidence interval construction with Student-t critical values at configured confidence levels
- Non-negative RUL boundary handling with zero-truncation tracking and constraint message
- Deterministic-only state preservation when no input standard uncertainties exist
"""

import pytest

from src.prognostics.uncertainty.propagation import (
    RULPropagationResult,
    RULUncertaintyPropagator,
)
from src.prognostics.uncertainty.types import (
    UncertaintyComponent,
    UncertaintyIntervalType,
    UncertaintySourceCategory,
    UncertaintyStatus,
)


class TestRULUncertaintyPropagator:
    """RUL uncertainty propagation tests."""

    def test_propagation_rate_uncertainty_only(self) -> None:
        """Verifies sigma_RUL = (RUL / rate) * sigma_r."""
        # RUL = 100 cycles, rate = 0.001 Ah/cycle, sigma_r = 0.0001 Ah/cycle
        # sigma_RUL = (100 / 0.001) * 0.0001 = 100,000 * 0.0001 = 10 cycles
        comp_r = UncertaintyComponent(
            source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
            status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            standard_uncertainty=0.0001,
            degrees_of_freedom=10,
            unit="Ah/cycles",
        )
        res = RULUncertaintyPropagator.propagate(
            rul_value=100.0,
            degradation_rate=0.001,
            rate_uncertainty_component=comp_r,
            domain_unit="cycles",
        )
        assert res.status == UncertaintyStatus.STATISTICALLY_SUPPORTED
        assert res.sensitivity_to_rate == pytest.approx(-100.0 / 0.001, rel=1e-6)
        assert res.propagated_standard_uncertainty == pytest.approx(10.0, rel=1e-6)

    def test_propagation_state_uncertainty_only(self) -> None:
        """Verifies sigma_RUL = (1 / rate) * sigma_y."""
        # RUL = 50 cycles, rate = 0.002 Ah/cycle, sigma_y = 0.01 Ah
        # sigma_RUL = (1 / 0.002) * 0.01 = 500 * 0.01 = 5.0 cycles
        comp_y = UncertaintyComponent(
            source_category=UncertaintySourceCategory.MEASUREMENT,
            status=UncertaintyStatus.ESTIMATED,
            standard_uncertainty=0.01,
            unit="Ah",
        )
        res = RULUncertaintyPropagator.propagate(
            rul_value=50.0,
            degradation_rate=0.002,
            state_uncertainty_component=comp_y,
            domain_unit="cycles",
        )
        assert res.propagated_standard_uncertainty == pytest.approx(5.0, rel=1e-6)

    def test_combined_independent_uncertainty(self) -> None:
        """Verifies RSS combination: sigma_total = sqrt(sigma_r^2 + sigma_y^2)."""
        # sigma_r_contrib = 10.0, sigma_y_contrib = 5.0 -> sqrt(100 + 25) = sqrt(125) = 11.1803...
        comp_r = UncertaintyComponent(
            source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
            status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            standard_uncertainty=0.0001,
            degrees_of_freedom=8,
            unit="Ah/cycles",
        )
        comp_y = UncertaintyComponent(
            source_category=UncertaintySourceCategory.MEASUREMENT,
            status=UncertaintyStatus.ESTIMATED,
            standard_uncertainty=0.01,
            unit="Ah",
        )
        res = RULUncertaintyPropagator.propagate(
            rul_value=100.0,
            degradation_rate=0.001,
            rate_uncertainty_component=comp_r,
            state_uncertainty_component=comp_y,
            assume_independent=True,
            domain_unit="cycles",
        )
        # rate: (100 / 0.001) * 0.0001 = 10.0
        # state: (1 / 0.001) * 0.01 = 10.0
        # total = sqrt(10^2 + 10^2) = sqrt(200) = 14.1421...
        expected = pytest.approx(14.1421356, rel=1e-5)
        assert res.propagated_standard_uncertainty == expected

    def test_covariance_unavailable_when_not_independent(self) -> None:
        """Verifies COMBINATION_UNAVAILABLE when multiple uncertainties exist but independence is not assumed."""
        comp_r = UncertaintyComponent(
            source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
            status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            standard_uncertainty=0.0001,
        )
        comp_y = UncertaintyComponent(
            source_category=UncertaintySourceCategory.MEASUREMENT,
            status=UncertaintyStatus.ESTIMATED,
            standard_uncertainty=0.01,
        )
        res = RULUncertaintyPropagator.propagate(
            rul_value=100.0,
            degradation_rate=0.001,
            rate_uncertainty_component=comp_r,
            state_uncertainty_component=comp_y,
            assume_independent=False,
        )
        assert res.status == UncertaintyStatus.COMBINATION_UNAVAILABLE
        assert res.propagated_standard_uncertainty is None

    def test_confidence_interval_with_student_t(self) -> None:
        """Verifies Student-t confidence interval generation at 95% confidence."""
        # df = 4, t_crit(0.95, 4) = 2.7764
        # sigma = 10.0 -> margin = 27.764 -> bounds = [100 - 27.764, 100 + 27.764] = [72.236, 127.764]
        comp_r = UncertaintyComponent(
            source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
            status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            standard_uncertainty=0.0001,
            degrees_of_freedom=4,
            unit="Ah/cycles",
        )
        res = RULUncertaintyPropagator.propagate(
            rul_value=100.0,
            degradation_rate=0.001,
            rate_uncertainty_component=comp_r,
            confidence_level=0.95,
            domain_unit="cycles",
        )
        assert res.bounds is not None
        assert res.bounds.interval_type == UncertaintyIntervalType.CONFIDENCE_INTERVAL
        assert res.bounds.lower == pytest.approx(100.0 - 2.7764 * 10.0, rel=1e-3)
        assert res.bounds.upper == pytest.approx(100.0 + 2.7764 * 10.0, rel=1e-3)
        assert res.bounds.is_truncated_at_zero is False

    def test_non_negative_rul_boundary_truncation(self) -> None:
        """Verifies lower bound is truncated at zero with constraint tracking when margin exceeds RUL."""
        # RUL = 5 cycles, sigma = 10 cycles -> raw lower = 5 - 20 = -15 -> truncated to 0
        comp_r = UncertaintyComponent(
            source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
            status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            standard_uncertainty=0.002,
            degrees_of_freedom=10,
            unit="Ah/cycles",
        )
        res = RULUncertaintyPropagator.propagate(
            rul_value=5.0,
            degradation_rate=0.001,
            rate_uncertainty_component=comp_r,
            confidence_level=0.95,
            domain_unit="cycles",
        )
        assert res.bounds is not None
        assert res.bounds.lower == 0.0
        assert res.bounds.is_truncated_at_zero is True
        assert res.bounds.constraint_description is not None
        assert res.bounds.lower <= res.bounds.upper

    def test_deterministic_only_when_no_uncertainty_supplied(self) -> None:
        """Verifies DETERMINISTIC_ONLY when inputs have no quantified standard uncertainty."""
        res = RULUncertaintyPropagator.propagate(
            rul_value=100.0,
            degradation_rate=0.001,
            rate_uncertainty_component=None,
            state_uncertainty_component=None,
        )
        assert res.status == UncertaintyStatus.DETERMINISTIC_ONLY
        assert res.propagated_standard_uncertainty is None
        assert res.bounds is None

    def test_zero_negative_and_near_zero_degradation_rate(self) -> None:
        """Check 1.2, 1.3, 1.4: Verifies rate == 0, rate < 0, and rate near zero return INSUFFICIENT_EVIDENCE."""
        comp_r = UncertaintyComponent(
            source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
            status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            standard_uncertainty=0.0001,
            degrees_of_freedom=5,
        )
        # rate == 0.0
        res_zero = RULUncertaintyPropagator.propagate(
            rul_value=100.0,
            degradation_rate=0.0,
            rate_uncertainty_component=comp_r,
        )
        assert res_zero.status == UncertaintyStatus.INSUFFICIENT_EVIDENCE
        assert res_zero.sensitivity_to_rate == 0.0
        assert res_zero.sensitivity_to_state == 0.0
        assert res_zero.propagated_standard_uncertainty is None

        # rate < 0.0
        res_neg = RULUncertaintyPropagator.propagate(
            rul_value=100.0,
            degradation_rate=-0.005,
            rate_uncertainty_component=comp_r,
        )
        assert res_neg.status == UncertaintyStatus.INSUFFICIENT_EVIDENCE

        # rate extremely close to zero (e.g. 1e-16)
        res_tiny = RULUncertaintyPropagator.propagate(
            rul_value=100.0,
            degradation_rate=1e-16,
            rate_uncertainty_component=comp_r,
        )
        assert res_tiny.status == UncertaintyStatus.INSUFFICIENT_EVIDENCE

    def test_delta_to_eol_zero_propagation(self) -> None:
        """Check 1.5, 1.6: Verifies RUL = 0 (at or beyond EOL) propagation safety."""
        comp_y = UncertaintyComponent(
            source_category=UncertaintySourceCategory.MEASUREMENT,
            status=UncertaintyStatus.ESTIMATED,
            standard_uncertainty=0.002,
        )
        res_zero_rul = RULUncertaintyPropagator.propagate(
            rul_value=0.0,
            degradation_rate=0.01,
            state_uncertainty_component=comp_y,
            confidence_level=0.95,
        )
        assert res_zero_rul.sensitivity_to_rate == 0.0
        assert res_zero_rul.sensitivity_to_state == pytest.approx(100.0, rel=1e-6)
        assert res_zero_rul.propagated_standard_uncertainty == pytest.approx(0.2, rel=1e-6)
        assert res_zero_rul.bounds is not None
        assert res_zero_rul.bounds.lower == 0.0  # non-negative truncated
        assert res_zero_rul.bounds.is_truncated_at_zero is True

    def test_nan_and_infinite_numerical_safety(self) -> None:
        """Check 1.7 - 1.12: Verifies rejection of NaN and infinite floats."""
        comp_valid = UncertaintyComponent(
            source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
            status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            standard_uncertainty=0.001,
        )

        # NaN / inf degradation rate
        with pytest.raises(ValueError, match="degradation_rate must be a finite float"):
            RULUncertaintyPropagator.propagate(rul_value=100.0, degradation_rate=float("nan"))

        with pytest.raises(ValueError, match="degradation_rate must be a finite float"):
            RULUncertaintyPropagator.propagate(rul_value=100.0, degradation_rate=float("inf"))

        # NaN / inf RUL value
        with pytest.raises(ValueError, match="rul_value must be a finite float"):
            RULUncertaintyPropagator.propagate(rul_value=float("nan"), degradation_rate=0.01)

        with pytest.raises(ValueError, match="rul_value must be a finite float"):
            RULUncertaintyPropagator.propagate(rul_value=float("inf"), degradation_rate=0.01)

        # NaN / inf slope or state uncertainty in UncertaintyComponent
        with pytest.raises(ValueError, match="standard_uncertainty must be a non-negative finite float"):
            UncertaintyComponent(
                source_category=UncertaintySourceCategory.MEASUREMENT,
                status=UncertaintyStatus.ESTIMATED,
                standard_uncertainty=float("nan"),
            )

        with pytest.raises(ValueError, match="standard_uncertainty must be a non-negative finite float"):
            UncertaintyComponent(
                source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
                status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
                standard_uncertainty=float("inf"),
            )

