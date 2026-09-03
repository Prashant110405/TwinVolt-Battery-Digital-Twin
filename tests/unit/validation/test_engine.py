"""Unit tests for ModelValidationEngine window lifecycle, state transitions, and history buffer."""

import unittest

from src.models.types import ModelOutput, ModelState
from src.runtime.synchronizer import TwinSyncOutput
from src.telemetry.snapshots import TelemetrySnapshot
from src.validation.engine import ModelValidationEngine
from src.validation.types import ModelValidationState, ValidationConfig


class MockSyncOutput:
    """Mock TwinSyncOutput container."""

    def __init__(
        self,
        v_sim: float = 3.8,
        v_oc: float = 3.9,
        t_sim: float = 25.0,
        soc_sim: float = 0.5,
        dt_s: float = 1.0,
    ) -> None:
        self.model_output = ModelOutput(
            terminal_voltage_v=v_sim,
            state=ModelState(soc_fraction=soc_sim, temperature_c=t_sim, soh_fraction=1.0),
            open_circuit_voltage_v=v_oc,
        )
        self.telemetry = TelemetrySnapshot(
            system_id="twin_01",
            snapshot_id="mock_sync_snap",
            timestamp_ns=0,
            pack_current_a=2.0,
        )
        self.estimation_output = None
        self.residuals = {"voltage_residual_v": 0.0}
        self.dt_s = dt_s


class TestModelValidationEngine(unittest.TestCase):
    """Test suite verifying ModelValidationEngine windowing lifecycle and validation state transitions."""

    def test_window_sealing_and_validated_state(self) -> None:
        """Well-tracked simulation over 60 seconds under dynamic current seals a VALIDATED window."""
        cfg = ValidationConfig(
            window_duration_s=10.0,
            min_samples_per_window=5,
            voltage_rmse_threshold_v=0.030,
            min_current_variance=0.01,
        )
        engine = ModelValidationEngine(system_id="twin_01", config=cfg)

        # Feed 12 samples (12 seconds) with small dynamic current (+3A, -2A) and low voltage error (5 mV)
        for i in range(12):
            t_s = i * 1.0
            i_k = 3.0 if i % 2 == 0 else -2.0
            v_meas = 3.805  # 5 mV error above v_sim = 3.800

            snap = TelemetrySnapshot(
                system_id="twin_01",
                snapshot_id=f"snap_{i}",
                timestamp_ns=int(t_s * 1_000_000_000),
                pack_current_a=i_k,
                pack_voltage_v=v_meas,
            )
            sync = MockSyncOutput(v_sim=3.800, v_oc=3.900, dt_s=1.0)
            report = engine.update(snapshot=snap, sync_output=sync, dt_s=1.0)

        # Assert window was sealed and recorded to history
        self.assertEqual(len(engine.validation_history), 1)
        completed = engine.validation_history[0]
        self.assertEqual(completed.state, ModelValidationState.VALIDATED)
        self.assertIsNotNone(completed.voltage_metrics)
        self.assertLess(completed.voltage_metrics.rmse, 0.030)

    def test_degraded_state_on_large_voltage_discrepancy(self) -> None:
        """Large voltage errors (>30 mV) result in DEGRADED validation state."""
        cfg = ValidationConfig(
            window_duration_s=10.0,
            min_samples_per_window=5,
            voltage_rmse_threshold_v=0.030,
        )
        engine = ModelValidationEngine(system_id="twin_01", config=cfg)

        for i in range(12):
            t_s = i * 1.0
            i_k = 3.0 if i % 2 == 0 else -2.0
            v_meas = 3.900  # 100 mV error above v_sim = 3.800

            snap = TelemetrySnapshot(
                system_id="twin_01",
                snapshot_id=f"snap_{i}",
                timestamp_ns=int(t_s * 1_000_000_000),
                pack_current_a=i_k,
                pack_voltage_v=v_meas,
            )
            sync = MockSyncOutput(v_sim=3.800, v_oc=3.900, dt_s=1.0)
            engine.update(snapshot=snap, sync_output=sync, dt_s=1.0)

        self.assertEqual(len(engine.validation_history), 1)
        completed = engine.validation_history[0]
        self.assertEqual(completed.state, ModelValidationState.DEGRADED)

    def test_steady_state_excitation_gating(self) -> None:
        """Constant DC current with zero variance yields EXCITATION_STEADY_STATE_ONLY state."""
        cfg = ValidationConfig(
            window_duration_s=10.0,
            min_samples_per_window=5,
            min_current_variance=0.01,
        )
        engine = ModelValidationEngine(system_id="twin_01", config=cfg)

        for i in range(12):
            t_s = i * 1.0
            snap = TelemetrySnapshot(
                system_id="twin_01",
                snapshot_id=f"snap_{i}",
                timestamp_ns=int(t_s * 1_000_000_000),
                pack_current_a=4.0,  # Flat constant DC current
                pack_voltage_v=3.802,
            )
            sync = MockSyncOutput(v_sim=3.800, dt_s=1.0)
            engine.update(snapshot=snap, sync_output=sync, dt_s=1.0)

        self.assertEqual(len(engine.validation_history), 1)
        completed = engine.validation_history[0]
        self.assertEqual(completed.state, ModelValidationState.EXCITATION_STEADY_STATE_ONLY)

    def test_telemetry_gap_interrupts_window_with_failure_state(self) -> None:
        """Telemetry gap > max_dt_s seals active window with DATA_QUALITY_FAILED and starts a new window."""
        cfg = ValidationConfig(max_dt_s=5.0)
        engine = ModelValidationEngine(system_id="twin_01", config=cfg)

        # Step 0 to 4 (4 seconds)
        for i in range(4):
            snap = TelemetrySnapshot(
                system_id="twin_01",
                snapshot_id=f"snap_{i}",
                timestamp_ns=i * 1_000_000_000,
                pack_current_a=2.0,
                pack_voltage_v=3.8,
            )
            sync = MockSyncOutput(v_sim=3.8)
            engine.update(snapshot=snap, sync_output=sync, dt_s=1.0)

        # Step at t = 50s (46 second gap)
        s_gap = TelemetrySnapshot(
            system_id="twin_01",
            snapshot_id="snap_gap",
            timestamp_ns=50 * 1_000_000_000,
            pack_current_a=2.0,
            pack_voltage_v=3.8,
        )
        sync_gap = MockSyncOutput(v_sim=3.8)
        engine.update(snapshot=s_gap, sync_output=sync_gap, dt_s=1.0)

        # Assert pre-gap window was sealed with DATA_QUALITY_FAILED
        self.assertEqual(len(engine.validation_history), 1)
        interrupted_win = engine.validation_history[0]
        self.assertEqual(interrupted_win.state, ModelValidationState.DATA_QUALITY_FAILED)


if __name__ == "__main__":
    unittest.main()
