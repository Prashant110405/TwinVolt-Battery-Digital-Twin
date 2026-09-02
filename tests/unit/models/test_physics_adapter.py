"""Unit tests for Physics-Based Electrochemical Model Backend and Adapters."""

import math
from typing import Any, Mapping, Optional, Union
import unittest

from src.models.base import BatteryModel
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.exceptions import (
    InvalidModelInputError,
    InvalidModelParametersError,
    InvalidModelStateError,
    ModelEvaluationError,
    NumericalInstabilityError,
    UnphysicalStateError,
)
from src.models.physics.base import (
    AbstractPhysicsBackend,
    PhysicsModelBackend,
    PhysicsStepResult,
)
from src.models.physics.parameters import (
    SUPPORTED_PHYSICS_MODELS,
    SUPPORTED_THERMAL_COUPLINGS,
    PhysicsModelParameters,
)
from src.models.physics.physics_adapter import PhysicsModelAdapter
from src.models.physics.pybamm_adapter import (
    PyBaMMModelAdapter,
    PyBaMMNativeBackend,
    SimulatedPhysicsBackend,
)
from src.models.thermal.lumped import LumpedThermalModel
from src.models.types import (
    ModelInput,
    ModelMetadata,
    ModelOutput,
    ModelParameters,
    ModelState,
)
from src.physics import (
    PhysicsModelAdapter as TopLevelPhysicsAdapter,
    PhysicsModelBackend as TopLevelPhysicsBackend,
    PhysicsModelParameters as TopLevelPhysicsParams,
)


class DummyCustomBackend(AbstractPhysicsBackend):
    """Custom physics backend implementation for testing lifecycle and contracts."""

    def __init__(self, backend_name: str = "DummyBackend") -> None:
        super().__init__(backend_name=backend_name)
        self.reset_count = 0

    def initialize_solver(
        self,
        parameters: ModelParameters,
        initial_soc: float,
        initial_temp_c: float,
        **kwargs: Any,
    ) -> None:
        self._is_initialized = True

    def step_simulation(
        self,
        current_a: float,
        dt_s: float,
        ambient_temp_c: float,
        current_state: ModelState,
    ) -> PhysicsStepResult:
        soc_next = max(0.0, min(1.0, current_state.soc_fraction - (current_a * dt_s / 3600.0)))
        v_oc = 3.6 + (soc_next * 0.5)
        v_term = v_oc - (current_a * 0.030)
        q_gen = (current_a ** 2) * 0.030
        temp_next = current_state.temperature_c + (q_gen * dt_s / 50.0)

        return PhysicsStepResult(
            terminal_voltage_v=v_term,
            open_circuit_voltage_v=v_oc,
            soc_fraction=soc_next,
            temperature_c=temp_next,
            custom_states={"dummy_flux": 1.23},
            heat_generation_w=q_gen,
            internal_resistance_mohm=30.0,
        )

    def reset(self) -> None:
        self._is_initialized = False
        self.reset_count += 1


class FaultyPhysicsBackend(AbstractPhysicsBackend):
    """Backend engineered to trigger failure modes and invariant violations."""

    def __init__(self, failure_mode: str = "crash") -> None:
        super().__init__(backend_name="FaultyBackend")
        self.failure_mode = failure_mode

    def initialize_solver(
        self,
        parameters: ModelParameters,
        initial_soc: float,
        initial_temp_c: float,
        **kwargs: Any,
    ) -> None:
        if self.failure_mode == "init_crash":
            raise RuntimeError("Solver PDE compilation failure")
        self._is_initialized = True

    def step_simulation(
        self,
        current_a: float,
        dt_s: float,
        ambient_temp_c: float,
        current_state: ModelState,
    ) -> Union[PhysicsStepResult, tuple[float, float, float, float, Mapping[str, float]]]:
        if self.failure_mode == "crash":
            raise RuntimeError("CasADi algebraic loop solver divergence")
        if self.failure_mode == "unphysical_soc_high":
            return PhysicsStepResult(3.7, 3.7, 1.05, 25.0, {})
        if self.failure_mode == "unphysical_soc_low":
            return PhysicsStepResult(3.7, 3.7, -0.05, 25.0, {})
        if self.failure_mode == "unphysical_temp":
            return PhysicsStepResult(3.7, 3.7, 0.5, -280.0, {})
        if self.failure_mode == "nan_voltage":
            return PhysicsStepResult(float("nan"), 3.7, 0.5, 25.0, {})
        return PhysicsStepResult(3.7, 3.7, 0.5, 25.0, {})

    def reset(self) -> None:
        self._is_initialized = False


