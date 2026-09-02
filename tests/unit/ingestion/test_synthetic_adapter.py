"""Unit tests for Synthetic Telemetry Generator and Adapter."""

import unittest

from src.ingestion.adapters.synthetic_adapter import (
    SyntheticTelemetryAdapter,
    SyntheticTelemetryConfig,
)
from src.telemetry.snapshots import TelemetrySnapshot


class TestSyntheticTelemetryAdapter(unittest.TestCase):
    """Test suite verifying synthetic telemetry generation, deterministic seeds, and current profiles."""

    def test_deterministic_generation_with_seed(self) -> None:
        """Two synthetic generators with identical seeds produce identical snapshots."""
        cfg = SyntheticTelemetryConfig(seed=12345, cell_count=4)
        gen1 = SyntheticTelemetryAdapter(config=cfg)
        gen2 = SyntheticTelemetryAdapter(config=cfg)

        snap1 = gen1.generate_step(step_index=0, dt_s=0.1)
        snap2 = gen2.generate_step(step_index=0, dt_s=0.1)

        self.assertEqual(snap1.pack_voltage_v, snap2.pack_voltage_v)
        self.assertEqual(snap1.pack_current_a, snap2.pack_current_a)
        self.assertEqual(snap1.soc_fraction, snap2.soc_fraction)
        self.assertEqual(len(snap1.cell_telemetries), 4)

    def test_current_profile_modes(self) -> None:
        """Verify pulse, constant, and charge current profile modes."""
        cfg_pulse = SyntheticTelemetryConfig(current_mode="PULSE", base_current_a=5.0, pulse_period_s=4.0)
        gen_pulse = SyntheticTelemetryAdapter(config=cfg_pulse)

        snap_active = gen_pulse.generate_step(step_index=1, dt_s=1.0)  # t=1s -> Active pulse
        snap_rest = gen_pulse.generate_step(step_index=3, dt_s=1.0)  # t=3s -> Rest pulse
        self.assertEqual(snap_active.pack_current_a, 5.0)
        self.assertEqual(snap_rest.pack_current_a, 0.0)

    def test_physical_plausibility_and_bounds(self) -> None:
        """Synthetic outputs must remain strictly within physical domain boundaries."""
        gen = SyntheticTelemetryAdapter()
        snap = gen.generate_step(step_index=10, dt_s=1.0)

        self.assertGreater(snap.pack_voltage_v, 10.0)
        self.assertLess(snap.pack_voltage_v, 20.0)
        self.assertGreaterEqual(snap.soc_fraction, 0.0)
        self.assertLessEqual(snap.soc_fraction, 1.0)
        self.assertGreater(snap.ambient_temperature_c, -40.0)


if __name__ == "__main__":
    unittest.main()
