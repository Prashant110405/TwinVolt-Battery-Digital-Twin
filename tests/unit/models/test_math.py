"""Unit tests for Mathematical Utilities and Numerical ODE Integrators."""

import math
import unittest

from src.models.exceptions import NumericalInstabilityError
from src.models.math import (
    ExplicitEulerIntegrator,
    RungeKutta4Integrator,
    assert_finite,
    calculate_coulomb_soc_step,
    clamp,
    is_finite_number,
    solve_rc_branch_voltage_step,
)


class TestMathematicalUtilities(unittest.TestCase):
    """Test suite verifying numerical integrity, integrators, and Coulomb accounting."""

    # --------------------------------------------------------------------------
    # 1. Finite Checking & Clamping
    # --------------------------------------------------------------------------
    def test_is_finite_number(self) -> None:
        """Verify finite real number detection."""
        self.assertTrue(is_finite_number(0))
        self.assertTrue(is_finite_number(3.1415))
        self.assertTrue(is_finite_number(-100.5))

        self.assertFalse(is_finite_number(float("nan")))
        self.assertFalse(is_finite_number(float("inf")))
        self.assertFalse(is_finite_number(float("-inf")))
        self.assertFalse(is_finite_number(True))
        self.assertFalse(is_finite_number("12.5"))
        self.assertFalse(is_finite_number(None))

    def test_assert_finite(self) -> None:
        """assert_finite must raise NumericalInstabilityError on NaN/Inf."""
        assert_finite(10.5, "valid_num")
        with self.assertRaises(NumericalInstabilityError):
            assert_finite(float("nan"), "bad_var")
        with self.assertRaises(NumericalInstabilityError):
            assert_finite(float("inf"), "bad_var")

    def test_clamp(self) -> None:
        """Verify clamping within boundaries."""
        self.assertEqual(clamp(0.5, 0.0, 1.0), 0.5)
        self.assertEqual(clamp(-0.2, 0.0, 1.0), 0.0)
        self.assertEqual(clamp(1.5, 0.0, 1.0), 1.0)
        with self.assertRaises(ValueError):
            clamp(0.5, 1.0, 0.0)

    # --------------------------------------------------------------------------
    # 2. Coulomb Accounting
    # --------------------------------------------------------------------------
    def test_calculate_coulomb_soc_step(self) -> None:
        """Verify exact charge integration: 1 hour at 1C (2.2A for 2.2Ah) -> dSOC = -1.0."""
        # 1-hour discharge at 1C (2.2A, 3600s, 2.2Ah)
        d_soc = calculate_coulomb_soc_step(
            current_a=2.2,
            dt_s=3600.0,
            nominal_capacity_ah=2.2,
        )
        self.assertAlmostEqual(d_soc, -1.0, places=6)

        # 1-second discharge at 2.2A
        d_soc_1s = calculate_coulomb_soc_step(
            current_a=2.2,
            dt_s=1.0,
            nominal_capacity_ah=2.2,
        )
        self.assertAlmostEqual(d_soc_1s, -1.0 / 3600.0, places=8)

        # 1-second charge at -2.2A with 98% efficiency
        d_soc_chg = calculate_coulomb_soc_step(
            current_a=-2.2,
            dt_s=3600.0,
            nominal_capacity_ah=2.2,
            coulombic_efficiency=0.98,
        )
        self.assertAlmostEqual(d_soc_chg, 0.98, places=6)

        # Zero current rest
        d_soc_rest = calculate_coulomb_soc_step(
            current_a=0.0,
            dt_s=100.0,
            nominal_capacity_ah=2.2,
        )
        self.assertEqual(d_soc_rest, 0.0)

    # --------------------------------------------------------------------------
    # 3. Explicit Euler & RK4 Integrators
    # --------------------------------------------------------------------------
    def test_euler_and_rk4_exponential_decay(self) -> None:
        """Compare Euler vs RK4 on dy/dt = -y (Analytical solution y(t) = y0 * exp(-t))."""
        # dy/dt = -y, y0 = 1.0, t = 0 to 1.0 s with dt = 0.1 s
        euler = ExplicitEulerIntegrator()
        rk4 = RungeKutta4Integrator()

        def dy_dt(t: float, y: float) -> float:
            return -y

        # Step 1 step dt=0.1
        y_euler_1 = euler.step(dy_dt, y=1.0, t=0.0, dt=0.1)
        y_rk4_1 = rk4.step(dy_dt, y=1.0, t=0.0, dt=0.1)
        y_exact_1 = math.exp(-0.1)

        # Euler: y1 = 1.0 - 0.1 = 0.9
        self.assertAlmostEqual(y_euler_1, 0.9, places=6)

        # RK4 error should be orders of magnitude smaller than Euler
        rk4_err = abs(y_rk4_1 - y_exact_1)
        euler_err = abs(y_euler_1 - y_exact_1)
        self.assertLess(rk4_err, 1e-5)
        self.assertLess(rk4_err, euler_err)

    # --------------------------------------------------------------------------
    # 4. RC Branch Analytical Step
    # --------------------------------------------------------------------------
    def test_solve_rc_branch_voltage_step(self) -> None:
        """Verify discrete RC branch exponential transient."""
        # R = 10 mOhm = 0.01 Ohm, C = 1000 F -> tau = 10 s
        # Current = 10 A -> steady state V_rc = I * R = 0.1 V
        r_ohm = 0.01
        c_f = 1000.0
        current_a = 10.0
        dt_s = 1.0

        # Step 1: from 0.0 V
        v_next_1 = solve_rc_branch_voltage_step(
            v_rc_current=0.0,
            current_a=current_a,
            resistance_r_ohm=r_ohm,
            capacitance_c_farad=c_f,
            dt_s=dt_s,
        )
        expected_1 = 0.1 * (1.0 - math.exp(-0.1))
        self.assertAlmostEqual(v_next_1, expected_1, places=6)

        # Zero R or zero C should instantly return 0.0
        self.assertEqual(
            solve_rc_branch_voltage_step(0.05, 10.0, 0.0, 1000.0, 1.0),
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
