"""Unit tests for Excitation Gating, Observability Criteria, and Safety Guards."""

import unittest
from src.calibration.gating import ExcitationDetector
from src.calibration.guard import ParameterSafetyGuard
from src.calibration.rls import RLSParameterIdentifier
from src.calibration.types import RLSConfig
from src.telemetry.enums import TelemetryQuality
from src.telemetry.snapshots import TelemetrySnapshot


class MockSyncOutput:
    """Mock TwinSyncOutput container."""

    def __init__(
        self,
        soc_fraction: float = 0.5,
        open_circuit_voltage_v: float = 3.6,
        voltage_residual_v: float = 0.0,
        dt_s: float = 1.0,
    ) -> None:
        self.model_output = type(
            "MockModelOutput",
            (),
            {
                "open_circuit_voltage_v": open_circuit_voltage_v,
                "state": type("MockState", (), {"soc_fraction": soc_fraction})(),
            },
        )()
        self.residuals = {"voltage_residual_v": voltage_residual_v}
        self.dt_s = dt_s


class TestExcitationGatingAndSafetyGuard(unittest.TestCase):
    """Test suite verifying excitation gating, gap detection, outlier rejection, and physical bounds."""

    def test_constant_current_hold_prevents_secondary_drift(self) -> None:
        """Constant DC current has zero variance; secondary R1/C1 identification is gated."""
        detector = ExcitationDetector(config=RLSConfig(min_current_variance=0.01))

        # Feed 10 steps of flat 5.0 A current
        for i in range(10):
            snap = TelemetrySnapshot(
                system_id="twin_01",
                snapshot_id=f"snap_{i}",
                timestamp_ns=(i + 1) * 1_000_000_000,
                pack_current_a=5.0,
                pack_voltage_v=3.5,
            )
            res = detector.evaluate(snap, soc_estimate=0.5)

        # Primary R0 can be observed, but secondary is gated due to zero variance
        self.assertTrue(res.can_update_r0)
        self.assertFalse(res.can_update_secondary)
        self.assertEqual(res.gating_status, "PRIMARY_ONLY_R0")

    def test_low_current_magnitude_gating(self) -> None:
        """Current below min_current_a threshold (0.1 A) is gated completely."""
        detector = ExcitationDetector(config=RLSConfig(min_current_a=0.1))

        snap = TelemetrySnapshot(
            system_id="twin_01",
            snapshot_id="snap_01",
            timestamp_ns=1_000_000_000,
            pack_current_a=0.03,
            pack_voltage_v=3.6,
        )
        res = detector.evaluate(snap, soc_estimate=0.5)

        self.assertFalse(res.can_update_r0)
        self.assertFalse(res.can_update_secondary)
        self.assertEqual(res.gating_status, "INSUFFICIENT_CURRENT")

    def test_soc_cliff_regime_gating(self) -> None:
        """SOC outside [0.10, 0.90] is gated to prevent steep OCV slope bias."""
        detector = ExcitationDetector(config=RLSConfig(min_soc=0.10, max_soc=0.90))

        snap1 = TelemetrySnapshot(
            system_id="twin_01",
            snapshot_id="snap_01",
            timestamp_ns=1_000_000_000,
            pack_current_a=3.0,
            pack_voltage_v=3.1,
        )
        res_low = detector.evaluate(snap1, soc_estimate=0.05)
        self.assertFalse(res_low.can_update_r0)
        self.assertEqual(res_low.gating_status, "SOC_CLIFF_REGIME")

        snap2 = TelemetrySnapshot(
            system_id="twin_01",
            snapshot_id="snap_02",
            timestamp_ns=2_000_000_000,
            pack_current_a=3.0,
            pack_voltage_v=3.1,
        )
        res_high = detector.evaluate(snap2, soc_estimate=0.95)
        self.assertFalse(res_high.can_update_r0)
        self.assertEqual(res_high.gating_status, "SOC_CLIFF_REGIME")

    def test_voltage_residual_outlier_rejection(self) -> None:
        """Voltage residuals exceeding threshold are rejected as sensor glitches/outliers."""
        detector = ExcitationDetector(config=RLSConfig(max_voltage_residual_v=0.15))

        snap = TelemetrySnapshot(
            system_id="twin_01",
            snapshot_id="snap_01",
            timestamp_ns=1_000_000_000,
            pack_current_a=3.0,
            pack_voltage_v=3.6,
        )
        res = detector.evaluate(snap, soc_estimate=0.5, voltage_residual_v=0.25)

        self.assertFalse(res.can_update_r0)
        self.assertEqual(res.gating_status, "VOLTAGE_RESIDUAL_OUTLIER")

    def test_duplicate_and_retrograde_timestamps(self) -> None:
        """Duplicate or retrograde timestamps return non-monotonic gating status and are ignored."""
        detector = ExcitationDetector()

        s0 = TelemetrySnapshot(
            system_id="twin_01",
            snapshot_id="snap_0",
            timestamp_ns=1000,
            pack_current_a=2.0,
        )
        detector.evaluate(s0, soc_estimate=0.5)

        # Duplicate
        s_dup = TelemetrySnapshot(
            system_id="twin_01",
            snapshot_id="snap_dup",
            timestamp_ns=1000,
            pack_current_a=2.0,
        )
        res_dup = detector.evaluate(s_dup, soc_estimate=0.5)
        self.assertFalse(res_dup.is_valid_step)
        self.assertEqual(res_dup.gating_status, "NON_MONOTONIC_TIMESTAMP")

    def test_telemetry_gap_handling(self) -> None:
        """Telemetry gap > max_dt_s triggers gap detection and inflates covariance."""
        identifier = RLSParameterIdentifier(
            system_id="gap_twin",
            config=RLSConfig(max_dt_s=5.0, gap_covariance_inflation_factor=2.0),
        )

        s0 = TelemetrySnapshot(
            system_id="gap_twin",
            snapshot_id="snap_0",
            timestamp_ns=0,
            pack_current_a=2.0,
            pack_voltage_v=3.6,
        )
        sync0 = MockSyncOutput(soc_fraction=0.5, open_circuit_voltage_v=3.6)
        identifier.update(s0, sync0, dt_s=1.0)

        cov_before = identifier._ud.get_trace()

        # Step 100 seconds later
        s_gap = TelemetrySnapshot(
            system_id="gap_twin",
            snapshot_id="snap_gap",
            timestamp_ns=100 * 1_000_000_000,
            pack_current_a=2.0,
            pack_voltage_v=3.6,
        )
        sync_gap = MockSyncOutput(soc_fraction=0.5, open_circuit_voltage_v=3.6)
        param_set = identifier.update(s_gap, sync_gap)

        self.assertEqual(param_set.gating_status, "TELEMETRY_GAP")
        cov_after = identifier._ud.get_trace()
        self.assertGreater(cov_after, cov_before)

    def test_invalid_physical_secondary_recovery_preserves_r0(self) -> None:
        """If a1 is outside (0, 1), guard preserves valid R0 and sets R1, C1 to None."""
        guard = ParameterSafetyGuard()

        # a1 = 1.05 (unphysical growth), b0 = 0.025 (valid R0)
        res = guard.validate_and_recover(a1=1.05, b0=0.025, b1=-0.01, dt_s=1.0)

        self.assertTrue(res.is_r0_valid)
        self.assertFalse(res.is_secondary_valid)
        self.assertEqual(res.r0_ohm, 0.025)
        self.assertIsNone(res.r1_ohm)
        self.assertIsNone(res.c1_farad)
        self.assertIn("outside valid interval", res.rejection_reason)


if __name__ == "__main__":
    unittest.main()
