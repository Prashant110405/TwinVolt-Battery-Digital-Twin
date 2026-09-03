"""Online Parameter Identification and Recursive Calibration Package."""

from src.calibration.events import ParameterIdentificationUpdatedEvent
from src.calibration.gating import ExcitationDetector, ExcitationGatingResult
from src.calibration.guard import ParameterSafetyGuard, ParameterValidationResult
from src.calibration.rls import RLSParameterIdentifier, UDCovarianceFactorizer
from src.calibration.types import (
    IdentifiedParameterSet,
    ParameterStateClassification,
    RLSConfig,
)

__all__ = [
    # Types & Enums
    "ParameterStateClassification",
    "RLSConfig",
    "IdentifiedParameterSet",
    # Excitation Gating
    "ExcitationGatingResult",
    "ExcitationDetector",
    # Parameter Safety Guard
    "ParameterValidationResult",
    "ParameterSafetyGuard",
    # RLS & U-D Factorization
    "UDCovarianceFactorizer",
    "RLSParameterIdentifier",
    # Events
    "ParameterIdentificationUpdatedEvent",
]
