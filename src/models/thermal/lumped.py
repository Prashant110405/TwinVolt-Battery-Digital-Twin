"""0D Lumped-Parameter Thermal Model for Battery Heat Evolution.

Implements the standard 0D lumped heat equation:
    C_th * dT/dt = Q_generation - (T - T_amb) / R_th
with analytical discrete-time integration.
"""

import math
from typing import Any, Optional

from src.models.exceptions import InvalidModelParametersError, InvalidModelStateError
from src.models.math import assert_finite
from src.models.types import ABSOLUTE_ZERO_CELSIUS


class LumpedThermalModel:
    """0D Lumped-capacitance battery thermal model.

    Models cell/module bulk temperature dynamics:
        C_th * dT/dt = Q_gen - hA * (T - T_amb)

    All physical quantities use explicit SI units:
    - thermal_capacitance_j_per_k: Bulk heat capacity C_th in J/K (> 0.0).
    - convective_heat_transfer_w_per_k: Heat dissipation coefficient hA in W/K (> 0.0).
    - thermal_resistance_k_per_w: R_th = 1 / (hA) in K/W (> 0.0).
    """

    def __init__(
        self,
        thermal_capacitance_j_per_k: float,
        convective_heat_transfer_w_per_k: Optional[float] = None,
        thermal_resistance_k_per_w: Optional[float] = None,
    ) -> None:
        assert_finite(thermal_capacitance_j_per_k, "thermal_capacitance_j_per_k")
        if thermal_capacitance_j_per_k <= 0.0:
            raise InvalidModelParametersError(
                f"thermal_capacitance_j_per_k must be positive, got {thermal_capacitance_j_per_k}."
            )
        self._c_th = float(thermal_capacitance_j_per_k)

        if convective_heat_transfer_w_per_k is not None and thermal_resistance_k_per_w is not None:
            raise InvalidModelParametersError(
                "Specify either convective_heat_transfer_w_per_k or thermal_resistance_k_per_w, not both."
            )

        if thermal_resistance_k_per_w is not None:
            assert_finite(thermal_resistance_k_per_w, "thermal_resistance_k_per_w")
            if thermal_resistance_k_per_w <= 0.0:
                raise InvalidModelParametersError(
                    f"thermal_resistance_k_per_w must be positive, got {thermal_resistance_k_per_w}."
                )
            self._r_th = float(thermal_resistance_k_per_w)
            self._ha = 1.0 / self._r_th
        elif convective_heat_transfer_w_per_k is not None:
            assert_finite(convective_heat_transfer_w_per_k, "convective_heat_transfer_w_per_k")
            if convective_heat_transfer_w_per_k <= 0.0:
                raise InvalidModelParametersError(
                    f"convective_heat_transfer_w_per_k must be positive, got {convective_heat_transfer_w_per_k}."
                )
            self._ha = float(convective_heat_transfer_w_per_k)
            self._r_th = 1.0 / self._ha
        else:
            # Default to 1.0 W/K (1.0 K/W)
            self._ha = 1.0
            self._r_th = 1.0

        self._tau_th = self._c_th * self._r_th

    @property
    def thermal_capacitance_j_per_k(self) -> float:
        """Thermal capacitance C_th in J/K."""
        return self._c_th

    @property
    def convective_heat_transfer_w_per_k(self) -> float:
        """Convective heat transfer coefficient hA in W/K."""
        return self._ha

    @property
    def thermal_resistance_k_per_w(self) -> float:
        """Thermal resistance R_th in K/W."""
        return self._r_th

    @property
    def thermal_time_constant_s(self) -> float:
        """Thermal time constant tau_th = R_th * C_th in seconds."""
        return self._tau_th

    def step(
        self,
        heat_generation_w: float,
        dt_s: float,
        ambient_temperature_c: float,
        current_temp_c: float,
    ) -> float:
        """Propagates thermal state across discrete step dt_s using exact analytical solution.

        Args:
            heat_generation_w: Instantaneous thermal generation rate in Watts (>= 0.0).
            dt_s: Time step in seconds (> 0.0).
            ambient_temperature_c: Ambient environment temperature in Celsius (> -273.15°C).
            current_temp_c: Current core/bulk temperature in Celsius (> -273.15°C).

        Returns:
            next_temperature_c: Updated bulk temperature in Celsius.
        """
        assert_finite(heat_generation_w, "heat_generation_w")
        assert_finite(dt_s, "dt_s")
        assert_finite(ambient_temperature_c, "ambient_temperature_c")
        assert_finite(current_temp_c, "current_temp_c")

        if dt_s <= 0.0:
            raise ValueError(f"dt_s must be positive, got {dt_s}.")
        if heat_generation_w < 0.0:
            raise ValueError(f"heat_generation_w cannot be negative, got {heat_generation_w}.")
        if ambient_temperature_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidModelStateError(f"ambient_temperature_c below absolute zero: {ambient_temperature_c}°C.")
        if current_temp_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidModelStateError(f"current_temp_c below absolute zero: {current_temp_c}°C.")

        # Exact analytical integration over [0, dt]:
        # T(dt) = T_amb + (T0 - T_amb) * exp(-dt / tau) + Q_gen * R_th * (1 - exp(-dt / tau))
        decay = math.exp(-dt_s / self._tau_th)
        temp_delta_ambient = current_temp_c - ambient_temperature_c
        steady_state_temp_rise = heat_generation_w * self._r_th

        next_temp_c = ambient_temperature_c + (temp_delta_ambient * decay) + (steady_state_temp_rise * (1.0 - decay))
        assert_finite(next_temp_c, "next_temp_c")
        return next_temp_c

    def to_dict(self) -> dict[str, Any]:
        """Serializes thermal model parameters to dictionary."""
        return {
            "thermal_capacitance_j_per_k": self._c_th,
            "convective_heat_transfer_w_per_k": self._ha,
            "thermal_resistance_k_per_w": self._r_th,
            "thermal_time_constant_s": self._tau_th,
        }
