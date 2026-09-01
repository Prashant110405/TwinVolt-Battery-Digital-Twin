"""Mathematical Utilities and Numerical ODE Integrators.

Provides deterministic mathematical helpers, numerical stability guards,
and explicit numerical integrators (Explicit Euler, Runge-Kutta 4th Order / RK4).
"""

from collections.abc import Callable
import math
from typing import Any, Mapping, Protocol

from src.models.exceptions import NumericalInstabilityError


def is_finite_number(value: Any) -> bool:
    """Returns True if value is an int or float that is neither NaN nor Infinite."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return not (math.isnan(value) or math.isinf(value))


def assert_finite(value: float, name: str = "value") -> None:
    """Raises NumericalInstabilityError if value is NaN, Inf, or non-numeric."""
    if not is_finite_number(value):
        raise NumericalInstabilityError(
            f"Numerical instability detected: '{name}' is non-finite (got {value}).",
            details={"variable": name, "value": value},
        )


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamps a finite float value between min_val and max_val inclusive."""
    assert_finite(value, "value")
    assert_finite(min_val, "min_val")
    assert_finite(max_val, "max_val")
    if min_val > max_val:
        raise ValueError(f"min_val ({min_val}) cannot be greater than max_val ({max_val}).")
    return max(min_val, min(value, max_val))


def calculate_coulomb_soc_step(
    current_a: float,
    dt_s: float,
    nominal_capacity_ah: float,
    coulombic_efficiency: float = 1.0,
) -> float:
    """Calculates the change in State of Charge ($dSOC$) over time step $dt$.

    Sign convention:
    - Current $I > 0$: Discharge $\\rightarrow$ SOC decreases ($dSOC < 0$).
    - Current $I < 0$: Charge $\\rightarrow$ SOC increases ($dSOC > 0$).
    - Current $I = 0$: Rest $\\rightarrow dSOC = 0$.

    Args:
        current_a: Current in Amperes (>0 discharge, <0 charge).
        dt_s: Step duration in seconds (>0).
        nominal_capacity_ah: Nominal capacity in Ampere-hours (>0).
        coulombic_efficiency: Coulombic charging efficiency factor (typically 0.95 - 1.0).

    Returns:
        dSOC: Incremental change in SOC fraction.
    """
    assert_finite(current_a, "current_a")
    assert_finite(dt_s, "dt_s")
    assert_finite(nominal_capacity_ah, "nominal_capacity_ah")

    if nominal_capacity_ah <= 0:
        raise ValueError(f"nominal_capacity_ah must be positive, got {nominal_capacity_ah}.")

    capacity_coulombs = nominal_capacity_ah * 3600.0
    charge_transferred_coulombs = current_a * dt_s

    # Apply coulombic efficiency only when charging (I < 0)
    if current_a < 0:
        eff = max(0.0, coulombic_efficiency)
        delta_soc = -(charge_transferred_coulombs * eff) / capacity_coulombs
    else:
        delta_soc = -charge_transferred_coulombs / capacity_coulombs

    assert_finite(delta_soc, "delta_soc")
    return delta_soc


class NumericalIntegrator(Protocol):
    """Protocol for scalar ODE integrators: dy/dt = f(t, y)."""

    def step(
        self,
        f: Callable[[float, float], float],
        y: float,
        t: float,
        dt: float,
    ) -> float:
        """Propagates state y at time t across step dt."""
        ...


class ExplicitEulerIntegrator:
    """Explicit 1st-order Euler numerical integrator: y[k+1] = y[k] + dt * f(t_k, y_k)."""

    def step(
        self,
        f: Callable[[float, float], float],
        y: float,
        t: float,
        dt: float,
    ) -> float:
        """Advances scalar ODE by dt using forward Euler."""
        assert_finite(y, "y")
        assert_finite(t, "t")
        assert_finite(dt, "dt")
        if dt <= 0:
            raise ValueError(f"dt must be positive, got {dt}.")

        derivative = f(t, y)
        assert_finite(derivative, "derivative")

        y_next = y + dt * derivative
        assert_finite(y_next, "y_next")
        return y_next


class RungeKutta4Integrator:
    """Classical 4th-order Runge-Kutta numerical ODE integrator."""

    def step(
        self,
        f: Callable[[float, float], float],
        y: float,
        t: float,
        dt: float,
    ) -> float:
        """Advances scalar ODE by dt using classical RK4."""
        assert_finite(y, "y")
        assert_finite(t, "t")
        assert_finite(dt, "dt")
        if dt <= 0:
            raise ValueError(f"dt must be positive, got {dt}.")

        k1 = f(t, y)
        assert_finite(k1, "k1")

        k2 = f(t + 0.5 * dt, y + 0.5 * dt * k1)
        assert_finite(k2, "k2")

        k3 = f(t + 0.5 * dt, y + 0.5 * dt * k2)
        assert_finite(k3, "k3")

        k4 = f(t + dt, y + dt * k3)
        assert_finite(k4, "k4")

        y_next = y + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        assert_finite(y_next, "y_next")
        return y_next


def solve_rc_branch_voltage_step(
    v_rc_current: float,
    current_a: float,
    resistance_r_ohm: float,
    capacitance_c_farad: float,
    dt_s: float,
) -> float:
    """Analytically solves discrete 1-RC branch voltage step:

    Equation: dV_rc/dt = (I / C) - (V_rc / (R * C))
    Exact Solution: V_rc[k+1] = V_rc[k] * exp(-dt / tau) + I * R * (1 - exp(-dt / tau))

    Where tau = R * C.
    If R == 0 or C == 0, V_rc instantly equals 0.0.
    """
    assert_finite(v_rc_current, "v_rc_current")
    assert_finite(current_a, "current_a")
    assert_finite(resistance_r_ohm, "resistance_r_ohm")
    assert_finite(capacitance_c_farad, "capacitance_c_farad")
    assert_finite(dt_s, "dt_s")

    if resistance_r_ohm <= 0.0 or capacitance_c_farad <= 0.0:
        return 0.0

    tau_s = resistance_r_ohm * capacitance_c_farad
    decay_factor = math.exp(-dt_s / tau_s)

    v_rc_next = (v_rc_current * decay_factor) + (current_a * resistance_r_ohm * (1.0 - decay_factor))
    assert_finite(v_rc_next, "v_rc_next")
    return v_rc_next
