"""Unit tests for Coupled Electro-Thermal Dynamics and Energy Balance."""

import unittest

from src.models.ecm.generic_ecm import GenericECMModel
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.thermal.lumped import LumpedThermalModel
from src.models.types import ModelInput


class TestElectroThermalCoupling(unittest.TestCase):
    """Test suite verifying coupled electrical losses, heat dissipation, and energy conservation."""

    def setUp(self) -> None:
        """Create standard electro-thermal test model."""
        self.ocv = LinearOCVModel(v_min_v=3.0, v_max_v=4.2, d_ocv_d_temp_v_per_k=0.0002)
        self.model = GenericECMModel.create_thevenin_1rc_model(
            model_id="coupled_1rc",
            nominal_capacity_ah=2.2,
            nominal_voltage_v=3.7,
            r0_ohm=0.025,
            r1_ohm=0.015,
            c1_farad=1200.0,
            ocv_model=self.ocv,
        )

    def test_coupled_heating_under_heavy_discharge_and_rest_cooling(self) -> None:
        """Heavy discharge causes thermal rise; subsequent rest causes cooling back toward ambient."""
        self.model.initialize(soc_init=0.9, temperature_c=25.0)

        # 1. 200 seconds of 5.0 A discharge
        inp_discharge = ModelInput(current_a=5.0, dt_s=1.0, ambient_temperature_c=25.0)
        for _ in range(200):
            out = self.model.step(inp_discharge)

        t_heated = out.state.temperature_c
        self.assertGreater(t_heated, 25.0, "Cell temperature should rise during heavy discharge.")
        self.assertGreater(out.heat_generation_w, 0.5, "Heat generation rate should be significant.")

        # 2. 500 seconds of rest (I = 0.0 A)
        inp_rest = ModelInput(current_a=0.0, dt_s=1.0, ambient_temperature_c=25.0)
        for _ in range(500):
            out = self.model.step(inp_rest)

        t_cooled = out.state.temperature_c
        self.assertLess(t_cooled, t_heated, "Cell temperature should decay toward ambient during rest.")
        self.assertAlmostEqual(out.heat_generation_w, 0.0, places=4, msg="Heat generation at rest must be zero.")

    def test_heat_generation_scales_quadratically_with_current(self) -> None:
        """Joule heating rate scales quadratically with current (I^2 * R0)."""
        pure_joule_model = GenericECMModel.create_rint_model(
            model_id="rint_joule",
            nominal_capacity_ah=2.2,
            nominal_voltage_v=3.7,
            r0_ohm=0.025,
            ocv_model=LinearOCVModel(v_min_v=3.0, v_max_v=4.2, d_ocv_d_temp_v_per_k=0.0),
        )

        pure_joule_model.initialize(soc_init=0.8, temperature_c=25.0)
        out_1a = pure_joule_model.step(ModelInput(current_a=1.0, dt_s=1.0))

        pure_joule_model.initialize(soc_init=0.8, temperature_c=25.0)
        out_2a = pure_joule_model.step(ModelInput(current_a=2.0, dt_s=1.0))

        # Q_1A = 1^2 * 0.025 = 0.025 W, Q_2A = 2^2 * 0.025 = 0.100 W (Ratio = exactly 4.0)
        self.assertAlmostEqual(out_1a.heat_generation_w, 0.025, places=5)
        self.assertAlmostEqual(out_2a.heat_generation_w, 0.100, places=5)
        self.assertAlmostEqual(out_2a.heat_generation_w / out_1a.heat_generation_w, 4.0, places=5)

    def test_electrical_power_loss_and_conservation(self) -> None:
        """P_loss = P_ocv - P_terminal >= 0 during discharge."""
        self.model.initialize(soc_init=0.7, temperature_c=25.0)
        inp = ModelInput(current_a=4.0, dt_s=1.0)
        out = self.model.step(inp)

        p_ocv = out.open_circuit_voltage_v * inp.current_a
        p_terminal = out.terminal_voltage_v * inp.current_a
        p_loss = p_ocv - p_terminal

        self.assertGreater(p_loss, 0.0, "Electrical internal loss must be strictly positive during discharge.")
        self.assertAlmostEqual(out.internal_resistance_mohm, 40.0, places=2)

    def test_deterministic_multi_step_simulation(self) -> None:
        """Two identical 50-step simulation runs produce bitwise identical trajectories."""
        steps = [
            ModelInput(current_a=2.0 if (i % 10 < 7) else -1.0, dt_s=0.5, ambient_temperature_c=25.0)
            for i in range(50)
        ]

        # Run 1
        self.model.initialize(soc_init=0.8, temperature_c=25.0)
        traj_1 = [self.model.step(inp).terminal_voltage_v for inp in steps]

        # Run 2
        self.model.initialize(soc_init=0.8, temperature_c=25.0)
        traj_2 = [self.model.step(inp).terminal_voltage_v for inp in steps]

        self.assertEqual(traj_1, traj_2, "Simulation trajectory must be 100% deterministic.")


if __name__ == "__main__":
    unittest.main()
