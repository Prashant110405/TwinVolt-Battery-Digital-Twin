"""Unit tests for TwinSynchronizer and TwinSyncOutput."""

import unittest

from src.estimators.coulomb_counter import CoulombCounter
from src.estimators.ekf import ExtendedKalmanFilter
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelMetadata
from src.runtime.config import ResidualTolerances, RuntimeConfig
from src.runtime.exceptions import ClockSkewError, SynchronizationError
from src.runtime.synchronizer import TwinSyncOutput, TwinSynchronizer
from src.telemetry.enums import CurrentFlowDirection, TelemetryQuality
from src.telemetry.snapshots import TelemetrySnapshot


class TestTwinSynchronizer(unittest.TestCase):
    """Test suite verifying discrete co-simulation synchronization, residuals, and timing logic."""

    def setUp(self) -> None:
        self.ocv = LinearOCVModel(v_min_v=3.0, v_max_v=4.2)
        self.params = GenericECMParameters(
            nominal_capacity_ah=2.5,
            nominal_voltage_v=3.7,
            series_resistance_r0_ohm=0.02,
            rc_branches=(RCBranchParameters(resistance_r_ohm=0.01, capacitance_c_farad=100.0),),
        )
        self.meta = ModelMetadata(
            model_id="ecm_sync_test",
            name="Test ECM",
            paradigm="EQUIVALENT_CIRCUIT",
        )
        self.model = GenericECMModel(
            metadata=self.meta,
            parameters=self.params,
            ocv_model=self.ocv,
        )
        self.model.initialize(soc_init=1.0, temperature_c=25.0)

        self.estimator = ExtendedKalmanFilter(
            estimator_id="ekf_sync_test",
            parameters=self.params,
            ocv_model=self.ocv,
        )
        self.estimator.initialize(initial_soc=1.0, initial_soh=1.0, temperature_c=25.0)

        self.config = RuntimeConfig(
            system_id="test_cell_01",
            default_dt_s=1.0,
            min_dt_s=0.001,
            max_dt_s=10.0,
            strict_monotonicity=True,
            stale_timeout_s=60.0,
        )
        self.synchronizer = TwinSynchronizer(
            battery_model=self.model,
            state_estimator=self.estimator,
            config=self.config,
        )

    def test_single_step_co_simulation_success(self) -> None:
        """Synchronizer executes discrete step and computes physical residuals."""
        snap = TelemetrySnapshot(
            snapshot_id="snap_01",
            system_id="test_cell_01",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=4.15,
            pack_current_a=1.0,
            avg_cell_temperature_c=25.5,
            soc_fraction=0.99,
        )

        out = self.synchronizer.step(snap)
        self.assertIsInstance(out, TwinSyncOutput)
        self.assertEqual(out.step_index, 1)
        self.assertEqual(out.timestamp_ns, 1_000_000_000)
        self.assertEqual(out.dt_s, 1.0)
        self.assertEqual(out.quality, "VALID")
        self.assertIsNotNone(out.model_output)
        self.assertIsNotNone(out.estimation_output)

        # Residuals
        self.assertIn("voltage_residual_v", out.residuals)
        self.assertIn("temp_residual_c", out.residuals)
        self.assertIn("soc_discrepancy", out.residuals)

        # Voltage residual = V_meas - V_sim
        expected_v_res = 4.15 - out.model_output.terminal_voltage_v
        self.assertAlmostEqual(out.residuals["voltage_residual_v"], expected_v_res, places=5)

    def test_step_without_state_estimator(self) -> None:
        """Synchronizer functions cleanly when state_estimator is omitted."""
        sync_no_est = TwinSynchronizer(battery_model=self.model, state_estimator=None)
        snap = TelemetrySnapshot(
            snapshot_id="snap_no_est",
            system_id="test_cell_01",
            timestamp_ns=2_000_000_000,
            pack_voltage_v=4.10,
            pack_current_a=2.0,
        )
        out = sync_no_est.step(snap)
        self.assertIsNone(out.estimation_output)
        self.assertNotIn("soc_discrepancy", out.residuals)
        self.assertIn("voltage_residual_v", out.residuals)

    def test_timestamp_delta_dt_calculation(self) -> None:
        """Sequential timestamps correctly compute dt_s."""
        snap1 = TelemetrySnapshot(
            snapshot_id="s1",
            system_id="test_cell_01",
            timestamp_ns=1_000_000_000,  # 1.0s
            pack_voltage_v=4.18,
            pack_current_a=1.0,
        )
        snap2 = TelemetrySnapshot(
            snapshot_id="s2",
            system_id="test_cell_01",
            timestamp_ns=1_500_000_000,  # 1.5s -> dt = 0.5s
            pack_voltage_v=4.16,
            pack_current_a=1.0,
        )

        out1 = self.synchronizer.step(snap1)
        self.assertEqual(out1.dt_s, 1.0)  # Default on first step

        out2 = self.synchronizer.step(snap2)
        self.assertAlmostEqual(out2.dt_s, 0.5, places=5)
        self.assertEqual(self.synchronizer.step_count, 2)

    def test_strict_monotonicity_raises_on_backward_timestamp(self) -> None:
        """Strict monotonicity mode raises ClockSkewError on out-of-order timestamp."""
        snap1 = TelemetrySnapshot(
            snapshot_id="s1",
            system_id="test_cell_01",
            timestamp_ns=2_000_000_000,
            pack_voltage_v=4.18,
        )
        snap_backward = TelemetrySnapshot(
            snapshot_id="s2",
            system_id="test_cell_01",
            timestamp_ns=1_000_000_000,  # Backward in time
            pack_voltage_v=4.18,
        )

        self.synchronizer.step(snap1)
        with self.assertRaises(ClockSkewError):
            self.synchronizer.step(snap_backward)

    def test_lenient_monotonicity_handles_backward_timestamp(self) -> None:
        """Non-strict mode flags DEGRADED quality without raising."""
        lenient_config = RuntimeConfig(
            system_id="test_cell_01",
            strict_monotonicity=False,
            default_dt_s=1.0,
        )
        sync_lenient = TwinSynchronizer(
            battery_model=self.model,
            state_estimator=self.estimator,
            config=lenient_config,
        )

        snap1 = TelemetrySnapshot(
            snapshot_id="s1",
            system_id="test_cell_01",
            timestamp_ns=5_000_000_000,
            pack_voltage_v=4.18,
        )
        snap2 = TelemetrySnapshot(
            snapshot_id="s2",
            system_id="test_cell_01",
            timestamp_ns=4_000_000_000,
            pack_voltage_v=4.18,
        )

        out1 = sync_lenient.step(snap1)
        self.assertEqual(out1.quality, "VALID")

        out2 = sync_lenient.step(snap2)
        self.assertEqual(out2.quality, "DEGRADED")
        self.assertEqual(out2.dt_s, 1.0)

    def test_stale_telemetry_detection(self) -> None:
        """Telemetry arriving after stale_timeout_s is marked as STALE."""
        snap1 = TelemetrySnapshot(
            snapshot_id="s1",
            system_id="test_cell_01",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=4.18,
        )
        # 100 seconds later (stale_timeout_s is 60.0s)
        snap_stale = TelemetrySnapshot(
            snapshot_id="s2",
            system_id="test_cell_01",
            timestamp_ns=101_000_000_000,
            pack_voltage_v=4.18,
        )

        self.synchronizer.step(snap1)
        out = self.synchronizer.step(snap_stale)
        self.assertEqual(out.quality, "STALE")

    def test_missing_optional_telemetry_measurements(self) -> None:
        """Missing current or temperature gracefully defaults without error."""
        snap_sparse = TelemetrySnapshot(
            snapshot_id="s_sparse",
            system_id="test_cell_01",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=4.18,
            # current_a and temperature are None
        )
        out = self.synchronizer.step(snap_sparse)
        self.assertEqual(out.quality, "VALID")
        self.assertIsNotNone(out.model_output)

    def test_reset_cleans_state(self) -> None:
        """Reset clears previous timestamp and step counter."""
        snap = TelemetrySnapshot(
            snapshot_id="s1",
            system_id="test_cell_01",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=4.18,
        )
        self.synchronizer.step(snap)
        self.assertEqual(self.synchronizer.step_count, 1)

        self.synchronizer.reset()
        self.assertEqual(self.synchronizer.step_count, 0)
        self.assertIsNone(self.synchronizer.previous_timestamp_ns)


if __name__ == "__main__":
    unittest.main()
