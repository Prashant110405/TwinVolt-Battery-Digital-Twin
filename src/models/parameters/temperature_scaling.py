"""Temperature Scaling and Arrhenius Kinetics Parameter Engine.

Models the electro-chemical temperature dependence of internal resistance,
polarization time constants, and usable charge capacity across thermal operating regimes.
"""

from dataclasses import dataclass
import math
from typing import Any, Mapping, Optional

from src.models.exceptions import InvalidModelParametersError, InvalidModelStateError
from src.models.math import assert_finite, clamp
from src.models.types import ABSOLUTE_ZERO_CELSIUS

# Universal Gas Constant R_g in J/(mol * K)
MOLAR_GAS_CONSTANT_J_PER_MOL_K = 8.31446261815324
DEFAULT_REFERENCE_TEMPERATURE_C = 25.0


@dataclass(frozen=True)
class TemperatureScaling:
    r"""Mathematical container for electro-thermal temperature scaling parameters.

    Governs thermal activation and capacity derating using SI units:
    - activation_energy_j_per_mol: Arrhenius activation energy $E_a$ in J/mol ($\ge 0.0$).
      Typical values: NMC ~25,000 J/mol, LFP ~30,000 J/mol, LTO ~18,000 J/mol.
    - reference_temperature_c: Baseline reference temperature in Celsius (default: 25.0°C).
    - low_temp_resistance_multiplier: Multiplier factor for sub-zero temperature impedance rise.
    - capacity_derating_fraction_per_k: Usable capacity loss rate below reference temp ($\ge 0.0$).
    - min_capacity_retention_fraction: Minimum usable capacity floor at extreme cold in range [0.0, 1.0].
    """

    activation_energy_j_per_mol: float = 25000.0
    reference_temperature_c: float = DEFAULT_REFERENCE_TEMPERATURE_C
    low_temp_resistance_multiplier: float = 1.0
    capacity_derating_fraction_per_k: float = 0.006
    min_capacity_retention_fraction: float = 0.40

    def __post_init__(self) -> None:
        assert_finite(self.activation_energy_j_per_mol, "activation_energy_j_per_mol")
        assert_finite(self.reference_temperature_c, "reference_temperature_c")
        assert_finite(self.low_temp_resistance_multiplier, "low_temp_resistance_multiplier")
        assert_finite(self.capacity_derating_fraction_per_k, "capacity_derating_fraction_per_k")
        assert_finite(self.min_capacity_retention_fraction, "min_capacity_retention_fraction")

        if self.activation_energy_j_per_mol < 0.0:
            raise InvalidModelParametersError("activation_energy_j_per_mol must be non-negative (>= 0.0 J/mol).")
        if self.reference_temperature_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidModelParametersError(f"reference_temperature_c below absolute zero: {self.reference_temperature_c}°C.")
        if self.low_temp_resistance_multiplier <= 0.0:
            raise InvalidModelParametersError("low_temp_resistance_multiplier must be strictly positive (> 0.0).")
        if self.capacity_derating_fraction_per_k < 0.0:
            raise InvalidModelParametersError("capacity_derating_fraction_per_k must be non-negative (>= 0.0).")
        if not (0.0 <= self.min_capacity_retention_fraction <= 1.0):
            raise InvalidModelParametersError(
                f"min_capacity_retention_fraction must be in range [0.0, 1.0], got {self.min_capacity_retention_fraction}."
            )

    @property
    def reference_temperature_k(self) -> float:
        """Reference temperature in Kelvin."""
        return self.reference_temperature_c + 273.15

    # --------------------------------------------------------------------------
    # Thermal Scaling Calculations
    # --------------------------------------------------------------------------
    def get_resistance_multiplier(self, temperature_c: float) -> float:
        """Calculates temperature-dependent resistance scaling factor $R(T) / R_{ref}$.

        Evaluates the Arrhenius equation:
            multiplier = exp( (E_a / R_g) * (1 / T_K - 1 / T_ref_K) )
        with low-temperature enhancement below 0°C.
        """
        assert_finite(temperature_c, "temperature_c")
        if temperature_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidModelStateError(f"temperature_c below absolute zero: {temperature_c}°C.")

        t_k = temperature_c + 273.15
        t_ref_k = self.reference_temperature_k

        # Standard Arrhenius factor
        exponent = (self.activation_energy_j_per_mol / MOLAR_GAS_CONSTANT_J_PER_MOL_K) * (
            (1.0 / t_k) - (1.0 / t_ref_k)
        )
        # Numerical safeguard against extreme exponent overflow
        clamped_exponent = clamp(exponent, -20.0, 20.0)
        arrhenius_factor = math.exp(clamped_exponent)

        # Apply sub-zero enhancement if temperature < 0.0 C
        if temperature_c < 0.0 and self.low_temp_resistance_multiplier > 1.0:
            sub_zero_delta = -temperature_c
            low_temp_boost = 1.0 + (self.low_temp_resistance_multiplier - 1.0) * (1.0 - math.exp(-sub_zero_delta / 15.0))
            arrhenius_factor *= low_temp_boost

        assert_finite(arrhenius_factor, "resistance_multiplier")
        return arrhenius_factor

    def scale_resistance(self, base_resistance_ohm: float, temperature_c: float) -> float:
        """Applies thermal scaling to an electrical resistance (R0 or Ri).

        Args:
            base_resistance_ohm: Baseline resistance at reference temperature in Ohms (> 0.0).
            temperature_c: Current cell core temperature in Celsius (> -273.15°C).

        Returns:
            Adjusted resistance $R(T)$ in Ohms.
        """
        assert_finite(base_resistance_ohm, "base_resistance_ohm")
        if base_resistance_ohm < 0.0:
            raise InvalidModelParametersError("base_resistance_ohm cannot be negative.")
        return base_resistance_ohm * self.get_resistance_multiplier(temperature_c)

    def get_capacity_retention_fraction(self, temperature_c: float) -> float:
        """Calculates temperature-dependent usable capacity retention fraction in range [0.0, 1.0].

        Cold temperatures reduce accessible lithium diffusion capacity:
            retention = clamp(1.0 - derating * (T_ref - T), min_retention, 1.0)
        """
        assert_finite(temperature_c, "temperature_c")
        if temperature_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidModelStateError(f"temperature_c below absolute zero: {temperature_c}°C.")

        if temperature_c >= self.reference_temperature_c:
            return 1.0

        temp_drop = self.reference_temperature_c - temperature_c
        retention = 1.0 - (self.capacity_derating_fraction_per_k * temp_drop)
        return clamp(retention, self.min_capacity_retention_fraction, 1.0)

    def scale_capacity(self, base_capacity_ah: float, temperature_c: float) -> float:
        """Applies thermal scaling to nominal capacity.

        Args:
            base_capacity_ah: Baseline charge capacity at reference temperature in Ampere-hours (> 0.0).
            temperature_c: Current cell core temperature in Celsius (> -273.15°C).

        Returns:
            Usable charge capacity $Q(T)$ in Ampere-hours.
        """
        assert_finite(base_capacity_ah, "base_capacity_ah")
        if base_capacity_ah <= 0.0:
            raise InvalidModelParametersError("base_capacity_ah must be strictly positive.")
        return base_capacity_ah * self.get_capacity_retention_fraction(temperature_c)

    # --------------------------------------------------------------------------
    # Serialization
    # --------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Serializes temperature scaling parameters to dictionary."""
        return {
            "activation_energy_j_per_mol": self.activation_energy_j_per_mol,
            "reference_temperature_c": self.reference_temperature_c,
            "low_temp_resistance_multiplier": self.low_temp_resistance_multiplier,
            "capacity_derating_fraction_per_k": self.capacity_derating_fraction_per_k,
            "min_capacity_retention_fraction": self.min_capacity_retention_fraction,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TemperatureScaling":
        """Reconstructs TemperatureScaling from dictionary serialization."""
        return cls(
            activation_energy_j_per_mol=data.get("activation_energy_j_per_mol", 25000.0),
            reference_temperature_c=data.get("reference_temperature_c", DEFAULT_REFERENCE_TEMPERATURE_C),
            low_temp_resistance_multiplier=data.get("low_temp_resistance_multiplier", 1.0),
            capacity_derating_fraction_per_k=data.get("capacity_derating_fraction_per_k", 0.006),
            min_capacity_retention_fraction=data.get("min_capacity_retention_fraction", 0.40),
        )
