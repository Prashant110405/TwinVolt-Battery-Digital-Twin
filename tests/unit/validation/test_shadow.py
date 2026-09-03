"""Unit tests for ProspectiveECMBranchSimulator, initial polarization state fairness, and immutability."""

import math
import unittest

from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelInput, ModelMetadata
from src.validation.shadow import ProspectiveECMBranchSimulator


class TestProspectiveECMBranchSimulator(unittest.TestCase):
    """Test suite verifying isolated shadow 1-RC simulation, initial state fairness, and live model immutability."""

    def test_exact_1_rc_recurrence_simulation(self) -> None:
        """Verifies exact analytical polarization recurrence and terminal voltage calculation."""
        sim = ProspectiveECMBranchSimulator()
        r0 = 0.025
        r1 = 0.015
        c1 = 1000.0
        dt = 1.0
        v_oc = 3.8
        tau = r1 * c1  # 15.0 s
        decay = math.exp(-dt / tau)

        # Step 1 with 0 initial polarization: initial current 4.0 A
        # Vp[1] = (0.0 * decay) + 4.0 * r1 * (1 - decay)
        v1 = sim.step(v_oc=v_oc, current_a=4.0, dt_s=dt, r0_ohm=r0, r1_ohm=r1, c1_farad=c1, initial_polarization_v=0.0)
        expected_vp1 = 4.0 * r1 * (1.0 - decay)
        expected_v1 = v_oc - (4.0 * r0) - expected_vp1
        self.assertAlmostEqual(v1, expected_v1, places=6)
        self.assertAlmostEqual(sim.polarization_voltage_v, expected_vp1, places=6)

        # Step 2: current 4.0 A
        v2 = sim.step(v_oc=v_oc, current_a=4.0, dt_s=dt, r0_ohm=r0, r1_ohm=r1, c1_farad=c1)
        expected_vp2 = (expected_vp1 * decay) + 4.0 * r1 * (1.0 - decay)
        expected_v2 = v_oc - (4.0 * r0) - expected_vp2
        self.assertAlmostEqual(v2, expected_v2, places=6)
        self.assertAlmostEqual(sim.polarization_voltage_v, expected_vp2, places=6)

    def test_initial_polarization_state_parity_with_nominal_model(self) -> None:
        """Verifies that prospective shadow simulation accurately inherits non-zero nominal initial polarization."""
        nominal_init_vp = 0.045  # 45 mV existing polarization
        sim = ProspectiveECMBranchSimulator()

        r0 = 0.025
        r1 = 0.015
        c1 = 1000.0
        dt = 1.0
        v_oc = 3.8
        i_k = 2.0
        tau = r1 * c1
        decay = math.exp(-dt / tau)

        # Step with non-zero initial polarization
        v_term = sim.step(
            v_oc=v_oc,
            current_a=i_k,
            dt_s=dt,
            r0_ohm=r0,
            r1_ohm=r1,
            c1_farad=c1,
            initial_polarization_v=nominal_init_vp,
        )

        expected_vp = (nominal_init_vp * decay) + (i_k * r1 * (1.0 - decay))
        expected_vterm = v_oc - (i_k * r0) - expected_vp

        self.assertAlmostEqual(sim.polarization_voltage_v, expected_vp, places=6)
        self.assertAlmostEqual(v_term, expected_vterm, places=6)

    def test_live_model_immutability_verification(self) -> None:
        """CRITICAL: Verifies that shadow simulation leaves live GenericECMModel parameters and state untouched."""
        nominal_params = GenericECMParameters(
            nominal_capacity_ah=2.5,
            nominal_voltage_v=3.6,
            series_resistance_r0_ohm=0.025,
            rc_branches=(RCBranchParameters(resistance_r_ohm=0.015, capacitance_c_farad=1000.0),),
        )
        live_model = GenericECMModel(
            metadata=ModelMetadata(model_id="live_ecm", name="LiveECM", paradigm="ECM"),
            parameters=nominal_params,
            ocv_model=LinearOCVModel(v_min_v=2.8, v_max_v=4.2),
        )
        live_model.initialize(soc_init=0.8, temperature_c=25.0)

        # Step live model once
        model_out = live_model.step(ModelInput(current_a=3.0, dt_s=1.0, ambient_temperature_c=25.0))
        live_vp_before = model_out.state.polarization_voltages_v[0]

        # Candidate parameters that differ significantly
        candidate_r0 = 0.045
        candidate_r1 = 0.030
        candidate_c1 = 1500.0

        sim = ProspectiveECMBranchSimulator()
        for _ in range(10):
            sim.step(
                v_oc=model_out.open_circuit_voltage_v,
                current_a=3.0,
                dt_s=1.0,
                r0_ohm=candidate_r0,
                r1_ohm=candidate_r1,
                c1_farad=candidate_c1,
                initial_polarization_v=live_vp_before,
            )

        # Verify live model parameters were NOT mutated in-place
        self.assertEqual(live_model.ecm_parameters.series_resistance_r0_ohm, 0.025)
        self.assertEqual(live_model.ecm_parameters.rc_branches[0].resistance_r_ohm, 0.015)
        self.assertEqual(live_model.ecm_parameters.rc_branches[0].capacitance_c_farad, 1000.0)

    def test_changing_candidate_parameters_alters_prospective_voltage_not_initial_condition(self) -> None:
        """Verifies candidate parameters alter terminal voltage prediction while preserving initial state."""
        init_vp = 0.020
        v_oc = 3.8
        dt = 1.0
        i_k = 2.0

        # Candidate A: standard R0
        sim_a = ProspectiveECMBranchSimulator()
        v_a = sim_a.step(v_oc=v_oc, current_a=i_k, dt_s=dt, r0_ohm=0.025, r1_ohm=0.015, c1_farad=1000.0, initial_polarization_v=init_vp)

        # Candidate B: double R0
        sim_b = ProspectiveECMBranchSimulator()
        v_b = sim_b.step(v_oc=v_oc, current_a=i_k, dt_s=dt, r0_ohm=0.050, r1_ohm=0.015, c1_farad=1000.0, initial_polarization_v=init_vp)

        # Both began from identical initial conditions, but v_b has additional (2.0 * 0.025) = 0.050 V drop
        self.assertAlmostEqual(v_a - v_b, 0.050, places=6)

    def test_reset_behavior(self) -> None:
        """Reset clears internal polarization voltage and initialization state."""
        sim = ProspectiveECMBranchSimulator()
        sim.step(v_oc=3.8, current_a=5.0, dt_s=1.0, r0_ohm=0.025, r1_ohm=0.015, c1_farad=1000.0)
        self.assertTrue(sim.is_initialized)
        self.assertGreater(sim.polarization_voltage_v, 0.0)

        sim.reset()
        self.assertFalse(sim.is_initialized)
        self.assertEqual(sim.polarization_voltage_v, 0.0)


if __name__ == "__main__":
    unittest.main()
