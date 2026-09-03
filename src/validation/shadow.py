"""Isolated Prospective ECM Branch Simulator for Parameter Validation.

Simulates candidate IdentifiedParameterSet equivalent circuit models in an isolated
shadow context without mutating live Digital Twin instances, models, or EKF states.
Ensures strict initial polarization state parity with the nominal model.
"""

import math
from typing import Optional


class ProspectiveECMBranchSimulator:
    """Isolated 1-RC Thevenin Branch Simulation Engine for prospective parameter validation."""

    def __init__(self) -> None:
        self._v_pol: float = 0.0
        self._is_initialized: bool = False

    @property
    def polarization_voltage_v(self) -> float:
        """Current internal shadow polarization overpotential [V]."""
        return self._v_pol

    @property
    def is_initialized(self) -> bool:
        """Whether the shadow branch has been initialized."""
        return self._is_initialized

    def initialize(self, initial_polarization_v: float = 0.0) -> None:
        """Initializes internal polarization state to match the nominal model's initial state."""
        if math.isnan(initial_polarization_v) or math.isinf(initial_polarization_v):
            self._v_pol = 0.0
        else:
            self._v_pol = float(initial_polarization_v)
        self._is_initialized = True

    def step(
        self,
        v_oc: float,
        current_a: float,
        dt_s: float,
        r0_ohm: float,
        r1_ohm: Optional[float] = None,
        c1_farad: Optional[float] = None,
        initial_polarization_v: Optional[float] = None,
    ) -> float:
        """Propagates prospective 1-RC model across step dt and computes terminal voltage.

        Equations (matching exact discrete ECM solution in solve_rc_branch_voltage_step):
        - Polarization Evolution: Vp[k+1] = Vp[k] * exp(-dt/tau) + I[k] * R1 * (1 - exp(-dt/tau))
        - Terminal Voltage: Vterm[k] = Voc[k] - I[k] * R0 - Vp[k+1]

        Args:
            v_oc: Open circuit voltage in Volts (provided directly from validated model output).
            current_a: Pack current in Amperes (>0 discharge, <0 charge).
            dt_s: Time step interval in seconds (>0).
            r0_ohm: Candidate series ohmic resistance in Ohms.
            r1_ohm: Optional candidate polarization resistance in Ohms.
            c1_farad: Optional candidate polarization capacitance in Farads.
            initial_polarization_v: Optional initial polarization voltage to align with nominal model.

        Returns:
            Simulated prospective terminal voltage V_term in Volts.
        """
        if not self._is_initialized:
            init_v = initial_polarization_v if initial_polarization_v is not None else 0.0
            self.initialize(initial_polarization_v=init_v)

        if dt_s <= 0.0:
            dt_s = 1.0

        # Polarization update across step dt matching discrete solve_rc_branch_voltage_step
        if r1_ohm is not None and c1_farad is not None and r1_ohm > 0.0 and c1_farad > 0.0:
            tau = r1_ohm * c1_farad
            decay_factor = math.exp(-dt_s / tau)
            v_pol_next = (self._v_pol * decay_factor) + (current_a * r1_ohm * (1.0 - decay_factor))
        else:
            v_pol_next = 0.0

        # Terminal voltage equation
        v_term = v_oc - (current_a * r0_ohm) - v_pol_next
        self._v_pol = v_pol_next
        return v_term

    def reset(self) -> None:
        """Resets shadow simulator state and polarization voltage."""
        self._v_pol = 0.0
        self._is_initialized = False
