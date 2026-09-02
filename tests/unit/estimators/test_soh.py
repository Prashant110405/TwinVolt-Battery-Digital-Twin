"""Unit tests for State of Health (SOH) and Impedance Degradation Estimator."""

import unittest

from src.domain.battery.enums import BatteryHealthState
from src.estimators.base import EstimationInput, StateEstimator
from src.estimators.soh import SOHEstimator
from src.models.exceptions import InvalidModelParametersError


class TestSOHEstimator(unittest.TestCase):
    """Test suite verifying SOH capacity tracking, resistance estimation, health classification, and invariants."""

    def setUp(self) -> None:
        """Create reference SOHEstimator instance."""
        self.soh = SOHEstimator(
            estimator_id="soh_test",
            nominal_capacity_ah=2.0,
            baseline_r0_ohm=0.025,
            eol_resistance_multiplier=2.0,
            min_cycle_delta_soc=0.20,
            current_step_threshold_a=1.0,
            capacity_filter_alpha=0.5,  # Fast filter for unit test
        )
        self.soh.initialize(initial_soc=1.0, initial_soh=1.0, temperature_c=25.0)

    # --------------------------------------------------------------------------
    # 1. Protocol & Basic Metrics
    # --------------------------------------------------------------------------
    def test_state_estimator_protocol_compliance(self) -> None:
        """Verify SOHEstimator adheres to the StateEstimator protocol."""
        self.assertIsInstance(self.soh, StateEstimator)
        self.assertEqual(self.soh.estimator_id, "soh_test")
        self.assertEqual(self.soh.health_state, BatteryHealthState.HEALTHY)

    def test_throughput_accumulation(self) -> None:
        """Charge and discharge currents accumulate total throughput in Ah."""
        # 1.0 A discharge for 1800 s = 0.50 Ah
        for _ in range(1800):
            self.soh.step(EstimationInput(current_a=1.0, voltage_v=3.8, dt_s=1.0))
        self.assertAlmostEqual(self.soh.total_throughput_ah, 0.50, places=4)

        # 2.0 A charge for 900 s = 0.50 Ah
        for _ in range(900):
            self.soh.step(EstimationInput(current_a=-2.0, voltage_v=3.9, dt_s=1.0))
        self.assertAlmostEqual(self.soh.total_throughput_ah, 1.00, places=4)

    # --------------------------------------------------------------------------
    # 2. Pulse Resistance Tracking
    # --------------------------------------------------------------------------
    def test_pulse_resistance_tracking(self) -> None:
        """Current step of 2.0 A with voltage drop of 0.060 V implies R0 = 30 mOhm."""
        # Baseline step at 0 A, 4.0 V
        self.soh.step(EstimationInput(current_a=0.0, voltage_v=4.0, dt_s=1.0))

        # Pulse step: I = 2.0 A (delta I = 2.0 A), V = 3.94 V (delta V = 0.060 V) -> R0 = 0.030 Ohm
        out = self.soh.step(EstimationInput(current_a=2.0, voltage_v=3.94, dt_s=1.0))

        # Filtered R0 should have shifted towards 30 mOhm from fresh 25 mOhm
        self.assertGreater(self.soh.estimated_r0_mohm, 25.0)
        self.assertLessEqual(self.soh.estimated_r0_mohm, 30.0)
        # SOH_R will decrease slightly
        self.assertLess(self.soh.soh_resistance_fraction, 1.0)

    # --------------------------------------------------------------------------
    # 3. Capacity Degradation Tracking
    # --------------------------------------------------------------------------
    def test_capacity_degradation_cycle_tracking(self) -> None:
        """Discharge of 0.80 Ah with SOC delta of 0.50 implies usable capacity = 1.60 Ah (SOH_C = 0.80)."""
        # Start at SOC = 1.0
        self.soh.initialize(initial_soc=1.0, initial_soh=1.0)

        # Discharge 1.0 A for 2880 s (0.80 Ah) while reporting SOC dropping from 1.0 to 0.50
        steps = 2880
        for step_idx in range(steps):
            soc_now = 1.0 - (step_idx / steps) * 0.50
            # Manually advance estimator state SOC for test
            self.soh.state.with_updates(soc_fraction=soc_now)
            self.soh._state = self.soh.state.with_updates(soc_fraction=soc_now)
            self.soh.step(EstimationInput(current_a=1.0, voltage_v=3.7, dt_s=1.0))

        # Enter rest to trigger cycle completion
        self.soh._state = self.soh.state.with_updates(soc_fraction=0.50)
        out = self.soh.step(EstimationInput(current_a=0.0, voltage_v=3.6, dt_s=1.0))

        # SOH capacity should reflect ~0.80
        self.assertLess(self.soh.soh_capacity_fraction, 1.0)

    # --------------------------------------------------------------------------
    # 4. Health State Classification
    # --------------------------------------------------------------------------
    def test_health_state_classifications(self) -> None:
        """Verify mapping to BatteryHealthState enum."""
        self.soh._soh_c = 0.95
        self.soh._soh_r = 0.95
        self.assertEqual(self.soh.health_state, BatteryHealthState.HEALTHY)

        self.soh._soh_c = 0.85
        self.assertEqual(self.soh.health_state, BatteryHealthState.AGED)

        self.soh._soh_c = 0.75
        self.assertEqual(self.soh.health_state, BatteryHealthState.DEGRADED)

        self.soh._soh_c = 0.65
        self.assertEqual(self.soh.health_state, BatteryHealthState.CRITICAL)

        self.soh._soh_c = 0.55
        self.assertEqual(self.soh.health_state, BatteryHealthState.END_OF_LIFE)

    # --------------------------------------------------------------------------
    # 5. Invariant & Parameter Validation
    # --------------------------------------------------------------------------
    def test_invalid_construction_parameters_raise(self) -> None:
        """Negative capacity or invalid resistance multipliers must fail."""
        with self.assertRaises(InvalidModelParametersError):
            SOHEstimator(estimator_id="bad", nominal_capacity_ah=0.0)

        with self.assertRaises(InvalidModelParametersError):
            SOHEstimator(estimator_id="bad", nominal_capacity_ah=2.0, eol_resistance_multiplier=1.0)


if __name__ == "__main__":
    unittest.main()
