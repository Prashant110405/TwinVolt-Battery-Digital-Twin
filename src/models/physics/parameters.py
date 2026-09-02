"""Physics-Based Electrochemical Model Parameters.

Defines parameter containers for PDE-based models (SPM, SPMe, DFN),
electrochemical constants, geometry properties, and solver tolerances.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional

from src.models.exceptions import InvalidModelParametersError
from src.models.math import assert_finite
from src.models.types import ModelParameters

SUPPORTED_PHYSICS_MODELS = {"SPM", "SPME", "DFN", "MSMR"}
SUPPORTED_THERMAL_COUPLINGS = {"ISOTHERMAL", "LUMPED", "COUPLED"}


@dataclass(frozen=True)
class PhysicsModelParameters(ModelParameters):
    """Parameter container for high-fidelity electrochemical models.

    All physical parameters use explicit SI units:
    - model_type: Electrochemical formulation ('SPM', 'SPMe', 'DFN', 'MSMR').
    - parameter_set_name: Canonical parameter set (e.g., 'Chen2020', 'Marquis2019', 'Prada2013').
    - electrode_area_m2: Total active electrode cross-sectional area in m^2 (> 0.0).
    - particle_radius_pos_m: Positive active material particle radius in meters (> 0.0).
    - particle_radius_neg_m: Negative active material particle radius in meters (> 0.0).
    - thickness_pos_m: Positive electrode coating thickness in meters (> 0.0).
    - thickness_neg_m: Negative electrode coating thickness in meters (> 0.0).
    - thickness_sep_m: Separator thickness in meters (> 0.0).
    - porosity_pos: Positive electrode volume porosity fraction in range (0.0, 1.0).
    - porosity_neg: Negative electrode volume porosity fraction in range (0.0, 1.0).
    - porosity_sep: Separator volume porosity fraction in range (0.0, 1.0).
    - solid_diffusivity_pos_m2_per_s: Positive solid-phase Li diffusivity in m^2/s (> 0.0).
    - solid_diffusivity_neg_m2_per_s: Negative solid-phase Li diffusivity in m^2/s (> 0.0).
    - electrolyte_conductivity_s_per_m: Bulk electrolyte ionic conductivity in S/m (> 0.0).
    - c_max_pos_mol_per_m3: Theoretical maximum Li concentration in positive electrode in mol/m^3 (> 0.0).
    - c_max_neg_mol_per_m3: Theoretical maximum Li concentration in negative electrode in mol/m^3 (> 0.0).
    - thermal_coupling: Thermal coupling paradigm ('ISOTHERMAL', 'LUMPED', 'COUPLED').
    - solver_rel_tol: Relative solver tolerance (> 0.0).
    - solver_abs_tol: Absolute solver tolerance (> 0.0).
    """

    model_type: str = "SPM"
    parameter_set_name: str = "Chen2020"
    electrode_area_m2: Optional[float] = None
    particle_radius_pos_m: Optional[float] = None
    particle_radius_neg_m: Optional[float] = None
    thickness_pos_m: Optional[float] = None
    thickness_neg_m: Optional[float] = None
    thickness_sep_m: Optional[float] = None
    porosity_pos: Optional[float] = None
    porosity_neg: Optional[float] = None
    porosity_sep: Optional[float] = None
    solid_diffusivity_pos_m2_per_s: Optional[float] = None
    solid_diffusivity_neg_m2_per_s: Optional[float] = None
    electrolyte_conductivity_s_per_m: Optional[float] = None
    c_max_pos_mol_per_m3: Optional[float] = None
    c_max_neg_mol_per_m3: Optional[float] = None
    thermal_coupling: str = "LUMPED"
    solver_rel_tol: float = 1e-6
    solver_abs_tol: float = 1e-6

    def __post_init__(self) -> None:
        super().__post_init__()
        normalized_model = self.model_type.upper().strip()
        if normalized_model not in {m.upper() for m in SUPPORTED_PHYSICS_MODELS}:
            raise InvalidModelParametersError(
                f"Unsupported physics model_type '{self.model_type}'. Supported: {sorted(SUPPORTED_PHYSICS_MODELS)}.",
                details={"model_type": self.model_type},
            )

        if not self.parameter_set_name.strip():
            raise InvalidModelParametersError("parameter_set_name cannot be empty.")

        normalized_thermal = self.thermal_coupling.upper().strip()
        if normalized_thermal not in SUPPORTED_THERMAL_COUPLINGS:
            raise InvalidModelParametersError(
                f"Unsupported thermal_coupling '{self.thermal_coupling}'. Supported: {sorted(SUPPORTED_THERMAL_COUPLINGS)}.",
                details={"thermal_coupling": self.thermal_coupling},
            )

        # Validate solver tolerances
        assert_finite(self.solver_rel_tol, "solver_rel_tol")
        assert_finite(self.solver_abs_tol, "solver_abs_tol")
        if self.solver_rel_tol <= 0.0:
            raise InvalidModelParametersError("solver_rel_tol must be strictly positive.")
        if self.solver_abs_tol <= 0.0:
            raise InvalidModelParametersError("solver_abs_tol must be strictly positive.")

        # Validate positive geometric / transport properties
        positive_checks = [
            ("electrode_area_m2", self.electrode_area_m2),
            ("particle_radius_pos_m", self.particle_radius_pos_m),
            ("particle_radius_neg_m", self.particle_radius_neg_m),
            ("thickness_pos_m", self.thickness_pos_m),
            ("thickness_neg_m", self.thickness_neg_m),
            ("thickness_sep_m", self.thickness_sep_m),
            ("solid_diffusivity_pos_m2_per_s", self.solid_diffusivity_pos_m2_per_s),
            ("solid_diffusivity_neg_m2_per_s", self.solid_diffusivity_neg_m2_per_s),
            ("electrolyte_conductivity_s_per_m", self.electrolyte_conductivity_s_per_m),
            ("c_max_pos_mol_per_m3", self.c_max_pos_mol_per_m3),
            ("c_max_neg_mol_per_m3", self.c_max_neg_mol_per_m3),
        ]
        for name, val in positive_checks:
            if val is not None:
                assert_finite(val, name)
                if val <= 0.0:
                    raise InvalidModelParametersError(
                        f"{name} must be strictly positive (> 0.0), got {val}.",
                        details={name: val},
                    )

        # Validate porosity bounds in (0.0, 1.0)
        porosity_checks = [
            ("porosity_pos", self.porosity_pos),
            ("porosity_neg", self.porosity_neg),
            ("porosity_sep", self.porosity_sep),
        ]
        for name, val in porosity_checks:
            if val is not None:
                assert_finite(val, name)
                if not (0.0 < val < 1.0):
                    raise InvalidModelParametersError(
                        f"{name} must be in open range (0.0, 1.0), got {val}.",
                        details={name: val},
                    )

    def to_dict(self) -> dict[str, Any]:
        """Serializes physics parameters to dictionary."""
        base_dict = super().to_dict()
        base_dict.update({
            "model_type": self.model_type.upper().strip(),
            "parameter_set_name": self.parameter_set_name,
            "electrode_area_m2": self.electrode_area_m2,
            "particle_radius_pos_m": self.particle_radius_pos_m,
            "particle_radius_neg_m": self.particle_radius_neg_m,
            "thickness_pos_m": self.thickness_pos_m,
            "thickness_neg_m": self.thickness_neg_m,
            "thickness_sep_m": self.thickness_sep_m,
            "porosity_pos": self.porosity_pos,
            "porosity_neg": self.porosity_neg,
            "porosity_sep": self.porosity_sep,
            "solid_diffusivity_pos_m2_per_s": self.solid_diffusivity_pos_m2_per_s,
            "solid_diffusivity_neg_m2_per_s": self.solid_diffusivity_neg_m2_per_s,
            "electrolyte_conductivity_s_per_m": self.electrolyte_conductivity_s_per_m,
            "c_max_pos_mol_per_m3": self.c_max_pos_mol_per_m3,
            "c_max_neg_mol_per_m3": self.c_max_neg_mol_per_m3,
            "thermal_coupling": self.thermal_coupling.upper().strip(),
            "solver_rel_tol": self.solver_rel_tol,
            "solver_abs_tol": self.solver_abs_tol,
        })
        return base_dict

