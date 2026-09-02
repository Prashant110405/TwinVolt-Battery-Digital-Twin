"""Unit tests for Temperature Scaling and Arrhenius Kinetics."""

import math
import unittest

from src.models.exceptions import (
    InvalidModelParametersError,
    InvalidModelStateError,
    NumericalInstabilityError,
)
from src.models.parameters.temperature_scaling import TemperatureScaling


class TestTemperatureScaling(unittest.TestCase):
    """Test suite verifying Arrhenius resistance scaling, capacity derating, and physical invariants."""

    def setUp(self) -> None:
        """Create standard test scaling models."""
        self.scaling_default = TemperatureScaling()
        self.scaling_custom = TemperatureScaling(
            activation_energy_j_per_mol=30000.0,
            reference_temperature_c=25.0,
            low_temp_resistance_multiplier=2.0,
            capacity_derating_fraction_per_k=0.008,
            min_capacity_retention_fraction=0.35,
        )

    # --------------------------------------------------------------------------
    # 1. Arrhenius Resistance Scaling
    # --------------------------------------------------------------------------
    def test_reference_temperature_neutrality(self) -> None:
        """At reference temperature (25°C), multiplier must be exactly 1.0."""
        mult = self.scaling_default.get_resistance_multiplier(25.0)
        self.assertAlmostEqual(mult, 1.0, places=6)

        r_scaled = self.scaling_default.scale_resistance(0.025, 25.0)
        self.assertAlmostEqual(r_scaled, 0.025, places=6)

    def test_high_temperature_resistance_decrease(self) -> None:
        """Above reference temperature (e.g. 45°C), thermal activation decreases resistance."""
        mult_45c = self.scaling_default.get_resistance_multiplier(45.0)
        self.assertLess(mult_45c, 1.0)
        self.assertGreater(mult_45c, 0.4)

        r_base = 0.025
        r_hot = self.scaling_default.scale_resistance(r_base, 45.0)
        self.assertLess(r_hot, r_base)

    def test_low_temperature_resistance_increase(self) -> None:
        """Below reference temperature (e.g. 0°C and -15°C), resistance increases significantly."""
        mult_0c = self.scaling_custom.get_resistance_multiplier(0.0)
        mult_minus15c = self.scaling_custom.get_resistance_multiplier(-15.0)

        self.assertGreater(mult_0c, 1.0)
        self.assertGreater(mult_minus15c, mult_0c)

        r_base = 0.030
        r_cold = self.scaling_custom.scale_resistance(r_base, -15.0)
        self.assertGreater(r_cold, r_base * 2.0)

    # --------------------------------------------------------------------------
    # 2. Usable Capacity Derating
    # --------------------------------------------------------------------------
    def test_usable_capacity_scaling_at_ambient_and_hot(self) -> None:
        """At or above 25°C, retention fraction is exactly 1.0 (no capacity loss)."""
        self.assertEqual(self.scaling_default.get_capacity_retention_fraction(25.0), 1.0)
        self.assertEqual(self.scaling_default.get_capacity_retention_fraction(40.0), 1.0)
        self.assertEqual(self.scaling_default.scale_capacity(2.5, 30.0), 2.5)

    def test_usable_capacity_derating_sub_zero_and_clamp(self) -> None:
        """At sub-zero temperatures, usable capacity decreases linearly and is clamped at floor."""
        # At 0°C (delta = 25 K): retention = 1.0 - (0.006 * 25) = 0.85
        ret_0c = self.scaling_default.get_capacity_retention_fraction(0.0)
        self.assertAlmostEqual(ret_0c, 0.85, places=5)
        self.assertAlmostEqual(self.scaling_default.scale_capacity(2.0, 0.0), 1.70, places=5)

        # At -50°C (delta = 75 K): calculated = 1.0 - (0.006 * 75) = 0.55
        ret_minus50c = self.scaling_default.get_capacity_retention_fraction(-50.0)
        self.assertAlmostEqual(ret_minus50c, 0.55, places=5)

        # At -200°C: must clamp to min_capacity_retention_fraction (0.40)
        ret_extreme = self.scaling_default.get_capacity_retention_fraction(-200.0)
        self.assertEqual(ret_extreme, 0.40)

    # --------------------------------------------------------------------------
    # 3. Invariants & Input Validation
    # --------------------------------------------------------------------------
    def test_invalid_construction_parameters_raise(self) -> None:
        """Negative activation energy, non-positive multiplier, or invalid floor must fail."""
        with self.assertRaises(InvalidModelParametersError):
            TemperatureScaling(activation_energy_j_per_mol=-1.0)

        with self.assertRaises(InvalidModelParametersError):
            TemperatureScaling(reference_temperature_c=-273.15)

        with self.assertRaises(InvalidModelParametersError):
            TemperatureScaling(low_temp_resistance_multiplier=0.0)

        with self.assertRaises(InvalidModelParametersError):
            TemperatureScaling(capacity_derating_fraction_per_k=-0.01)

        with self.assertRaises(InvalidModelParametersError):
            TemperatureScaling(min_capacity_retention_fraction=-0.1)

        with self.assertRaises(InvalidModelParametersError):
            TemperatureScaling(min_capacity_retention_fraction=1.5)

    def test_invalid_evaluation_temperature_and_resistance_raise(self) -> None:
        """Temperature <= -273.15 C and negative resistances must fail."""
        with self.assertRaises(InvalidModelStateError):
            self.scaling_default.get_resistance_multiplier(-273.15)

        with self.assertRaises(InvalidModelStateError):
            self.scaling_default.get_capacity_retention_fraction(-274.0)

        with self.assertRaises(InvalidModelParametersError):
            self.scaling_default.scale_resistance(-0.01, 25.0)

        with self.assertRaises(InvalidModelParametersError):
            self.scaling_default.scale_capacity(0.0, 25.0)

    def test_nan_and_inf_rejection(self) -> None:
        """NaN and Inf values must raise NumericalInstabilityError."""
        with self.assertRaises(NumericalInstabilityError):
            self.scaling_default.get_resistance_multiplier(float("nan"))

        with self.assertRaises(NumericalInstabilityError):
            self.scaling_default.scale_resistance(float("inf"), 25.0)

    # --------------------------------------------------------------------------
    # 4. Serialization & Determinism
    # --------------------------------------------------------------------------
    def test_serialization_roundtrip(self) -> None:
        """Verify to_dict and from_dict produce identical configurations."""
        d = self.scaling_custom.to_dict()
        reconstructed = TemperatureScaling.from_dict(d)
        self.assertEqual(reconstructed.activation_energy_j_per_mol, 30000.0)
        self.assertEqual(reconstructed.low_temp_resistance_multiplier, 2.0)
        self.assertEqual(
            reconstructed.get_resistance_multiplier(-10.0),
            self.scaling_custom.get_resistance_multiplier(-10.0),
        )

    def test_deterministic_scaling(self) -> None:
        """Identical inputs produce bitwise equal outputs."""
        m1 = self.scaling_default.get_resistance_multiplier(-5.555555555)
        m2 = self.scaling_default.get_resistance_multiplier(-5.555555555)
        self.assertEqual(m1, m2)


if __name__ == "__main__":
    unittest.main()
