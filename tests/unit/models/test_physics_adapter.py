"""Unit tests for Physics-Based Electrochemical Model Backend and PyBaMM Adapter."""

import unittest

from src.models.base import BatteryModel
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.exceptions import InvalidModelParametersError
from src.models.physics.base import PhysicsModelBackend
from src.models.physics.parameters import PhysicsModelParameters
from src.models.physics.pybamm_adapter import (
    PyBaMMModelAdapter,
    PyBaMMNativeBackend,
    SimulatedPhysicsBackend,
)
from src.models.types import ModelInput, ModelMetadata


class TestPhysicsModelAdapter(unittest.TestCase):
    """Test suite verifying physics model abstractions, PyBaMM adapter, and hot-swappability."""

    # --------------------------------------------------------------------------
    # 1. PhysicsModelParameters Tests
    # --------------------------------------------------------------------------
    def test_valid_physics_parameters(self) -> None:
        """Create valid PhysicsModelParameters across SPM, SPMe, and DFN."""
        params_spm = PhysicsModelParameters(
            nominal_capacity_ah=2.2,
            nominal_voltage_v=3.7,
            model_type="SPM",
            parameter_set_name="Chen2020",
            electrode_area_m2=0.05,
        )
        self.assertEqual(params_spm.model_type, "SPM")
        self.assertEqual(params_spm.parameter_set_name, "Chen2020")
        self.assertEqual(params_spm.electrode_area_m2, 0.05)

        params_dfn = PhysicsModelParameters(
            nominal_capacity_ah=50.0,
            nominal_voltage_v=3.2,
            model_type="DFN",
            parameter_set_name="Prada2013",
        )
        self.assertEqual(params_dfn.model_type, "DFN")

    def test_invalid_physics_parameters_raise(self) -> None:
        """Unknown model type or empty parameter set name must fail."""
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(
                nominal_capacity_ah=2.2,
                nominal_voltage_v=3.7,
                model_type="QUANTUM_TELEPORTATION_SOLVER",
            )

        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(
                nominal_capacity_ah=2.2,
                nominal_voltage_v=3.7,
                parameter_set_name="",
            )

    # --------------------------------------------------------------------------
    # 2. SimulatedPhysicsBackend Tests
    # --------------------------------------------------------------------------
    def test_simulated_physics_backend_execution(self) -> None:
        """Verify simulated electrochemical backend returns valid physics variables."""
        backend = SimulatedPhysicsBackend(model_type="SPM")
        adapter = PyBaMMModelAdapter.create_spm_adapter(
            model_id="spm_sim_01",
            nominal_capacity_ah=2.2,
            nominal_voltage_v=3.7,
            backend=backend,
        )

        adapter.initialize(soc_init=0.9, temperature_c=25.0)
        self.assertEqual(adapter.state.soc_fraction, 0.9)

        # Step 2.0 A discharge for dt = 1.0 s
        inp = ModelInput(current_a=2.0, dt_s=1.0, ambient_temperature_c=25.0)
        out = adapter.step(inp)

        self.assertLess(out.state.soc_fraction, 0.9)
        self.assertGreater(out.terminal_voltage_v, 3.0)
        self.assertIn("c_s_pos_surface", out.state.custom_states)
        self.assertIn("c_s_neg_surface", out.state.custom_states)
        self.assertIn("eta_reaction_v", out.state.custom_states)

    # --------------------------------------------------------------------------
    # 3. Protocol Compliance & Model Hot-Swappability
    # --------------------------------------------------------------------------
    def test_battery_model_protocol_compliance_and_hot_swapping(self) -> None:
        """Demonstrate that ECM and Physics adapters adhere identically to BatteryModel."""
        ecm_model = GenericECMModel.create_thevenin_1rc_model("ecm_test", 2.2, 3.7)
        physics_model = PyBaMMModelAdapter.create_spm_adapter("spm_test", 2.2, 3.7)

        # Both must satisfy BatteryModel protocol
        self.assertIsInstance(ecm_model, BatteryModel)
        self.assertIsInstance(physics_model, BatteryModel)

        # Uniform simulation loop hot-swapping across different model paradigms
        models: list[BatteryModel] = [ecm_model, physics_model]
        inp = ModelInput(current_a=1.5, dt_s=0.5, ambient_temperature_c=25.0)

        for m in models:
            m.initialize(soc_init=0.8, temperature_c=25.0)
            out = m.step(inp)
            self.assertIsInstance(out.terminal_voltage_v, float)
            self.assertIsInstance(out.open_circuit_voltage_v, float)
            self.assertGreater(out.terminal_voltage_v, 2.5)
            self.assertLessEqual(out.state.soc_fraction, 0.8)

    # --------------------------------------------------------------------------
    # 4. Native PyBaMM Solver Integration
    # --------------------------------------------------------------------------
    def test_native_pybamm_adapter_creation_and_step(self) -> None:
        """Verify native PyBaMM DFN and SPM adapter creation."""
        spm_adapter = PyBaMMModelAdapter.create_spm_adapter(
            model_id="pybamm_spm_native",
            nominal_capacity_ah=2.2,
            nominal_voltage_v=3.7,
            parameter_set_name="Chen2020",
        )
        self.assertIsInstance(spm_adapter.backend, PhysicsModelBackend)
        spm_adapter.initialize(soc_init=0.85, temperature_c=25.0)

        out = spm_adapter.step(ModelInput(current_a=2.0, dt_s=1.0))
        self.assertGreater(out.terminal_voltage_v, 3.0)
        self.assertLess(out.state.soc_fraction, 0.85)

        dfn_adapter = PyBaMMModelAdapter.create_dfn_adapter(
            model_id="pybamm_dfn_native",
            nominal_capacity_ah=2.2,
            nominal_voltage_v=3.7,
        )
        dfn_adapter.initialize(soc_init=0.8, temperature_c=25.0)
        out_dfn = dfn_adapter.step(ModelInput(current_a=1.0, dt_s=1.0))
        self.assertGreater(out_dfn.terminal_voltage_v, 3.0)


if __name__ == "__main__":
    unittest.main()
