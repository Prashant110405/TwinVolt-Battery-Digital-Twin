"""Unit tests enforcing Mathematical and Physical Invariants."""

import unittest

from src.models.exceptions import (
    InvalidModelInputError,
    InvalidModelParametersError,
    InvalidModelStateError,
    NumericalInstabilityError,
)
from src.models.math import assert_finite, calculate_coulomb_soc_step, clamp
from src.models.types import (
    ModelInput,
    ModelOutput,
    ModelParameters,
    ModelState,
)


class TestMathematicalInvariants(unittest.TestCase):
    """Rigorous tests enforcing mathematical and physical invariant defense."""

    def test_invariant_soc_and_soh_clamping_and_bounds(self) -> None:
        """SOC and SOH must strictly reside within [0.0, 1.0]."""
        valid_state = ModelState(soc_fraction=0.0, soh_fraction=0.0)
        self.assertEqual(valid_state.soc_fraction, 0.0)
        self.assertEqual(valid_state.soh_fraction, 0.0)

        valid_full = ModelState(soc_fraction=1.0, soh_fraction=1.0)
        self.assertEqual(valid_full.soc_fraction, 1.0)
        self.assertEqual(valid_full.soh_fraction, 1.0)

        with self.assertRaises(InvalidModelStateError):
            ModelState(soc_fraction=-0.0001)

        with self.assertRaises(InvalidModelStateError):
            ModelState(soc_fraction=1.0001)

        with self.assertRaises(InvalidModelStateError):
            ModelState(soc_fraction=0.5, soh_fraction=-0.1)

    def test_invariant_absolute_zero_temperature(self) -> None:
        """No temperature in state, input, or output may equal or fall below -273.15 C."""
        with self.assertRaises(InvalidModelStateError):
            ModelState(soc_fraction=0.5, temperature_c=-273.15)

        with self.assertRaises(InvalidModelStateError):
            ModelState(soc_fraction=0.5, surface_temperature_c=-273.15)

        with self.assertRaises(InvalidModelInputError):
            ModelInput(current_a=0.0, dt_s=1.0, ambient_temperature_c=-273.15)

        with self.assertRaises(InvalidModelInputError):
            ModelInput(current_a=0.0, dt_s=1.0, coolant_temperature_c=-273.15)

    def test_invariant_time_direction(self) -> None:
        """Time step dt must strictly be > 0.0 seconds (no time reversal or freeze)."""
        with self.assertRaises(InvalidModelInputError):
            ModelInput(current_a=1.0, dt_s=0.0)

        with self.assertRaises(InvalidModelInputError):
            ModelInput(current_a=1.0, dt_s=-1e-6)

    def test_invariant_numerical_finiteness(self) -> None:
        """NaN and Inf must be rejected across all containers and numerical math."""
        with self.assertRaises(InvalidModelStateError):
            ModelState(soc_fraction=float("nan"))

        with self.assertRaises(InvalidModelInputError):
            ModelInput(current_a=float("inf"), dt_s=1.0)

        with self.assertRaises(InvalidModelParametersError):
            ModelOutput(
                terminal_voltage_v=float("nan"),
                open_circuit_voltage_v=3.7,
                state=ModelState(soc_fraction=0.5),
            )

        with self.assertRaises(NumericalInstabilityError):
            assert_finite(float("-inf"))

    def test_invariant_deterministic_state_propagation(self) -> None:
        """Given identical inputs, Coulomb step calculation must be 100% deterministic."""
        res1 = calculate_coulomb_soc_step(2.5, 0.1, 2.2, 0.99)
        res2 = calculate_coulomb_soc_step(2.5, 0.1, 2.2, 0.99)
        self.assertEqual(res1, res2)


if __name__ == "__main__":
    unittest.main()
