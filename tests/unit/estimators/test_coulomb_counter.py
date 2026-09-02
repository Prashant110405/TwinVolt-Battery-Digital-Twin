"""Unit tests for CoulombCounter Battery State of Charge (SOC) Estimator."""

import math
import unittest

from src.estimators.base import EstimationInput, EstimationState, StateEstimator
from src.estimators.coulomb_counter import CoulombCounter
from src.estimators.exceptions import InvalidEstimatorInputError
from src.models.exceptions import InvalidModelParametersError, InvalidModelStateError
from src.models.parameters.linear_ocv import LinearOCVModel


class TestCoulombCounter(unittest.TestCase):
    """Test suite verifying CoulombCounter integration, variance growth, rest recalibration, and invariants."""

    def setUp(self) -> None:
        """Create reference CoulombCounter instances."""
        self.ocv_model = LinearOCVModel(v_min_v=3.0, v_max_v=4.2)
        self.cc = CoulombCounter(
            estimator_id="cc_unit_test",
            nominal_capacity_ah=2.0,
            coulombic_efficiency=1.0,
            current_sensor_noise_std_a=0.01,
            rest_current_threshold_a=0.02,
            rest_time_threshold_s=100.0,  # Short threshold for test
            ocv_recalibration_soc_variance=0.0002,
            ocv_model=self.ocv_model,
        )
        self.cc.initialize(initial_soc=1.0, initial_soh=1.0, temperature_c=25.0)

    # --------------------------------------------------------------------------
    # 1. Protocol & Basic Integration
    # --------------------------------------------------------------------------
    def test_state_estimator_protocol_compliance(self) -> None:
        """Verify CoulombCounter adheres to the StateEstimator protocol."""
        self.assertIsInstance(self.cc, StateEstimator)
        self.assertEqual(self.cc.estimator_id, "cc_unit_test")
        self.assertEqual(self.cc.state.soc_fraction, 1.0)

    def test_constant_current_discharge(self) -> None:
        """Discharging 2.0 A for 1800 s on a 2.0 Ah cell must reduce SOC by exactly 0.50."""
        # 1800 steps of dt = 1.0 s, I = 2.0 A
        for _ in range(1800):
            inp = EstimationInput(current_a=2.0, voltage_v=3.6, temperature_c=25.0, dt_s=1.0)
            out = self.cc.step(inp)

        self.assertAlmostEqual(self.cc.state.soc_fraction, 0.50, places=4)
        self.assertAlmostEqual(out.state.soc_fraction, 0.50, places=4)
        # Variance should have grown
        self.assertGreater(self.cc.state.soc_variance, 0.0001)

    def test_constant_current_charge_with_efficiency(self) -> None:
        """Charging with coulombic efficiency < 1.0."""
        cc_eff = CoulombCounter(
            estimator_id="cc_eff",
            nominal_capacity_ah=2.0,
            coulombic_efficiency=0.90,
        )
        cc_eff.initialize(initial_soc=0.0, initial_soh=1.0)

        # Charge -2.0 A for 1800 s -> 1.0 Ah drawn * 0.90 eff = 0.90 Ah stored -> SOC = 0.45
        for _ in range(1800):
            cc_eff.step(EstimationInput(current_a=-2.0, voltage_v=3.5, dt_s=1.0))

        self.assertAlmostEqual(cc_eff.state.soc_fraction, 0.45, places=4)

    # --------------------------------------------------------------------------
    # 2. Rest Detection and Resting OCV Recalibration
    # --------------------------------------------------------------------------
    def test_resting_ocv_recalibration(self) -> None:
        """When current is near zero for rest_time_threshold_s, OCV recalibration corrects SOC."""
        # Set SOC intentionally off: 0.20
        self.cc.initialize(initial_soc=0.20, temperature_c=25.0)

        # Apply rest current 0.005 A with voltage 3.96 V (which corresponds to SOC = 0.80 for 3.0-4.2V linear OCV)
        # OCV(0.8) = 3.0 + 0.8 * 1.2 = 3.96 V
        recalibrated = False
        for step_idx in range(150):
            out = self.cc.step(
                EstimationInput(current_a=0.005, voltage_v=3.96, temperature_c=25.0, dt_s=1.0)
            )
            if out.diagnostics.get("recalibration_applied"):
                recalibrated = True
                break

        self.assertTrue(recalibrated, "OCV resting recalibration should have triggered.")
        self.assertAlmostEqual(self.cc.state.soc_fraction, 0.80, delta=0.01)
        self.assertEqual(self.cc.state.soc_variance, 0.0002)
        self.assertEqual(self.cc.total_recalibrations, 1)

    # --------------------------------------------------------------------------
    # 3. Boundary Clamping & Invariant Defense
    # --------------------------------------------------------------------------
    def test_soc_boundary_clamping(self) -> None:
        """Over-discharging or over-charging is clamped strictly to [0.0, 1.0]."""
        self.cc.initialize(initial_soc=0.10)
        # Deep discharge 10.0 A for 1000 s
        self.cc.step(EstimationInput(current_a=10.0, voltage_v=3.0, dt_s=1000.0))
        self.assertEqual(self.cc.state.soc_fraction, 0.0)

        # Heavy charge -10.0 A for 2000 s
        self.cc.step(EstimationInput(current_a=-10.0, voltage_v=4.2, dt_s=2000.0))
        self.assertEqual(self.cc.state.soc_fraction, 1.0)

    def test_invalid_construction_and_input_parameters(self) -> None:
        """Verify strict parameter validation."""
        with self.assertRaises(InvalidModelParametersError):
            CoulombCounter(estimator_id="cc_bad", nominal_capacity_ah=-1.0)

        with self.assertRaises(InvalidModelParametersError):
            CoulombCounter(estimator_id="cc_bad", nominal_capacity_ah=2.0, coulombic_efficiency=0.0)

        with self.assertRaises(InvalidEstimatorInputError):
            self.cc.step(EstimationInput(current_a=1.0, voltage_v=-1.0, dt_s=1.0))

        with self.assertRaises(InvalidEstimatorInputError):
            self.cc.step(EstimationInput(current_a=1.0, voltage_v=3.7, dt_s=-1.0))

    def test_reset_behavior(self) -> None:
        """Reset clears rest timers and updates state."""
        self.cc.initialize(initial_soc=0.5)
        self.cc.step(EstimationInput(current_a=0.0, voltage_v=3.6, dt_s=50.0))
        self.assertEqual(self.cc.rest_duration_s, 50.0)

        self.cc.reset()
        self.assertEqual(self.cc.rest_duration_s, 0.0)
        self.assertEqual(self.cc.state.soc_fraction, 1.0)


if __name__ == "__main__":
    unittest.main()
