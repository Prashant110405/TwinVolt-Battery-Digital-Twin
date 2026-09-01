"""Unit tests for BatteryModel Protocol and AbstractBatteryModel Base Class."""

from typing import Any
import unittest

from src.models.base import AbstractBatteryModel, BatteryModel
from src.models.exceptions import ModelEvaluationError, ModelInitializationError
from src.models.types import (
    ModelInput,
    ModelMetadata,
    ModelOutput,
    ModelParameters,
    ModelState,
)


class SimpleMockModel(AbstractBatteryModel):
    """Simple linear resistance battery model implementation for contract testing."""

    def _create_initial_state(
        self,
        soc_init: float,
        temperature_c: float,
        **kwargs: Any,
    ) -> ModelState:
        return ModelState(
            soc_fraction=soc_init,
            temperature_c=temperature_c,
        )

    def _compute_step(
        self,
        model_input: ModelInput,
        current_state: ModelState,
    ) -> ModelOutput:
        # Simple dummy linear relationship: V = 3.7 - I * 0.025
        v_oc = 3.7
        r_ohm = 0.025
        v_term = v_oc - (model_input.current_a * r_ohm)
        q_gen = (model_input.current_a ** 2) * r_ohm

        next_state = current_state.with_updates(
            temperature_c=current_state.temperature_c + 0.01
        )

        return ModelOutput(
            terminal_voltage_v=v_term,
            open_circuit_voltage_v=v_oc,
            state=next_state,
            heat_generation_w=q_gen,
            internal_resistance_mohm=r_ohm * 1000.0,
        )


class FaultyMockModel(AbstractBatteryModel):
    """Model that raises during step for error handling verification."""

    def _create_initial_state(self, soc_init: float, temperature_c: float, **kwargs: Any) -> ModelState:
        if kwargs.get("fail_init"):
            raise ValueError("Forced init failure")
        return ModelState(soc_fraction=soc_init, temperature_c=temperature_c)

    def _compute_step(self, model_input: ModelInput, current_state: ModelState) -> ModelOutput:
        raise ZeroDivisionError("Simulated solver crash")


class TestBaseContracts(unittest.TestCase):
    """Test suite verifying protocol compliance and abstract model base class."""

    def setUp(self) -> None:
        """Create test metadata and parameters."""
        self.metadata = ModelMetadata(
            model_id="mock_model_01",
            name="Mock Test Model",
            paradigm="ECM_TEST",
        )
        self.parameters = ModelParameters(
            nominal_capacity_ah=2.2,
            nominal_voltage_v=3.7,
        )

    def test_battery_model_protocol_compliance(self) -> None:
        """Verify that SimpleMockModel satisfies BatteryModel protocol."""
        model = SimpleMockModel(self.metadata, self.parameters)
        self.assertIsInstance(model, BatteryModel)

    def test_model_lifecycle_step_and_reset(self) -> None:
        """Test initialize, step, state updates, and reset."""
        model = SimpleMockModel(self.metadata, self.parameters)
        self.assertEqual(model.state.soc_fraction, 1.0)
        self.assertEqual(model.state.temperature_c, 25.0)

        # Initialize with custom SOC
        init_state = model.initialize(soc_init=0.8, temperature_c=30.0)
        self.assertEqual(init_state.soc_fraction, 0.8)
        self.assertEqual(model.state.temperature_c, 30.0)

        # Execute simulation step
        inp = ModelInput(current_a=2.0, dt_s=1.0)
        out = model.step(inp)
        self.assertAlmostEqual(out.terminal_voltage_v, 3.7 - (2.0 * 0.025), places=4)
        self.assertAlmostEqual(out.heat_generation_w, (4.0 * 0.025), places=4)
        self.assertEqual(model.state.temperature_c, 30.01)

        # Reset
        model.reset()
        self.assertEqual(model.state.soc_fraction, 1.0)
        self.assertEqual(model.state.temperature_c, 25.0)

    def test_error_wrapping_in_model_lifecycle(self) -> None:
        """Verify that initialization and evaluation errors are properly wrapped."""
        faulty = FaultyMockModel(self.metadata, self.parameters)

        # Init failure wrapped in ModelInitializationError
        with self.assertRaises(ModelInitializationError):
            faulty.initialize(fail_init=True)

        # Step failure wrapped in ModelEvaluationError
        inp = ModelInput(current_a=1.0, dt_s=1.0)
        with self.assertRaises(ModelEvaluationError):
            faulty.step(inp)


if __name__ == "__main__":
    unittest.main()
