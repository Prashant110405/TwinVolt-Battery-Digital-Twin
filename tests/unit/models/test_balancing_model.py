"""Unit tests for Passive Dissipative Cell Balancing Model."""

import unittest

from src.models.aggregator.balancing_model import (
    PassiveBalancingConfig,
    PassiveBalancingModel,
)
from src.models.exceptions import InvalidModelParametersError, InvalidModelStateError


class TestPassiveBalancingModel(unittest.TestCase):
    """Test suite verifying balancing threshold evaluation, bleed current calculation, and heat dissipation."""

    def setUp(self) -> None:
        """Create balancing model with custom test thresholds."""
        self.config = PassiveBalancingConfig(
            bleed_resistance_ohm=33.0,
            voltage_threshold_v=3.50,
            voltage_delta_threshold_v=0.020,  # 20 mV threshold
            max_balancing_current_a=0.15,
            enabled=True,
        )
        self.bm = PassiveBalancingModel(self.config)

    def test_default_initialization(self) -> None:
        """Verify default configuration values."""
        default_bm = PassiveBalancingModel()
        self.assertEqual(default_bm.config.bleed_resistance_ohm, 33.0)
        self.assertEqual(default_bm.config.voltage_threshold_v, 3.40)
        self.assertTrue(default_bm.config.enabled)

    def test_no_balancing_below_absolute_voltage_threshold(self) -> None:
        """Cells below 3.50 V must not balance even if delta V is large."""
        # Voltages: [3.40, 3.45, 3.48] -> Delta = 80 mV, but all are < 3.50 V
        currents = self.bm.compute_balancing_currents([3.40, 3.45, 3.48])
        self.assertEqual(currents, (0.0, 0.0, 0.0))

    def test_no_balancing_below_delta_threshold(self) -> None:
        """Cells above 3.50 V but within 20 mV delta must not balance."""
        # Voltages: [3.60, 3.61, 3.615] -> min=3.60, max_delta=15 mV < 20 mV
        currents = self.bm.compute_balancing_currents([3.60, 3.61, 3.615])
        self.assertEqual(currents, (0.0, 0.0, 0.0))

    def test_active_balancing_on_deviant_cells(self) -> None:
        """Deviant high cell triggers bleed current clamped by max limiter."""
        # Voltages: [3.50, 3.51, 3.60] -> min=3.50. Cell 3 has delta=100 mV >= 20 mV, V=3.60 >= 3.50
        # Expected I_bleed for Cell 3: 3.60 / 33.0 = 0.109 A (below 0.15 A max)
        currents = self.bm.compute_balancing_currents([3.50, 3.51, 3.60])
        self.assertEqual(currents[0], 0.0)
        self.assertEqual(currents[1], 0.0)
        self.assertAlmostEqual(currents[2], 3.60 / 33.0, places=4)

    def test_balancing_heat_dissipation(self) -> None:
        """Verify thermal power dissipation P = V * I_bleed."""
        voltages = [3.50, 3.60]
        currents = self.bm.compute_balancing_currents(voltages)
        heat_w = self.bm.compute_balancing_heat_w(voltages, currents)

        self.assertEqual(heat_w[0], 0.0)
        expected_p = 3.60 * (3.60 / 33.0)
        self.assertAlmostEqual(heat_w[1], expected_p, places=4)

    def test_disabled_balancing_toggle(self) -> None:
        """When disabled=False, all currents must be zero."""
        cfg_disabled = PassiveBalancingConfig(enabled=False)
        bm_disabled = PassiveBalancingModel(cfg_disabled)
        currents = bm_disabled.compute_balancing_currents([3.50, 3.70, 3.90])
        self.assertEqual(currents, (0.0, 0.0, 0.0))

    def test_invalid_configurations_and_voltages(self) -> None:
        """Test parameter validation against non-physical inputs."""
        with self.assertRaises(InvalidModelParametersError):
            PassiveBalancingConfig(bleed_resistance_ohm=0.0)

        with self.assertRaises(InvalidModelParametersError):
            PassiveBalancingConfig(voltage_threshold_v=-1.0)

        with self.assertRaises(InvalidModelStateError):
            self.bm.compute_balancing_currents([3.7, -0.5])


if __name__ == "__main__":
    unittest.main()
