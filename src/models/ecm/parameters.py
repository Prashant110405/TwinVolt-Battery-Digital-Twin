"""Equivalent Circuit Model (ECM) Parameter Containers.

Defines strongly-typed, immutable parameter specifications for RC branches,
internal resistances, and electro-thermal parameters.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence

from src.models.exceptions import InvalidModelParametersError
from src.models.math import assert_finite
from src.models.types import ModelParameters


@dataclass(frozen=True)
class RCBranchParameters:
    """Parameters for a single parallel Resistor-Capacitor ($R_i \\parallel C_i$) polarization branch.

    All physical quantities use explicit SI units:
    - resistance_r_ohm: Polarization resistance in Ohms (>= 0.0).
    - capacitance_c_farad: Polarization capacitance in Farads (>= 0.0).
    """

    resistance_r_ohm: float
    capacitance_c_farad: float

    def __post_init__(self) -> None:
        assert_finite(self.resistance_r_ohm, "resistance_r_ohm")
        assert_finite(self.capacitance_c_farad, "capacitance_c_farad")
        if self.resistance_r_ohm < 0.0:
            raise InvalidModelParametersError(
                f"resistance_r_ohm cannot be negative, got {self.resistance_r_ohm}."
            )
        if self.capacitance_c_farad < 0.0:
            raise InvalidModelParametersError(
                f"capacitance_c_farad cannot be negative, got {self.capacitance_c_farad}."
            )

    @property
    def resistance_r_mohm(self) -> float:
        """Polarization resistance in milli-Ohms ($m\\Omega$)."""
        return self.resistance_r_ohm * 1000.0

    @property
    def time_constant_tau_s(self) -> float:
        """Branch time constant $\\tau_i = R_i \\cdot C_i$ in seconds."""
        return self.resistance_r_ohm * self.capacitance_c_farad

    def to_dict(self) -> dict[str, Any]:
        """Serializes branch parameters to dictionary."""
        return {
            "resistance_r_ohm": self.resistance_r_ohm,
            "resistance_r_mohm": self.resistance_r_mohm,
            "capacitance_c_farad": self.capacitance_c_farad,
            "time_constant_tau_s": self.time_constant_tau_s,
        }


@dataclass(frozen=True)
class GenericECMParameters(ModelParameters):
    """Parameter container for generic N-RC Equivalent Circuit Models.

    Supports 0-RC ($R_{int}$), 1-RC (Thevenin), 2-RC (Dual Polarization), and N-RC topologies.
    """

    series_resistance_r0_ohm: float = 0.025
    rc_branches: tuple[RCBranchParameters, ...] = ()
    coulombic_efficiency: float = 1.0
    entropic_coefficient_v_per_k: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        assert_finite(self.series_resistance_r0_ohm, "series_resistance_r0_ohm")
        if self.series_resistance_r0_ohm < 0.0:
            raise InvalidModelParametersError(
                f"series_resistance_r0_ohm cannot be negative, got {self.series_resistance_r0_ohm}."
            )

        assert_finite(self.coulombic_efficiency, "coulombic_efficiency")
        if not (0.0 < self.coulombic_efficiency <= 1.0):
            raise InvalidModelParametersError(
                f"coulombic_efficiency must be in (0.0, 1.0], got {self.coulombic_efficiency}."
            )

        assert_finite(self.entropic_coefficient_v_per_k, "entropic_coefficient_v_per_k")

        for idx, branch in enumerate(self.rc_branches):
            if not isinstance(branch, RCBranchParameters):
                raise InvalidModelParametersError(
                    f"rc_branches[{idx}] must be an RCBranchParameters instance, got {type(branch).__name__}."
                )

    @property
    def series_resistance_r0_mohm(self) -> float:
        """Series internal resistance in milli-Ohms ($m\\Omega$)."""
        return self.series_resistance_r0_ohm * 1000.0

    @property
    def branch_count(self) -> int:
        """Number of RC polarization branches ($N$)."""
        return len(self.rc_branches)

    @property
    def total_polarization_resistance_ohm(self) -> float:
        """Sum of all polarization branch resistances $\\sum R_i$ in Ohms."""
        return sum(b.resistance_r_ohm for b in self.rc_branches)

    @property
    def total_dc_resistance_ohm(self) -> float:
        """Total equivalent steady-state DC resistance $R_0 + \\sum R_i$ in Ohms."""
        return self.series_resistance_r0_ohm + self.total_polarization_resistance_ohm

    @property
    def total_dc_resistance_mohm(self) -> float:
        """Total equivalent steady-state DC resistance in milli-Ohms ($m\\Omega$)."""
        return self.total_dc_resistance_ohm * 1000.0

    def to_dict(self) -> dict[str, Any]:
        """Serializes ECM parameters to dictionary."""
        base_dict = super().to_dict()
        base_dict.update({
            "series_resistance_r0_ohm": self.series_resistance_r0_ohm,
            "series_resistance_r0_mohm": self.series_resistance_r0_mohm,
            "branch_count": self.branch_count,
            "rc_branches": [b.to_dict() for b in self.rc_branches],
            "total_polarization_resistance_ohm": self.total_polarization_resistance_ohm,
            "total_dc_resistance_ohm": self.total_dc_resistance_ohm,
            "total_dc_resistance_mohm": self.total_dc_resistance_mohm,
            "coulombic_efficiency": self.coulombic_efficiency,
            "entropic_coefficient_v_per_k": self.entropic_coefficient_v_per_k,
        })
        return base_dict
