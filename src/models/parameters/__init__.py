"""Battery Parameterization, OCV Modeling, and Chemistry Catalogs.

Provides analytical and non-linear OCV models, Arrhenius temperature scaling,
and standardized reference parameter sets across all major battery chemistries.
"""

from src.models.parameters.chemistry_defaults import (
    ChemistryProfile,
    get_chemistry_default_ocv_model,
    get_chemistry_default_parameters,
    get_chemistry_default_temperature_scaling,
    get_chemistry_profile,
    list_supported_default_chemistries,
)
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.parameters.ocv_curve import OCVCurve
from src.models.parameters.temperature_scaling import (
    DEFAULT_REFERENCE_TEMPERATURE_C,
    MOLAR_GAS_CONSTANT_J_PER_MOL_K,
    TemperatureScaling,
)

__all__ = [
    # OCV Models
    "LinearOCVModel",
    "OCVCurve",
    # Thermal Scaling
    "TemperatureScaling",
    "MOLAR_GAS_CONSTANT_J_PER_MOL_K",
    "DEFAULT_REFERENCE_TEMPERATURE_C",
    # Chemistry Catalogs & Helpers
    "ChemistryProfile",
    "get_chemistry_profile",
    "get_chemistry_default_parameters",
    "get_chemistry_default_ocv_model",
    "get_chemistry_default_temperature_scaling",
    "list_supported_default_chemistries",
]
