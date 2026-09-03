"""Unit tests for TrackingMetricsEvaluator and SignalTrackingMetrics."""

import math
import unittest

from src.models.types import ModelOutput, ModelState
from src.replay.evaluator import (
    SignalTrackingMetrics,
    TrackingMetricsEvaluator,
    TrackingMetricsReport,
)
from src.replay.exceptions import EvaluationError
from src.runtime.synchronizer import TwinSyncOutput
from src.telemetry.snapshots import TelemetrySnapshot


class TestTrackingMetricsEvaluator(unittest.TestCase):
    """Test suite verifying mathematical accuracy of RMSE, MAE, Max Error, MBE, R^2, and NRMSE."""

    def setUp(self) -> None:
        self.evaluator = TrackingMetricsEvaluator()

    def test_exact_zero_error_on_identical_signals(self) -> None:
        """Identical observed and simulated signals produce zero errors and perfect R^2 = 1.0."""
        signal = [3.2, 3.4, 3.6, 3.8, 4.0, 4.2]
        metrics = self.evaluator.compute_signal_metrics("voltage_v", signal, signal)

        self.assertEqual(metrics.signal_name, "voltage_v")
        self.assertEqual(metrics.sample_count, 6)
        self.assertEqual(metrics.rmse, 0.0)
        self.assertEqual(metrics.mae, 0.0)
        self.assertEqual(metrics.max_error, 0.0)
        self.assertEqual(metrics.mean_bias_error, 0.0)
        self.assertEqual(metrics.r_squared, 1.0)
        self.assertEqual(metrics.nrmse, 0.0)
        self.assertEqual(metrics.observed_mean, sum(signal) / 6)

    def test_constant_offset_analytical_metrics(self) -> None:
        """Known constant offset matches analytical error metrics."""
        obs = [10.0, 20.0, 30.0, 40.0]
        # Offset by +2.0 (simulated is 2.0 higher than observed)
        sim = [12.0, 22.0, 32.0, 42.0]

        metrics = self.evaluator.compute_signal_metrics("test_signal", obs, sim)

        self.assertEqual(metrics.mae, 2.0)
        self.assertEqual(metrics.rmse, 2.0)
        self.assertEqual(metrics.max_error, 2.0)
        self.assertEqual(metrics.mean_bias_error, -2.0)  # y - y_hat = -2.0
        self.assertAlmostEqual(metrics.nrmse, 2.0 / 30.0, places=5)

    def test_dynamic_error_analytical_metrics(self) -> None:
        """Dynamic varying errors match hand-computed statistical metrics."""
        obs = [3.0, 3.5, 4.0]
        sim = [3.1, 3.4, 4.2]
        # errors: [-0.1, +0.1, -0.2]
        # abs errors: [0.1, 0.1, 0.2] -> MAE = 0.4 / 3 = 0.13333...
        # sq errors: [0.01, 0.01, 0.04] = 0.06 -> MSE = 0.02, RMSE = sqrt(0.02) ≈ 0.141421
        # max_error: 0.2
        # MBE: -0.2 / 3 = -0.06666...
        # SS_tot: (3.0-3.5)^2 + (3.5-3.5)^2 + (4.0-3.5)^2 = 0.25 + 0 + 0.25 = 0.50
        # SS_res: 0.06 -> R^2 = 1 - (0.06 / 0.50) = 0.88

        metrics = self.evaluator.compute_signal_metrics("voltage_v", obs, sim)

        self.assertAlmostEqual(metrics.mae, 0.4 / 3.0, places=5)
        self.assertAlmostEqual(metrics.rmse, math.sqrt(0.02), places=5)
        self.assertAlmostEqual(metrics.max_error, 0.2, places=5)
        self.assertAlmostEqual(metrics.mean_bias_error, -0.2 / 3.0, places=5)
        self.assertAlmostEqual(metrics.r_squared, 0.88, places=5)
        self.assertAlmostEqual(metrics.nrmse, math.sqrt(0.02) / 1.0, places=5)

    def test_constant_signal_edge_case_r_squared(self) -> None:
        """Constant signals handle zero variance without ZeroDivisionError."""
        const_obs = [3.7, 3.7, 3.7]
        # Perfect match on constant signal
        m_perfect = self.evaluator.compute_signal_metrics("const", const_obs, const_obs)
        self.assertEqual(m_perfect.r_squared, 1.0)
        self.assertEqual(m_perfect.rmse, 0.0)

        # Discrepant match on constant signal
        const_sim = [3.8, 3.8, 3.8]
        m_offset = self.evaluator.compute_signal_metrics("const", const_obs, const_sim)
        self.assertEqual(m_offset.r_squared, 0.0)
        self.assertAlmostEqual(m_offset.mae, 0.1, places=6)

    def test_evaluate_from_sync_outputs(self) -> None:
        """Evaluator extracts voltage, temperature, and SOC signals from sync outputs."""
        sync_outputs = []
        for i in range(5):
            snap = TelemetrySnapshot(
                snapshot_id=f"s_{i}",
                system_id="pack_test",
                timestamp_ns=1_000_000_000 * (i + 1),
                pack_voltage_v=3.60 + 0.05 * i,
                avg_cell_temperature_c=25.0 + 0.5 * i,
                soc_fraction=0.90 - 0.02 * i,
            )
            m_state = ModelState(soc_fraction=0.90 - 0.02 * i, temperature_c=25.0 + 0.4 * i)
            m_out = ModelOutput(
                terminal_voltage_v=3.60 + 0.04 * i,
                open_circuit_voltage_v=3.60,
                state=m_state,
            )
            out = TwinSyncOutput(
                step_index=i + 1,
                timestamp_ns=snap.timestamp_ns,
                dt_s=1.0,
                telemetry=snap,
                model_output=m_out,
            )
            sync_outputs.append(out)

        # 1. Evaluate with passing thresholds
        report_pass = self.evaluator.evaluate_from_sync_outputs(
            sync_outputs=sync_outputs,
            system_id="pack_test",
            profile_name="test_run",
            target_voltage_rmse_v=0.10,
            target_temp_rmse_c=1.0,
            target_soc_rmse=0.05,
        )
        self.assertTrue(report_pass.is_passing)
        self.assertIsNotNone(report_pass.voltage_metrics)
        self.assertIsNotNone(report_pass.temperature_metrics)
        self.assertIsNotNone(report_pass.soc_metrics)

        # 2. Evaluate with failing voltage threshold (voltage RMSE is > 0.001)
        report_fail = self.evaluator.evaluate_from_sync_outputs(
            sync_outputs=sync_outputs,
            system_id="pack_test",
            profile_name="test_run",
            target_voltage_rmse_v=0.001,
        )
        self.assertFalse(report_fail.is_passing)

    def test_evaluator_validates_inputs(self) -> None:
        """Evaluator raises EvaluationError on empty, mismatched, or non-finite inputs."""
        with self.assertRaises(EvaluationError):
            self.evaluator.compute_signal_metrics("empty", [], [])

        with self.assertRaises(EvaluationError):
            self.evaluator.compute_signal_metrics("mismatch", [1.0, 2.0], [1.0])

        with self.assertRaises(EvaluationError):
            self.evaluator.compute_signal_metrics("nan", [1.0, float("nan")], [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
