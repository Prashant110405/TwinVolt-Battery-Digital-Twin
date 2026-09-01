"""Physics-Based Electrochemical Model Parameters.

Defines parameter containers for PDE-based models (SPM, SPMe, DFN),
electrochemical constants, and geometry properties.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from src.models.exceptions import InvalidModelParametersError
from src.models.math import assert_finite
from src.models.types import ModelParameters

SUPPORTED_PHYSICS_MODELS = {"SPM", "SPMe", "DFN", "MSMR"}


@dataclass(frozen=True)
class PhysicsModelParameters(ModelParameters):
    """Parameter container for high-fidelity electrochemical models.

    All physical parameters use explicit SI units.
    """

    model_type: str = "SPM"
    parameter_set_name: str = "Chen2020"
    electrode_area_m2: Optional[float] = None
    solid_diffusivity_pos_m2_per_s: Optional[float] = None
    solid_diffusivity_neg_m2_per_s: Optional[float] = None
    electrolyte_conductivity_s_per_m: Optional[float] = None

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

        if self.electrode_area_m2 is not None:
            assert_finite(self.electrode_area_m2, "electrode_area_m2")
            if self.electrode_area_m2 <= 0.0:
                raise InvalidModelParametersError("electrode_area_m2 must be positive.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes physics parameters to dictionary."""
        base_dict = super().to_dict()
        base_dict.update({
            "model_type": self.model_type.upper().strip(),
            "parameter_set_name": self.parameter_set_name,
            "electrode_area_m2": self.electrode_area_m2,
            "solid_diffusivity_pos_m2_per_s": self.solid_diffusivity_pos_m2_per_s,
            "solid_diffusivity_neg_m2_per_s": self.solid_diffusivity_neg_m2_per_s,
            "electrolyte_conductivity_s_per_m": self.electrolyte_conductivity_s_per_m,
        })
        return base_dict
