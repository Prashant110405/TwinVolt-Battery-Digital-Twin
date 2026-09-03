"""Unit tests for PhysicsAnomalyDetector and AnomalyReport."""

import unittest

from src.models.types import ModelInput, ModelMetadata, ModelOutput, ModelState
from src.runtime.anomaly_detector import PhysicsAnomalyDetector
from src.runtime.config import AnomalyThresholds, ResidualTolerances, RuntimeConfig
from src.runtime.synchronizer import TwinSyncOutput
from src.telemetry.measurements import CellTelemetry
from src.telemetry.snapshots import TelemetrySnapshot


class TestPhysicsAnomalyDetector(unittest.TestCase):
    """Test suite verifying physics-informed anomaly and safety precursor detection."""

    def setUp(self) -> None:
        self.config = RuntimeConfig(
            tolerances=ResidualTolerances(
                voltage_warning_threshold_v=0.05,
                voltage_critical_threshold_v=0.15,
                temperature_warning_threshold_c=3.0,
                temperature_critical_threshold_c=8.0,
                soc_warning_threshold=0.05,
                soc_critical_threshold=0.15,
                cell_voltage_delta_max_v=0.08,
            ),
            anomaly_thresholds=AnomalyThresholds(
                critical_thermal_cutoff_c=65.0,
                max_temperature_rate_c_per_s=0.5,
                sensor_drift_window_size=5,
                sensor_drift_mean_bias_v=0.04,
                min_samples_for_drift_detection=3,
            ),
        )
        self.detector = PhysicsAnomalyDetector(config=self.config)

    def _create_mock_sync_output(
        self,
        v_meas: float = 3.7,
        v_sim: float = 3.7,
        t_meas: float = 25.0,
        t_sim: float = 25.0,
        ts_ns: int = 1_000_000_000,
        cell_voltages: tuple[float, ...] = (3.7, 3.7),
    ) -> TwinSyncOutput:
        """Helper constructing a mock TwinSyncOutput for testing anomaly evaluation."""
        cells = tuple(
            CellTelemetry(cell_id=f"cell_{i:02d}", voltage_v=v)
            for i, v in enumerate(cell_voltages)
        )
        snap = TelemetrySnapshot(
            snapshot_id="snap_test",
            system_id="test_pack",
            timestamp_ns=ts_ns,
            pack_voltage_v=v_meas,
            avg_cell_temperature_c=t_meas,
            cell_telemetries=cells,
        )
        m_state = ModelState(soc_fraction=0.8, temperature_c=t_sim)
        m_out = ModelOutput(
            terminal_voltage_v=v_sim,
            open_circuit_voltage_v=v_sim,
            state=m_state,
        )
        residuals = {
            "voltage_residual_v": v_meas - v_sim,
            "temp_residual_c": t_meas - t_sim,
        }
        return TwinSyncOutput(
            step_index=1,
            timestamp_ns=ts_ns,
            dt_s=1.0,
            telemetry=snap,
            model_output=m_out,
            residuals=residuals,
        )

    def test_nominal_tracking_produces_zero_anomalies(self) -> None:
        """Nominal tracking within tolerances produces no anomalies."""
        sync_out = self._create_mock_sync_output(
            v_meas=3.702,
            v_sim=3.700,
            t_meas=25.2,
            t_sim=25.0,
        )
        report = self.detector.evaluate(sync_out)
        self.assertFalse(report.has_anomalies)
        self.assertEqual(report.max_severity, "NONE")
        self.assertEqual(len(report.anomalies), 0)

    def test_voltage_divergence_warning_and_critical(self) -> None:
        """Voltage residual exceeding warning/critical triggers respective severity."""
        # Warning (60 mV > 50 mV warning threshold, < 150 mV critical)
        out_warn = self._create_mock_sync_output(v_meas=3.76, v_sim=3.70)
        report_warn = self.detector.evaluate(out_warn)
        self.assertTrue(report_warn.has_anomalies)
        self.assertEqual(report_warn.max_severity, "WARNING")
        self.assertEqual(report_warn.anomalies[0].anomaly_type, "VOLTAGE_DIVERGENCE")

        # Critical (200 mV > 150 mV critical threshold)
        out_crit = self._create_mock_sync_output(v_meas=3.90, v_sim=3.70)
        report_crit = self.detector.evaluate(out_crit)
        self.assertEqual(report_crit.max_severity, "CRITICAL")
        self.assertEqual(report_crit.anomalies[0].severity, "CRITICAL")

    def test_thermal_divergence_warning_and_critical(self) -> None:
        """Temperature residual exceeding warning/critical triggers respective severity."""
        # Warning (4°C > 3°C warning, < 8°C critical)
        out_warn = self._create_mock_sync_output(t_meas=29.0, t_sim=25.0)
        report_warn = self.detector.evaluate(out_warn)
        self.assertEqual(report_warn.max_severity, "WARNING")
        self.assertEqual(report_warn.anomalies[0].anomaly_type, "THERMAL_DIVERGENCE")

        # Critical (10°C > 8°C critical)
        out_crit = self._create_mock_sync_output(t_meas=35.0, t_sim=25.0)
        report_crit = self.detector.evaluate(out_crit)
        self.assertEqual(report_crit.max_severity, "CRITICAL")

    def test_thermal_runaway_emergency_cutoff(self) -> None:
        """Exceeding critical thermal limit triggers EMERGENCY anomaly."""
        out_emergency = self._create_mock_sync_output(t_meas=68.0, t_sim=60.0)
        report = self.detector.evaluate(out_emergency)
        self.assertEqual(report.max_severity, "EMERGENCY")
        types = [a.anomaly_type for a in report.anomalies]
        self.assertIn("THERMAL_RUNAWAY_PRECURSOR", types)

    def test_rapid_temperature_rate_of_rise(self) -> None:
        """Rate of temperature rise >= 0.5°C/s triggers CRITICAL thermal precursor."""
        out1 = self._create_mock_sync_output(t_meas=30.0, ts_ns=1_000_000_000)
        self.detector.evaluate(out1)

        # 1 second later, temperature jumped by 1.0°C (1.0°C/s > 0.5°C/s)
        out2 = self._create_mock_sync_output(t_meas=31.0, ts_ns=2_000_000_000)
        report2 = self.detector.evaluate(out2)
        self.assertTrue(report2.has_anomalies)
        types = [a.anomaly_type for a in report2.anomalies]
        self.assertIn("THERMAL_RUNAWAY_PRECURSOR", types)

    def test_cell_voltage_dispersion_anomaly(self) -> None:
        """Cell voltage dispersion >= 80mV triggers CELL_IMBALANCE_DIVERGENCE."""
        out_imbalance = self._create_mock_sync_output(
            cell_voltages=(3.75, 3.65),  # Delta = 100 mV > 80 mV
        )
        report = self.detector.evaluate(out_imbalance)
        self.assertTrue(report.has_anomalies)
        types = [a.anomaly_type for a in report.anomalies]
        self.assertIn("CELL_IMBALANCE_DIVERGENCE", types)

    def test_rolling_sensor_drift_detection(self) -> None:
        """Continuous residual bias across rolling window triggers SENSOR_DRIFT."""
        # Feed 4 consecutive samples with +0.045V bias (< 0.05V single-sample warning, but > 0.04V mean drift)
        for i in range(4):
            out = self._create_mock_sync_output(
                v_meas=3.745,
                v_sim=3.700,
                ts_ns=1_000_000_000 * (i + 1),
            )
            report = self.detector.evaluate(out)

        self.assertTrue(report.has_anomalies)
        types = [a.anomaly_type for a in report.anomalies]
        self.assertIn("SENSOR_DRIFT", types)

    def test_reset_clears_detector_state(self) -> None:
        """Reset clears previous temperature tracking and rolling residuals."""
        out = self._create_mock_sync_output(v_meas=3.745, v_sim=3.700)
        self.detector.evaluate(out)
        self.assertEqual(len(self.detector._voltage_residuals), 1)

        self.detector.reset()
        self.assertEqual(len(self.detector._voltage_residuals), 0)
        self.assertIsNone(self.detector._prev_temp_c)


if __name__ == "__main__":
    unittest.main()
