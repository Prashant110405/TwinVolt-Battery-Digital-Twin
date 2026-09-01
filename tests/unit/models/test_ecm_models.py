"""Unit tests for Equivalent Circuit Models (0-RC, 1-RC, 2-RC, N-RC)."""

import math
import unittest

from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import (
    ModelInput,
    ModelMetadata,
)


class TestECMModels(unittest.TestCase):
    """Test suite verifying Equivalent Circuit Model electrical dynamics."""

    def setUp(self) -> None:
        """Create standard test parameters."""
        self.ocv_model = LinearOCVModel(v_min_v=3.0, v_max_v=4.2)
        self.cap_ah = 2.2
        self.v_nom = 3.7

    # --------------------------------------------------------------------------
    # 1. 0-RC (Rint) Model Tests
    # --------------------------------------------------------------------------
    def test_rint_0rc_model_instantaneous_step(self) -> None:
        """0-RC model has instantaneous ohmic voltage drop with no polarization delay."""
        r0_ohm = 0.025  # 25 mOhm
        model = GenericECMModel.create_rint_model(
            model_id="rint_01",
            nominal_capacity_ah=self.cap_ah,
            nominal_voltage_v=self.v_nom,
            r0_ohm=r0_ohm,
            ocv_model=self.ocv_model,
        )

        # Initial state at 100% SOC -> V_oc = 4.2V
        model.initialize(soc_init=1.0, temperature_c=25.0)
        self.assertEqual(model.state.polarization_voltages_v, ())

        # Apply 2.0 A discharge for dt = 1.0 s
        inp = ModelInput(current_a=2.0, dt_s=1.0)
        out = model.step(inp)

        # V_oc at updated SOC after 1s of 2A discharge
        expected_v_oc = self.ocv_model.get_ocv(out.state.soc_fraction, 25.0)
        self.assertAlmostEqual(out.open_circuit_voltage_v, expected_v_oc, places=5)
        self.assertAlmostEqual(out.terminal_voltage_v, expected_v_oc - (2.0 * r0_ohm), places=5)
        self.assertEqual(out.state.polarization_voltages_v, ())

    # --------------------------------------------------------------------------
    # 2. 1-RC Thevenin Model Tests
    # --------------------------------------------------------------------------
    def test_thevenin_1rc_model_transient_and_relaxation(self) -> None:
        """1-RC model demonstrates ohmic jump followed by exponential RC polarization curve."""
        r0_ohm = 0.020  # 20 mOhm
        r1_ohm = 0.010  # 10 mOhm
        c1_f = 1000.0   # 1000 F -> tau = 10.0 s

        model = GenericECMModel.create_thevenin_1rc_model(
            model_id="thevenin_01",
            nominal_capacity_ah=self.cap_ah,
            nominal_voltage_v=self.v_nom,
            r0_ohm=r0_ohm,
            r1_ohm=r1_ohm,
            c1_farad=c1_f,
            ocv_model=self.ocv_model,
        )
        model.initialize(soc_init=1.0, temperature_c=25.0)

        # Step 1: 10 A discharge pulse for 10 s (1 time constant)
        inp_pulse = ModelInput(current_a=10.0, dt_s=10.0)
        out_1 = model.step(inp_pulse)

        # Expected V_rc1 after 1 tau: I * R1 * (1 - exp(-1)) = 10 * 0.01 * 0.63212 = 0.063212 V
        expected_v_rc1 = 10.0 * r1_ohm * (1.0 - math.exp(-1.0))
        self.assertAlmostEqual(out_1.state.polarization_voltages_v[0], expected_v_rc1, places=5)

        # V_oc at new SOC (dSOC = -10*10 / (2.2*3600) = -0.012626)
        expected_v_oc = self.ocv_model.get_ocv(out_1.state.soc_fraction, 25.0)
        expected_v_term = expected_v_oc - (10.0 * r0_ohm) - expected_v_rc1
        self.assertAlmostEqual(out_1.terminal_voltage_v, expected_v_term, places=5)

        # Step 2: Current interruption (Rest: I = 0 A for 10 s)
        inp_rest = ModelInput(current_a=0.0, dt_s=10.0)
        out_2 = model.step(inp_rest)

        # Expected V_rc1 decayed: V_rc1_prev * exp(-1) = expected_v_rc1 * 0.367879
        expected_v_rc1_decay = expected_v_rc1 * math.exp(-1.0)
        self.assertAlmostEqual(out_2.state.polarization_voltages_v[0], expected_v_rc1_decay, places=5)
        self.assertAlmostEqual(out_2.terminal_voltage_v, out_2.open_circuit_voltage_v - expected_v_rc1_decay, places=5)

    # --------------------------------------------------------------------------
    # 3. 2-RC Dual Polarization Model Tests
    # --------------------------------------------------------------------------
    def test_dual_polarization_2rc_model_two_time_constants(self) -> None:
        """2-RC model tracks fast charge transfer and slow diffusion branches independently."""
        model = GenericECMModel.create_dual_polarization_2rc_model(
            model_id="dp_2rc_01",
            nominal_capacity_ah=self.cap_ah,
            nominal_voltage_v=self.v_nom,
            r0_ohm=0.020,
            r1_ohm=0.010,
            c1_farad=500.0,   # tau1 = 5.0 s (fast)
            r2_ohm=0.015,
            c2_farad=2000.0,  # tau2 = 30.0 s (slow)
            ocv_model=self.ocv_model,
        )
        model.initialize(soc_init=0.5, temperature_c=25.0)

        inp = ModelInput(current_a=5.0, dt_s=5.0)
        out = model.step(inp)

        # Verify both branch voltages are present and positive during discharge
        self.assertEqual(len(out.state.polarization_voltages_v), 2)
        v_rc1, v_rc2 = out.state.polarization_voltages_v
        self.assertGreater(v_rc1, 0.0)
        self.assertGreater(v_rc2, 0.0)

        # Branch 1 (tau = 5s, dt = 5s -> 1 tau) reached ~63.2% of steady state (0.05V -> 0.0316V)
        # Branch 2 (tau = 30s, dt = 5s -> 1/6 tau) reached ~15.3% of steady state (0.075V -> 0.0115V)
        self.assertAlmostEqual(v_rc1, 5.0 * 0.010 * (1.0 - math.exp(-1.0)), places=5)
        self.assertAlmostEqual(v_rc2, 5.0 * 0.015 * (1.0 - math.exp(-5.0 / 30.0)), places=5)

    # --------------------------------------------------------------------------
    # 4. Configurable N-RC Model Tests
    # --------------------------------------------------------------------------
    def test_generic_n_rc_model_arbitrary_branches(self) -> None:
        """Verify arbitrary 3-RC configuration."""
        meta = ModelMetadata(model_id="n_rc_3", name="3-RC Model", paradigm="ECM_3RC")
        params = GenericECMParameters(
            nominal_capacity_ah=self.cap_ah,
            nominal_voltage_v=self.v_nom,
            series_resistance_r0_ohm=0.015,
            rc_branches=(
                RCBranchParameters(resistance_r_ohm=0.005, capacitance_c_farad=100.0),
                RCBranchParameters(resistance_r_ohm=0.008, capacitance_c_farad=1000.0),
                RCBranchParameters(resistance_r_ohm=0.012, capacitance_c_farad=5000.0),
            ),
        )
        model = GenericECMModel(metadata=meta, parameters=params, ocv_model=self.ocv_model)
        self.assertEqual(model.ecm_parameters.branch_count, 3)
        self.assertAlmostEqual(model.ecm_parameters.total_dc_resistance_mohm, 40.0, places=3)

        model.initialize(soc_init=0.9, temperature_c=25.0)
        out = model.step(ModelInput(current_a=4.0, dt_s=1.0))
        self.assertEqual(len(out.state.polarization_voltages_v), 3)

    # --------------------------------------------------------------------------
    # 5. Charging Mode & Coulombic Efficiency
    # --------------------------------------------------------------------------
    def test_charging_mode_voltage_rise_and_coulombic_efficiency(self) -> None:
        """During charging (I < 0), terminal voltage rises above Voc and SOC increases."""
        model = GenericECMModel.create_thevenin_1rc_model(
            model_id="thevenin_chg",
            nominal_capacity_ah=self.cap_ah,
            nominal_voltage_v=self.v_nom,
            r0_ohm=0.025,
            r1_ohm=0.015,
            c1_farad=1000.0,
            coulombic_efficiency=0.98,
            ocv_model=self.ocv_model,
        )
        model.initialize(soc_init=0.5, temperature_c=25.0)

        # Apply -2.2 A (1C charge) for 100 s
        inp = ModelInput(current_a=-2.2, dt_s=100.0)
        out = model.step(inp)

        # Terminal voltage must be GREATER than Voc due to charging overpotentials
        self.assertGreater(out.terminal_voltage_v, out.open_circuit_voltage_v)
        self.assertGreater(out.state.soc_fraction, 0.5)


if __name__ == "__main__":
    unittest.main()