class TestPhysicsModelAdapter(unittest.TestCase):
    """Test suite verifying physics model abstractions, PyBaMM adapter, and hot-swappability."""

    # --------------------------------------------------------------------------
    # 1. PhysicsModelParameters Tests
    # --------------------------------------------------------------------------
    def test_valid_physics_parameters_comprehensive(self) -> None:
        """Create valid PhysicsModelParameters across SPM, SPMe, DFN, MSMR with all SI parameters."""
        params = PhysicsModelParameters(
            nominal_capacity_ah=2.2,
            nominal_voltage_v=3.7,
            model_type="DFN",
            parameter_set_name="Chen2020",
            electrode_area_m2=0.05,
            particle_radius_pos_m=5e-6,
            particle_radius_neg_m=10e-6,
            thickness_pos_m=70e-6,
            thickness_neg_m=80e-6,
            thickness_sep_m=25e-6,
            porosity_pos=0.35,
            porosity_neg=0.30,
            porosity_sep=0.45,
            solid_diffusivity_pos_m2_per_s=1e-14,
            solid_diffusivity_neg_m2_per_s=3e-14,
            electrolyte_conductivity_s_per_m=1.1,
            c_max_pos_mol_per_m3=51000.0,
            c_max_neg_mol_per_m3=30500.0,
            thermal_coupling="LUMPED",
            solver_rel_tol=1e-7,
            solver_abs_tol=1e-7,
        )
        self.assertEqual(params.model_type, "DFN")
        self.assertEqual(params.parameter_set_name, "Chen2020")
        self.assertEqual(params.particle_radius_pos_m, 5e-6)
        self.assertEqual(params.porosity_pos, 0.35)
        self.assertEqual(params.thermal_coupling, "LUMPED")

        # Verify serialization
        d = params.to_dict()
        self.assertEqual(d["model_type"], "DFN")
        self.assertEqual(d["porosity_neg"], 0.30)
        self.assertEqual(d["c_max_pos_mol_per_m3"], 51000.0)

    def test_invalid_physics_parameters_validation(self) -> None:
        """Verify strict SI unit and numerical boundary validation for parameters."""
        # Unsupported model type
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, model_type="WARP_DRIVE")

        # Empty parameter set name
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, parameter_set_name="   ")

        # Non-positive geometric / transport properties
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, electrode_area_m2=-0.01)
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, particle_radius_pos_m=0.0)
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, thickness_sep_m=-1e-6)
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, solid_diffusivity_pos_m2_per_s=0.0)
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, electrolyte_conductivity_s_per_m=-1.0)
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, c_max_pos_mol_per_m3=0.0)

        # Invalid porosity outside (0, 1)
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, porosity_pos=0.0)
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, porosity_pos=1.0)
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, porosity_neg=1.5)

        # Invalid thermal coupling
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, thermal_coupling="SUPERCOOLED")

        # Invalid solver tolerances
        with self.assertRaises(InvalidModelParametersError):
            PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7, solver_rel_tol=0.0)

    # --------------------------------------------------------------------------
    # 2. PhysicsStepResult Tests
    # --------------------------------------------------------------------------
    def test_physics_step_result_unpacking_and_attributes(self) -> None:
        """Verify that PhysicsStepResult supports attribute access and 5-tuple sequence unpacking."""
        res = PhysicsStepResult(
            terminal_voltage_v=3.65,
            open_circuit_voltage_v=3.80,
            soc_fraction=0.75,
            temperature_c=28.5,
            custom_states={"c_s_pos": 24000.0},
            heat_generation_w=0.45,
            internal_resistance_mohm=22.0,
            derivatives={"d_soc_dt": -0.001},
        )
        # Direct attributes
        self.assertEqual(res.terminal_voltage_v, 3.65)
        self.assertEqual(res.open_circuit_voltage_v, 3.80)
        self.assertEqual(res.soc_fraction, 0.75)
        self.assertEqual(res.temperature_c, 28.5)
        self.assertEqual(res.heat_generation_w, 0.45)
        self.assertEqual(res.internal_resistance_mohm, 22.0)

        # Sequence unpacking (5-tuple backward compatibility)
        v_term, v_oc, soc, temp, custom = res
        self.assertEqual(v_term, 3.65)
        self.assertEqual(v_oc, 3.80)
        self.assertEqual(soc, 0.75)
        self.assertEqual(temp, 28.5)
        self.assertEqual(custom["c_s_pos"], 24000.0)

        # Length and index access
        self.assertEqual(len(res), 5)
        self.assertEqual(res[0], 3.65)
        self.assertEqual(res[1], 3.80)

    # --------------------------------------------------------------------------
    # 3. Model-Agnostic PhysicsModelAdapter Tests
    # --------------------------------------------------------------------------
    def test_physics_model_adapter_lifecycle_and_protocol(self) -> None:
        """Verify model-agnostic PhysicsModelAdapter conforms to BatteryModel protocol and lifecycle."""
        backend = DummyCustomBackend("TestBackend")
        adapter = PhysicsModelAdapter.create_physics_model(
            model_id="phys_test_01",
            backend=backend,
            model_type="SPM",
            nominal_capacity_ah=2.2,
            nominal_voltage_v=3.7,
        )

        self.assertIsInstance(adapter, BatteryModel)
        self.assertEqual(adapter.metadata.model_id, "phys_test_01")
        self.assertEqual(adapter.metadata.paradigm, "PHYSICS_SPM")

        # Initialize
        init_state = adapter.initialize(soc_init=0.9, temperature_c=26.0)
        self.assertEqual(init_state.soc_fraction, 0.9)
        self.assertEqual(init_state.temperature_c, 26.0)
        self.assertTrue(backend.is_initialized)

        # Step
        inp = ModelInput(current_a=2.0, dt_s=1.0, ambient_temperature_c=25.0)
        out = adapter.step(inp)
        self.assertIsInstance(out, ModelOutput)
        self.assertLess(out.state.soc_fraction, 0.9)
        self.assertGreater(out.terminal_voltage_v, 3.0)
        self.assertIn("dummy_flux", out.state.custom_states)
        self.assertGreater(out.heat_generation_w, 0.0)
        self.assertEqual(out.internal_resistance_mohm, 30.0)

        # Reset
        adapter.reset()
        self.assertEqual(backend.reset_count, 1)

    # --------------------------------------------------------------------------
    # 4. Invariant Defense and Physical Bounds
    # --------------------------------------------------------------------------
    def test_physics_adapter_invariant_defense_unphysical_states(self) -> None:
        """Ensure adapter catches and rejects unphysical states (SOC > 1, SOC < 0, Temp <= -273.15C, NaN)."""
        meta = ModelMetadata(model_id="inv_test", name="Invariant Test", paradigm="PHYSICS_TEST")
        params = PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7)

        # Unphysical SOC High
        backend_high = FaultyPhysicsBackend("unphysical_soc_high")
        adapter_high = PhysicsModelAdapter(meta, params, backend_high)
        adapter_high.initialize(soc_init=0.8, temperature_c=25.0)
        with self.assertRaises(UnphysicalStateError):
            adapter_high.step(ModelInput(current_a=1.0, dt_s=1.0))

        # Unphysical SOC Low
        backend_low = FaultyPhysicsBackend("unphysical_soc_low")
        adapter_low = PhysicsModelAdapter(meta, params, backend_low)
        adapter_low.initialize(soc_init=0.8, temperature_c=25.0)
        with self.assertRaises(UnphysicalStateError):
            adapter_low.step(ModelInput(current_a=1.0, dt_s=1.0))

        # Unphysical Temperature
        backend_temp = FaultyPhysicsBackend("unphysical_temp")
        adapter_temp = PhysicsModelAdapter(meta, params, backend_temp)
        adapter_temp.initialize(soc_init=0.8, temperature_c=25.0)
        with self.assertRaises(UnphysicalStateError):
            adapter_temp.step(ModelInput(current_a=1.0, dt_s=1.0))

        # NaN Voltage
        backend_nan = FaultyPhysicsBackend("nan_voltage")
        adapter_nan = PhysicsModelAdapter(meta, params, backend_nan)
        adapter_nan.initialize(soc_init=0.8, temperature_c=25.0)
        with self.assertRaises(NumericalInstabilityError):
            adapter_nan.step(ModelInput(current_a=1.0, dt_s=1.0))

    def test_physics_adapter_error_propagation_on_backend_crash(self) -> None:
        """Backend solver runtime exceptions must be wrapped cleanly in ModelEvaluationError."""
        meta = ModelMetadata(model_id="crash_test", name="Crash Test", paradigm="PHYSICS_TEST")
        params = PhysicsModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=3.7)
        backend_crash = FaultyPhysicsBackend("crash")
        adapter = PhysicsModelAdapter(meta, params, backend_crash)
        adapter.initialize(soc_init=0.8, temperature_c=25.0)

        with self.assertRaises(ModelEvaluationError) as ctx:
            adapter.step(ModelInput(current_a=1.0, dt_s=1.0))
        self.assertIn("divergence", str(ctx.exception))

    # --------------------------------------------------------------------------
    # 5. SimulatedPhysicsBackend Electrochemical Tests
    # --------------------------------------------------------------------------
    def test_simulated_physics_backend_execution(self) -> None:
        """Verify simulated electrochemical backend returns valid physics variables and custom states."""
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
        self.assertIn("eta_ohmic_v", out.state.custom_states)

    # --------------------------------------------------------------------------
    # 6. Electro-Thermal Dynamics and Determinism
    # --------------------------------------------------------------------------
    def test_physics_model_electro_thermal_heating_and_cooling(self) -> None:
        """Verify heavy discharge causes temperature rise and subsequent rest cools toward ambient."""
        adapter = PyBaMMModelAdapter.create_spm_adapter(
            model_id="spm_thermal_01",
            nominal_capacity_ah=2.2,
            nominal_voltage_v=3.7,
            backend=SimulatedPhysicsBackend(model_type="SPM"),
        )
        adapter.initialize(soc_init=0.95, temperature_c=25.0)

        # 1. 100 seconds of 4.0 A discharge
        inp_discharge = ModelInput(current_a=4.0, dt_s=1.0, ambient_temperature_c=25.0)
        for _ in range(100):
            out = adapter.step(inp_discharge)

        t_heated = out.state.temperature_c
        self.assertGreater(t_heated, 25.0, "Cell temperature must rise during 4A discharge.")
        self.assertGreater(out.heat_generation_w, 0.2, "Heat generation rate must be positive.")

        # 2. 200 seconds of rest (I = 0.0 A)
        inp_rest = ModelInput(current_a=0.0, dt_s=1.0, ambient_temperature_c=25.0)
        for _ in range(200):
            out = adapter.step(inp_rest)

        t_cooled = out.state.temperature_c
        self.assertLess(t_cooled, t_heated, "Cell temperature must decay back toward ambient during rest.")

    def test_deterministic_physics_simulation_runs(self) -> None:
        """Two identical multi-step simulation sequences must produce bitwise identical trajectories."""
        backend_1 = SimulatedPhysicsBackend(model_type="SPM")
        adapter_1 = PyBaMMModelAdapter.create_spm_adapter("spm_det_1", 2.2, 3.7, backend=backend_1)

        backend_2 = SimulatedPhysicsBackend(model_type="SPM")
        adapter_2 = PyBaMMModelAdapter.create_spm_adapter("spm_det_2", 2.2, 3.7, backend=backend_2)

        steps = [
            ModelInput(current_a=2.5 if (i % 8 < 5) else -1.0, dt_s=0.5, ambient_temperature_c=25.0)
            for i in range(40)
        ]

        adapter_1.initialize(soc_init=0.85, temperature_c=25.0)
        traj_1 = [adapter_1.step(inp).terminal_voltage_v for inp in steps]

        adapter_2.initialize(soc_init=0.85, temperature_c=25.0)
        traj_2 = [adapter_2.step(inp).terminal_voltage_v for inp in steps]

        self.assertEqual(traj_1, traj_2, "Physics simulation trajectories must be 100% deterministic.")

    # --------------------------------------------------------------------------
    # 7. Protocol Compliance & Model Hot-Swappability
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
    # 8. Native PyBaMM Solver Integration
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

    # --------------------------------------------------------------------------
    # 9. Top-Level src.physics Package Re-export Tests
    # --------------------------------------------------------------------------
    def test_src_physics_package_reexports(self) -> None:
        """Verify that src.physics re-exports core physics interfaces cleanly."""
        from src.models.base import AbstractBatteryModel

        self.assertTrue(issubclass(TopLevelPhysicsAdapter, AbstractBatteryModel))
        adapter = TopLevelPhysicsAdapter.create_physics_model(
            model_id="top_test",
            backend=DummyCustomBackend(),
        )
        self.assertIsInstance(adapter, BatteryModel)
        params = TopLevelPhysicsParams(nominal_capacity_ah=2.2, nominal_voltage_v=3.7)
        self.assertEqual(params.nominal_capacity_ah, 2.2)


if __name__ == "__main__":
    unittest.main()

