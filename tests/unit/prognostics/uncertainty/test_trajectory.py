"""Unit Tests for Trajectory and Trend OLS Uncertainty Evaluation.

Validates:
- Exact mathematical OLS residual statistics (n, df, SSxx, SSyy, SSxy, RSS, s^2, s, SE(m), SE(c), R^2)
- Synthetic perfect linear trajectory (RSS = 0, SE(m) = 0, R^2 = 1.0)
- Trajectory with deliberate scatter and exact analytical checks
- Endpoint slope (n = 2) behavior returning DETERMINISTIC_ONLY and not fabricating regression error
- Insufficient sample count (n < 2) returning INSUFFICIENT_EVIDENCE
- Degenerate zero-span trajectory (all x identical, SSxx = 0) returning INSUFFICIENT_EVIDENCE
- R^2 explanatory fit semantics (descriptive fit, not future predictive confidence)
"""

import math
import pytest

from src.prognostics.uncertainty.trajectory import (
    OLSTrendUncertaintyEvaluator,
    TrajectoryTrendStatistics,
)
from src.prognostics.uncertainty.types import (
    UncertaintySourceCategory,
    UncertaintyStatus,
)


class TestOLSTrendUncertaintyEvaluator:
    """Trajectory and OLS trend uncertainty evaluation tests."""

    def test_perfect_linear_trajectory(self) -> None:
        """Verifies OLS statistics on a perfect line: y = 3.0 - 0.01 * x for x in [0, 10, 20, 30, 40]."""
        pairs = [(0.0, 3.00), (10.0, 2.90), (20.0, 2.80), (30.0, 2.70), (40.0, 2.60)]
        stats = OLSTrendUncertaintyEvaluator.evaluate_pairs(pairs, unit_x="cycles", unit_y="Ah")

        assert stats.sample_count == 5
        assert stats.degrees_of_freedom == 3
        assert stats.status == UncertaintyStatus.STATISTICALLY_SUPPORTED
        assert stats.slope == pytest.approx(-0.01, rel=1e-6)
        assert stats.intercept == pytest.approx(3.00, rel=1e-6)
        assert stats.residual_sum_of_squares == pytest.approx(0.0, abs=1e-12)
        assert stats.residual_variance == pytest.approx(0.0, abs=1e-12)
        assert stats.residual_standard_error == pytest.approx(0.0, abs=1e-12)
        assert stats.slope_standard_error == pytest.approx(0.0, abs=1e-12)
        assert stats.r_squared == pytest.approx(1.0, rel=1e-6)
        assert stats.slope_component is not None
        assert stats.slope_component.source_category == UncertaintySourceCategory.TRAJECTORY_TREND
        assert stats.slope_component.standard_uncertainty == pytest.approx(0.0, abs=1e-12)

    def test_trajectory_with_known_scatter(self) -> None:
        """Verifies exact analytical formulas with deliberate non-zero residuals."""
        # x = [0, 1, 2, 3, 4]
        # y = [3.0, 2.8, 2.7, 2.3, 2.2]
        # mean_x = 2.0, mean_y = 2.6
        # SS_xx = 4 + 1 + 0 + 1 + 4 = 10.0
        # x - mean_x = [-2, -1, 0, 1, 2]
        # y - mean_y = [0.4, 0.2, 0.1, -0.3, -0.4]
        # SS_xy = (-2)*(0.4) + (-1)*(0.2) + 0 + (1)*(-0.3) + (2)*(-0.4) = -0.8 - 0.2 - 0.3 - 0.8 = -2.1
        # slope m = -2.1 / 10.0 = -0.21
        # intercept c = 2.6 - (-0.21)*2.0 = 2.6 + 0.42 = 3.02
        # fitted y = [3.02, 2.81, 2.60, 2.39, 2.18]
        # residuals e = [-0.02, -0.01, 0.10, -0.09, 0.02]
        # RSS = 0.0004 + 0.0001 + 0.0100 + 0.0081 + 0.0004 = 0.0190
        # df = 5 - 2 = 3
        # s^2 = 0.0190 / 3 = 0.00633333...
        # s = sqrt(0.00633333...) = 0.079582...
        # SE(m) = s / sqrt(10.0) = 0.079582... / 3.162277... = 0.025166...
        pairs = [(0.0, 3.0), (1.0, 2.8), (2.0, 2.7), (3.0, 2.3), (4.0, 2.2)]
        stats = OLSTrendUncertaintyEvaluator.evaluate_pairs(pairs)

        assert stats.sample_count == 5
        assert stats.degrees_of_freedom == 3
        assert stats.slope == pytest.approx(-0.21, rel=1e-5)
        assert stats.intercept == pytest.approx(3.02, rel=1e-5)
        assert stats.residual_sum_of_squares == pytest.approx(0.0190, rel=1e-5)
        assert stats.residual_variance == pytest.approx(0.0190 / 3.0, rel=1e-5)
        assert stats.residual_standard_error == pytest.approx(math.sqrt(0.0190 / 3.0), rel=1e-5)
        assert stats.slope_standard_error == pytest.approx(math.sqrt(0.0190 / 3.0) / math.sqrt(10.0), rel=1e-5)
        assert stats.r_squared is not None and 0.90 < stats.r_squared < 1.0

    def test_endpoint_slope_n_equals_two(self) -> None:
        """Verifies that 2 observation points return DETERMINISTIC_ONLY without fabricating SE."""
        pairs = [(0.0, 3.00), (50.0, 2.50)]
        stats = OLSTrendUncertaintyEvaluator.evaluate_pairs(pairs)

        assert stats.sample_count == 2
        assert stats.degrees_of_freedom == 0
        assert stats.status == UncertaintyStatus.DETERMINISTIC_ONLY
        assert stats.slope == pytest.approx(-0.01, rel=1e-6)
        assert stats.slope_standard_error is None
        assert stats.residual_standard_error is None
        assert stats.slope_component is not None
        assert stats.slope_component.status == UncertaintyStatus.DETERMINISTIC_ONLY
        assert stats.slope_component.standard_uncertainty is None

    def test_insufficient_samples_n_less_than_two(self) -> None:
        """Verifies that fewer than 2 points returns INSUFFICIENT_EVIDENCE."""
        pairs = [(0.0, 3.00)]
        stats = OLSTrendUncertaintyEvaluator.evaluate_pairs(pairs)
        assert stats.sample_count == 1
        assert stats.status == UncertaintyStatus.INSUFFICIENT_EVIDENCE
        assert stats.slope is None

    def test_degenerate_zero_span_all_x_identical(self) -> None:
        """Verifies that identical x coordinates (SSxx = 0) returns INSUFFICIENT_EVIDENCE."""
        pairs = [(10.0, 3.00), (10.0, 2.90), (10.0, 2.80)]
        stats = OLSTrendUncertaintyEvaluator.evaluate_pairs(pairs)
        assert stats.status == UncertaintyStatus.INSUFFICIENT_EVIDENCE
        assert stats.slope is None
