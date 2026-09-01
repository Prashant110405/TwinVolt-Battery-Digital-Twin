"""Unit tests for 0D Lumped Thermal Dynamics Model."""

import math
import unittest

from src.models.exceptions import InvalidModelParametersError, InvalidModelStateError
from src.models.thermal.lumped import LumpedThermalModel


class TestLumpedThermalModel(unittest.TestCase):
    """Test suite verifying 0D lumped thermal dynamics and analytical heat equations."""

    def test_thermal_model_initialization_and_properties(self) -> None:
        """Create LumpedThermalModel and verify computed time constants."""
        # C_th = 50 J/K, hA = 2.0 W/K -> R_th = 0.5 K/W, tau_th = 25.0 s
        model = LumpedThermalModel(
            thermal_capacitance_j_per_k=50.0,
            convective_heat_transfer_w_per_k=2.0,
        )
        self.assertEqual(model.thermal_capacitance_j_per_k, 50.0)
        self.assertEqual(model.convective_heat_transfer_w_per_k, 2.0)
        self.assertEqual(model.thermal_resistance_k_per_w, 0.5)
        self.assertEqual(model.thermal_time_constant_s, 25.0)

        # Alternative init with thermal_resistance_k_per_w
        model2 = LumpedThermalModel(
            thermal_capacitance_j_per_k=100.0,
            thermal_resistance_k_per_w=0.2,
        )
        self.assertEqual(model2.convective_heat_transfer_w_per_k, 5.0)
        self.assertEqual(model2.thermal_time_constant_s, 20.0)

    def test_invalid_parameters_raise(self) -> None:
        """Negative or zero heat capacities or dual specification must raise error."""
        with self.assertRaises(InvalidModelParametersError):
            LumpedThermalModel(thermal_capacitance_j_per_k=0.0)

        with self.assertRaises(InvalidModelParametersError):
            LumpedThermalModel(thermal_capacitance_j_per_k=-10.0)

        with self.assertRaises(InvalidModelParametersError):
            LumpedThermalModel(
                thermal_capacitance_j_per_k=50.0,
                convective_heat_transfer_w_per_k=1.0,
                thermal_resistance_k_per_w=1.0,
            )

    def test_cooling_to_ambient_at_zero_heat(self) -> None:
        """Verify exponential cooling toward ambient temperature when Q_gen = 0."""
        # C_th = 100 J/K, R_th = 1 K/W -> tau = 100 s
        model = LumpedThermalModel(
            thermal_capacitance_j_per_k=100.0,
            thermal_resistance_k_per_w=1.0,
        )
        t_amb = 25.0
        t_init = 45.0  # +20°C above ambient

        # Step 100 seconds (1 tau)
        t_100s = model.step(
            heat_generation_w=0.0,
            dt_s=100.0,
            ambient_temperature_c=t_amb,
            current_temp_c=t_init,
        )

        # Analytical: T(100) = 25 + 20 * exp(-1) = 25 + 20 * 0.367879 = 32.35758°C
        expected_t = t_amb + (20.0 * math.exp(-1.0))
        self.assertAlmostEqual(t_100s, expected_t, places=5)

    def test_heating_under_constant_power(self) -> None:
        """Verify temperature rise under constant heat dissipation."""
        # C_th = 100 J/K, R_th = 2 K/W, Q = 5 W -> Steady state rise = 10°C
        model = LumpedThermalModel(
            thermal_capacitance_j_per_k=100.0,
            thermal_resistance_k_per_w=2.0,
        )
        t_amb = 25.0

        # Step 1000 seconds (5 tau -> reaches 99.3% of steady state)
        t_cur = t_amb
        for _ in range(10):
            t_cur = model.step(
                heat_generation_w=5.0,
                dt_s=100.0,
                ambient_temperature_c=t_amb,
                current_temp_c=t_cur,
            )

        # Steady state = 25 + 5 * 2 = 35°C
        self.assertAlmostEqual(t_cur, 35.0, delta=0.1)

    def test_invalid_temperature_inputs_raise(self) -> None:
        """Temperatures below absolute zero or negative dt must raise errors."""
        model = LumpedThermalModel(thermal_capacitance_j_per_k=50.0)
        with self.assertRaises(ValueError):
            model.step(heat_generation_w=-1.0, dt_s=1.0, ambient_temperature_c=25.0, current_temp_c=25.0)
        with self.assertRaises(ValueError):
            model.step(heat_generation_w=1.0, dt_s=0.0, ambient_temperature_c=25.0, current_temp_c=25.0)
        with self.assertRaises(InvalidModelStateError):
            model.step(heat_generation_w=1.0, dt_s=1.0, ambient_temperature_c=-274.0, current_temp_c=25.0)


if __name__ == "__main__":
    unittest.main()
