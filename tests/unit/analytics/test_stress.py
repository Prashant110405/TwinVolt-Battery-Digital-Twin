"""Unit tests for StressAccumulator and Throughput Integration."""

import unittest
from src.analytics.stress import StressAccumulator
from src.telemetry.enums import TelemetryQuality
from src.telemetry.snapshots import TelemetrySnapshot


class TestStressAccumulator(unittest.TestCase):
    """Test suite verifying cumulative Ah, Wh, EFC integration and timestamp clamping."""

    def test_constant_discharge_integration(self) -> None:
        """Constant positive current accumulates discharge Ah and total throughput."""
        acc = StressAccumulator(nominal_capacity_ah=2.5)

        # 1. First sample at t = 0
        s0 = TelemetrySnapshot(
            system_id="pack_01",
            snapshot_id="snap_00",
            timestamp_ns=0,
            pack_current_a=2.0,
            pack_voltage_v=3.6,
        )
        st0 = acc.update(s0)
        self.assertEqual(st0.total_throughput_ah, 0.0)

        # 2. Step 1 hour later (t = 3600 s) with explicit dt_s = 3600.0 and max_integration_interval_s = 7200.0
        acc_long = StressAccumulator(nominal_capacity_ah=2.5, max_integration_interval_s=7200.0)
        acc_long.update(s0)

        s1 = TelemetrySnapshot(
            system_id="pack_01",
            snapshot_id="snap_01",
            timestamp_ns=3600 * 1_000_000_000,
            pack_current_a=2.0,
            pack_voltage_v=3.6,
        )
        st1 = acc_long.update(s1, dt_s=3600.0)

        # 2.0 A * 1.0 hr = 2.0 Ah
        self.assertAlmostEqual(st1.discharge_throughput_ah, 2.0, places=4)
        self.assertAlmostEqual(st1.charge_throughput_ah, 0.0, places=4)
        self.assertAlmostEqual(st1.total_throughput_ah, 2.0, places=4)
        # Energy = 3.6 V * 2.0 A * 1.0 hr = 7.2 Wh
        self.assertAlmostEqual(st1.energy_throughput_wh, 7.2, places=4)
        # EFC = 2.0 Ah / (2 * 2.5 Ah) = 0.40 EFC
        self.assertAlmostEqual(st1.equivalent_full_cycles, 0.4, places=4)

    def test_constant_charge_integration(self) -> None:
        """Constant negative current accumulates charge Ah and total throughput."""
        acc = StressAccumulator(nominal_capacity_ah=2.0, max_integration_interval_s=7200.0)

        s0 = TelemetrySnapshot(
            system_id="pack_01",
            snapshot_id="snap_00",
            timestamp_ns=0,
            pack_current_a=-1.0,
            pack_voltage_v=3.7,
        )
        acc.update(s0)

        s1 = TelemetrySnapshot(
            system_id="pack_01",
            snapshot_id="snap_01",
            timestamp_ns=3600 * 1_000_000_000,
            pack_current_a=-1.0,
            pack_voltage_v=3.7,
        )
        st1 = acc.update(s1, dt_s=3600.0)

        # 1.0 A * 1 hr = 1.0 Ah charge
        self.assertAlmostEqual(st1.charge_throughput_ah, 1.0, places=4)
        self.assertAlmostEqual(st1.discharge_throughput_ah, 0.0, places=4)
        self.assertAlmostEqual(st1.total_throughput_ah, 1.0, places=4)
        self.assertAlmostEqual(st1.energy_throughput_wh, 3.7, places=4)
        # EFC = 1.0 / (2 * 2.0) = 0.25 EFC
        self.assertAlmostEqual(st1.equivalent_full_cycles, 0.25, places=4)

    def test_duplicate_and_retrograde_timestamps(self) -> None:
        """Duplicate or retrograde timestamps are safely skipped without double-counting."""
        acc = StressAccumulator(nominal_capacity_ah=2.0)

        s0 = TelemetrySnapshot(
            system_id="pack_01",
            snapshot_id="snap_00",
            timestamp_ns=1000,
            pack_current_a=2.0,
        )
        acc.update(s0)

        # Duplicate timestamp
        s_dup = TelemetrySnapshot(
            system_id="pack_01",
            snapshot_id="snap_dup",
            timestamp_ns=1000,
            pack_current_a=2.0,
        )
        st_dup = acc.update(s_dup)
        self.assertEqual(st_dup.total_throughput_ah, 0.0)

        # Retrograde timestamp
        s_retro = TelemetrySnapshot(
            system_id="pack_01",
            snapshot_id="snap_retro",
            timestamp_ns=500,
            pack_current_a=2.0,
        )
        st_retro = acc.update(s_retro)
        self.assertEqual(st_retro.total_throughput_ah, 0.0)

    def test_max_dt_clamping(self) -> None:
        """Large gaps in telemetry timestamps are clamped to max_integration_interval_s."""
        acc = StressAccumulator(nominal_capacity_ah=2.0, max_integration_interval_s=10.0)

        s0 = TelemetrySnapshot(
            system_id="pack_01",
            snapshot_id="snap_00",
            timestamp_ns=0,
            pack_current_a=3.6,
        )
        acc.update(s0)

        # Gap of 1000 seconds -> clamped to 10.0s
        s1 = TelemetrySnapshot(
            system_id="pack_01",
            snapshot_id="snap_01",
            timestamp_ns=1000 * 1_000_000_000,
            pack_current_a=3.6,
        )
        st1 = acc.update(s1)

        # Clamped dt = 10.0 s -> delta_ah = 3.6 A * 10 s / 3600 = 0.01 Ah
        self.assertAlmostEqual(st1.total_throughput_ah, 0.01, places=4)
        self.assertAlmostEqual(st1.total_elapsed_time_s, 10.0, places=2)

    def test_invalid_telemetry_skipped(self) -> None:
        """Telemetry flagged as INVALID does not accumulate stress."""
        acc = StressAccumulator(nominal_capacity_ah=2.0)

        s_bad = TelemetrySnapshot(
            system_id="pack_01",
            snapshot_id="snap_bad",
            timestamp_ns=1_000_000_000,
            pack_current_a=100.0,
            quality=TelemetryQuality.INVALID,
        )
        st = acc.update(s_bad)
        self.assertEqual(st.total_throughput_ah, 0.0)
        self.assertEqual(st.sample_count, 0)

    def test_zero_nominal_capacity_efc(self) -> None:
        """Zero nominal capacity avoids ZeroDivisionError and sets EFC to 0.0."""
        acc = StressAccumulator(nominal_capacity_ah=0.0)
        st = acc.get_state()
        self.assertEqual(st.equivalent_full_cycles, 0.0)

    def test_monotonic_throughput(self) -> None:
        """Cumulative throughput counters are strictly monotonic non-decreasing."""
        acc = StressAccumulator(nominal_capacity_ah=2.0)
        prev_ah = 0.0

        for i in range(10):
            s = TelemetrySnapshot(
                system_id="pack_01",
                snapshot_id=f"snap_{i}",
                timestamp_ns=(i + 1) * 1_000_000_000,
                pack_current_a=1.5 if i % 2 == 0 else -1.5,
            )
            st = acc.update(s, dt_s=1.0)
            self.assertGreaterEqual(st.total_throughput_ah, prev_ah)
            prev_ah = st.total_throughput_ah


if __name__ == "__main__":
    unittest.main()
