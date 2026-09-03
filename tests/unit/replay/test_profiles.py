"""Unit tests for DriveCycleProfile and standard profile generators."""

import unittest

from src.replay.exceptions import InvalidProfileError
from src.replay.profiles import (
    DriveCycleProfile,
    ProfilePoint,
    create_constant_current_profile,
    create_dst_profile,
    create_pulse_discharge_profile,
    create_us06_profile,
    create_wltp_class3_profile,
)


class TestDriveCycleProfiles(unittest.TestCase):
    """Test suite verifying drive cycle profile generation, interpolation, and snapshot conversion."""

    def test_constant_current_profile_generation(self) -> None:
        """Constant current profile generates correctly spaced time-series points."""
        prof = create_constant_current_profile(
            duration_s=100.0,
            current_a=5.0,
            dt_s=1.0,
            ambient_temp_c=25.0,
        )
        self.assertEqual(prof.sample_count, 101)
        self.assertEqual(prof.duration_s, 100.0)
        self.assertEqual(prof.peak_discharge_current_a, 5.0)
        self.assertEqual(prof.peak_charge_current_a, 0.0)
        self.assertEqual(prof.points[0].time_s, 0.0)
        self.assertEqual(prof.points[-1].time_s, 100.0)
        self.assertTrue(all(p.current_a == 5.0 for p in prof.points))

    def test_pulse_discharge_profile_generation(self) -> None:
        """Pulse discharge profile generates alternating active and resting phases."""
        prof = create_pulse_discharge_profile(
            pulse_current_a=10.0,
            rest_current_a=0.0,
            pulse_duration_s=5.0,
            rest_duration_s=10.0,
            cycles=3,
            dt_s=1.0,
        )
        self.assertEqual(prof.duration_s, 45.0)  # 3 * 15s = 45s
        self.assertEqual(prof.peak_discharge_current_a, 10.0)
        self.assertEqual(prof.points[0].current_a, 10.0)
        self.assertEqual(prof.points[5].current_a, 0.0)

    def test_wltp_class3_profile_generation(self) -> None:
        """WLTP Class 3 profile includes dynamic discharge and regenerative braking."""
        prof = create_wltp_class3_profile(
            peak_current_a=50.0,
            time_scale_s=1800.0,
            dt_s=1.0,
        )
        self.assertEqual(prof.duration_s, 1800.0)
        self.assertEqual(prof.sample_count, 1801)
        self.assertAlmostEqual(prof.peak_discharge_current_a, 50.0, places=1)
        self.assertLess(prof.peak_charge_current_a, 0.0)  # Contains regenerative charge

    def test_us06_aggressive_profile_generation(self) -> None:
        """US06 profile produces high acceleration transients and regen."""
        prof = create_us06_profile(
            peak_current_a=80.0,
            time_scale_s=600.0,
            dt_s=1.0,
        )
        self.assertEqual(prof.duration_s, 600.0)
        self.assertEqual(prof.sample_count, 601)
        self.assertGreaterEqual(prof.peak_discharge_current_a, 75.0)
        self.assertLess(prof.peak_charge_current_a, 0.0)

    def test_dst_dynamic_stress_test_profile(self) -> None:
        """DST profile generates standard 360-second power schedule across cycles."""
        prof = create_dst_profile(
            peak_discharge_a=40.0,
            regenerative_charge_a=-20.0,
            cycles=2,
            dt_s=1.0,
        )
        self.assertEqual(prof.duration_s, 720.0)  # 2 * 360s = 720s
        self.assertEqual(prof.peak_discharge_current_a, 40.0)
        self.assertEqual(prof.peak_charge_current_a, -10.0)

    def test_to_snapshots_direct_and_resampled(self) -> None:
        """Profile materializes canonical TelemetrySnapshot instances with and without resampling."""
        prof = create_constant_current_profile(duration_s=10.0, current_a=2.0, dt_s=2.0)
        # 1. Direct 1:1 mapping (dt = 2.0s -> 6 points)
        snaps = prof.to_snapshots(system_id="pack_test", start_timestamp_ns=1_000_000_000)
        self.assertEqual(len(snaps), 6)
        self.assertEqual(snaps[0].system_id, "pack_test")
        self.assertEqual(snaps[0].pack_current_a, 2.0)
        self.assertEqual(snaps[1].timestamp_ns, 3_000_000_000)  # +2.0s

        # 2. Resampled at 1.0s interval -> 11 snapshots
        resampled_snaps = prof.to_snapshots(
            system_id="pack_test",
            start_timestamp_ns=1_000_000_000,
            sample_interval_s=1.0,
        )
        self.assertEqual(len(resampled_snaps), 11)
        self.assertEqual(resampled_snaps[1].timestamp_ns, 2_000_000_000)  # +1.0s

    def test_profile_point_validation(self) -> None:
        """ProfilePoint validates physical constraints and non-negative time."""
        with self.assertRaises(InvalidProfileError):
            ProfilePoint(time_s=-1.0, current_a=5.0)

        with self.assertRaises(InvalidProfileError):
            ProfilePoint(time_s=0.0, current_a=5.0, ambient_temperature_c=-300.0)

        with self.assertRaises(InvalidProfileError):
            ProfilePoint(time_s=0.0, current_a=5.0, voltage_v=-3.0)

        with self.assertRaises(InvalidProfileError):
            ProfilePoint(time_s=0.0, current_a=5.0, soc_fraction=1.5)

    def test_profile_non_monotonic_points_rejected(self) -> None:
        """DriveCycleProfile rejects non-monotonic timestamps."""
        p1 = ProfilePoint(time_s=0.0, current_a=1.0)
        p2 = ProfilePoint(time_s=2.0, current_a=1.0)
        p3_bad = ProfilePoint(time_s=1.0, current_a=1.0)  # Backward

        with self.assertRaises(InvalidProfileError):
            DriveCycleProfile(name="bad_prof", points=(p1, p2, p3_bad))

    def test_profile_generators_reject_invalid_parameters(self) -> None:
        """Profile generator functions reject invalid durations and time steps."""
        with self.assertRaises(InvalidProfileError):
            create_constant_current_profile(duration_s=0.0, current_a=1.0)

        with self.assertRaises(InvalidProfileError):
            create_constant_current_profile(duration_s=10.0, current_a=1.0, dt_s=-1.0)

        with self.assertRaises(InvalidProfileError):
            create_wltp_class3_profile(peak_current_a=-5.0)

        with self.assertRaises(InvalidProfileError):
            create_dst_profile(peak_discharge_a=10.0, regenerative_charge_a=5.0)  # Must be negative


if __name__ == "__main__":
    unittest.main()
