"""Semi-Empirical Battery Degradation Modeling.

Provides parametric calendar aging (Arrhenius SEI growth) and cycling aging formulations
for capacity fade and internal resistance growth.
"""

from dataclasses import dataclass
import math
from typing import Optional, Protocol, runtime_checkable

from src.analytics.types import DegradationMetrics, StressAccumulatorState

UNIVERSAL_GAS_CONSTANT_R = 8.31446261815324  # J / (mol * K)
REFERENCE_TEMPERATURE_KELVIN = 298.15         # 25.0 °C in Kelvin


@dataclass(frozen=True)
class DegradationParameters:
    """Configurable parameters for empirical battery aging models.

    All coefficients use explicit SI units and standard reference conditions (25°C).
    """

    # Calendar aging parameters
    calendar_ref_rate_per_day: float = 1.0e-4          # [1/day] Base calendar capacity loss rate at 25°C
    calendar_activation_energy_j_mol: float = 22400.0   # [J/mol] Arrhenius activation energy for SEI growth
    calendar_time_exponent: float = 0.5                 # [-] Diffusion-limited parabolic growth exponent (t^0.5)

    # Cycling aging parameters
    cycling_ref_rate_per_efc: float = 2.0e-4           # [1/EFC] Base cycling capacity loss rate at 25°C
    cycling_activation_energy_j_mol: float = 20000.0    # [J/mol] Arrhenius activation energy for cycling degradation

    # Resistance growth parameters
    resistance_growth_rate_per_efc: float = 3.0e-4      # [1/EFC] Fractional series resistance growth per EFC
    resistance_growth_calendar_per_day: float = 1.0e-4  # [1/day] Fractional series resistance growth per calendar day
    eol_resistance_growth_limit: float = 1.0            # [-] Fractional growth defining End of Life (1.0 = +100% R0)

    def __post_init__(self) -> None:
        if self.calendar_ref_rate_per_day < 0.0:
            raise ValueError("calendar_ref_rate_per_day must be non-negative.")
        if self.cycling_ref_rate_per_efc < 0.0:
            raise ValueError("cycling_ref_rate_per_efc must be non-negative.")
        if self.calendar_time_exponent <= 0.0 or self.calendar_time_exponent > 1.0:
            raise ValueError("calendar_time_exponent must be in range (0.0, 1.0].")
        if self.eol_resistance_growth_limit <= 0.0:
            raise ValueError("eol_resistance_growth_limit must be strictly positive.")


@runtime_checkable
class DegradationModel(Protocol):
    """Protocol for battery capacity and resistance degradation models."""

    def evaluate(
        self,
        stress: StressAccumulatorState,
        temperature_c: float = 25.0,
        avg_soc: float = 0.5,
    ) -> DegradationMetrics:
        """Evaluates modeled capacity fade and resistance growth.

        Args:
            stress: Current cumulative stress state.
            temperature_c: Cell/pack temperature in Celsius.
            avg_soc: Mean State of Charge in range [0.0, 1.0].

        Returns:
            DegradationMetrics with capacity fade and resistance growth fractions.
        """
        ...


class ArrheniusSEIEmpiricalDegradationModel:
    """Universal semi-empirical Arrhenius SEI degradation model.

    Formulation:
    1. Calendar Aging (Square root of time & Arrhenius temperature dependency):
       k_cal(T) = k_cal_ref * exp(-E_a_cal / R * (1/T_K - 1/T_ref))
       fade_cal = k_cal(T) * (days)^z

    2. Cycling Aging (Equivalent full cycles & Arrhenius temperature dependency):
       k_cyc(T) = k_cyc_ref * exp(-E_a_cyc / R * (1/T_K - 1/T_ref))
       fade_cyc = k_cyc(T) * EFC

    3. Total Capacity Fade:
       fade_total = min(1.0, fade_cal + fade_cyc)

    4. Resistance Growth:
       growth_R = (days * k_R_cal) + (EFC * k_R_cyc)
    """

    def __init__(self, parameters: Optional[DegradationParameters] = None) -> None:
        self.params = parameters or DegradationParameters()

    def evaluate(
        self,
        stress: StressAccumulatorState,
        temperature_c: float = 25.0,
        avg_soc: float = 0.5,
    ) -> DegradationMetrics:
        """Evaluates degradation metrics based on accumulated stress and temperature."""
        temp_k = max(200.0, temperature_c + 273.15)
        temp_factor_cal = math.exp(
            -(self.params.calendar_activation_energy_j_mol / UNIVERSAL_GAS_CONSTANT_R)
            * ((1.0 / temp_k) - (1.0 / REFERENCE_TEMPERATURE_KELVIN))
        )
        temp_factor_cyc = math.exp(
            -(self.params.cycling_activation_energy_j_mol / UNIVERSAL_GAS_CONSTANT_R)
            * ((1.0 / temp_k) - (1.0 / REFERENCE_TEMPERATURE_KELVIN))
        )

        # Elapsed calendar days
        elapsed_days = max(0.0, stress.total_elapsed_time_s / 86400.0)

        # Calendar capacity loss
        cal_fade = (
            self.params.calendar_ref_rate_per_day
            * temp_factor_cal
            * (elapsed_days ** self.params.calendar_time_exponent)
        )

        # Cycling capacity loss
        cyc_fade = (
            self.params.cycling_ref_rate_per_efc
            * temp_factor_cyc
            * max(0.0, stress.equivalent_full_cycles)
        )

        total_fade = min(1.0, max(0.0, cal_fade + cyc_fade))

        # Resistance growth fraction (Delta R0 / R0_nominal)
        r_growth = max(
            0.0,
            (elapsed_days * self.params.resistance_growth_calendar_per_day)
            + (stress.equivalent_full_cycles * self.params.resistance_growth_rate_per_efc),
        )

        return DegradationMetrics(
            calendar_capacity_fade_fraction=min(1.0, max(0.0, cal_fade)),
            cycling_capacity_fade_fraction=min(1.0, max(0.0, cyc_fade)),
            total_capacity_fade_fraction=total_fade,
            resistance_growth_fraction=r_growth,
        )
