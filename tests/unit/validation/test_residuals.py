"""Unit tests for ResidualStatisticsAccumulator and Welford statistical error computation."""

import math
import unittest

from src.validation.residuals import ResidualStatisticsAccumulator
from src.validation.types import SignalProvenance


class TestResidualStatisticsAccumulator(unittest.TestCase):
    """Test suite verifying numerically stable Welford residual statistics and paired R^2 computation."""

    def test_zero_residuals_exact_match(self) -> None:
        """Identical measured and simulated signals yield zero error across all statistical moments."""
        acc = ResidualStatisticsAccumulator()
        for v in [3.5, 3.6, 3.7, 3.8, 3.9]:
            acc.update(measured=v, simulated=v)

        metrics = acc.compute_metrics("voltage_v")
        self.assertEqual(metrics.sample_count, 5)
        self.assertEqual(metrics.rmse, 0.0)
        self.assertEqual(metrics.mae, 0.0)
        self.assertEqual(metrics.max_error, 0.0)
        self.assertEqual(metrics.mean_bias_error, 0.0)
        self.assertEqual(metrics.std_dev, 0.0)
        self.assertAlmostEqual(metrics.r_squared, 1.0, places=6)
        self.assertIsNone(metrics.r_squared_diagnostic)

    def test_known_residual_sequence_accuracy(self) -> None:
        """Verifies exact analytical calculation against a known residual sequence."""
        # Errors: [0.1, -0.2, 0.3, -0.4, 0.5]
        meas = [3.1, 3.3, 3.5, 3.7, 3.9]
        sim = [3.0, 3.5, 3.2, 4.1, 3.4]
        acc = ResidualStatisticsAccumulator()

        for m, s in zip(meas, sim):
            acc.update(measured=m, simulated=s)

        metrics = acc.compute_metrics("voltage_v")
        self.assertEqual(metrics.sample_count, 5)

        # Expected values:
        # sum_error = 0.1 - 0.2 + 0.3 - 0.4 + 0.5 = 0.3
        # mbe = 0.3 / 5 = 0.06
        self.assertAlmostEqual(metrics.mean_bias_error, 0.06, places=8)

        # sum_abs = 0.1 + 0.2 + 0.3 + 0.4 + 0.5 = 1.5
        # mae = 1.5 / 5 = 0.3
        self.assertAlmostEqual(metrics.mae, 0.3, places=8)

        # sum_sq = 0.01 + 0.04 + 0.09 + 0.16 + 0.25 = 0.55
        # rmse = sqrt(0.55 / 5) = sqrt(0.11)
        expected_rmse = math.sqrt(0.11)
        self.assertAlmostEqual(metrics.rmse, expected_rmse, places=8)

        # max_error = 0.5
        self.assertAlmostEqual(metrics.max_error, 0.5, places=8)

        # Sample variance = sum((e_i - mbe)^2) / 4
        # (0.1 - 0.06)^2 + (-0.2 - 0.06)^2 + (0.3 - 0.06)^2 + (-0.4 - 0.06)^2 + (0.5 - 0.06)^2 = 0.532 / 4 = 0.133
        expected_std = math.sqrt(0.133)
        self.assertAlmostEqual(metrics.std_dev, expected_std, places=8)

    def test_paired_r_squared_calculation(self) -> None:
        """Verifies paired R^2 computation for well-correlated signals."""
        meas = [3.0, 3.2, 3.4, 3.6, 3.8, 4.0]
        sim = [3.01, 3.19, 3.42, 3.58, 3.81, 3.99]
        acc = ResidualStatisticsAccumulator()

        for m, s in zip(meas, sim):
            acc.update(measured=m, simulated=s)

        metrics = acc.compute_metrics("voltage_v")
        self.assertIsNotNone(metrics.r_squared)
        self.assertGreater(metrics.r_squared, 0.99)
        self.assertIsNone(metrics.r_squared_diagnostic)

    def test_zero_measured_variance_safe_r_squared_handling(self) -> None:
        """When measured signal is constant (zero variance), R^2 is None with explicit diagnostic reason."""
        meas = [3.8, 3.8, 3.8, 3.8]  # Zero SST
        sim = [3.81, 3.82, 3.79, 3.80]
        acc = ResidualStatisticsAccumulator()

        for m, s in zip(meas, sim):
            acc.update(measured=m, simulated=s)

        metrics = acc.compute_metrics("voltage_v")
        self.assertIsNone(metrics.r_squared)
        self.assertEqual(metrics.r_squared_diagnostic, "ZERO_MEASURED_VARIANCE")

    def test_insufficient_samples_handling(self) -> None:
        """Accumulator gracefully handles 0 or 1 sample without division by zero."""
        acc = ResidualStatisticsAccumulator()
        m0 = acc.compute_metrics("voltage_v")
        self.assertEqual(m0.sample_count, 0)
        self.assertEqual(m0.r_squared_diagnostic, "INSUFFICIENT_SAMPLES")

        acc.update(3.6, 3.5)
        m1 = acc.compute_metrics("voltage_v")
        self.assertEqual(m1.sample_count, 1)
        self.assertEqual(m1.std_dev, 0.0)
        self.assertEqual(m1.r_squared_diagnostic, "INSUFFICIENT_SAMPLES")


if __name__ == "__main__":
    unittest.main()
