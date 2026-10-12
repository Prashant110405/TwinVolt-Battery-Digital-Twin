"""TwinVolt Level 6.4 — Uncertainty & Confidence Framework.

Provides rigorous, transparent, and chemistry-agnostic uncertainty and evidence
quantification for Remaining Useful Life (RUL) predictions.
"""

from src.prognostics.uncertainty.engine import (
    PrognosticUncertaintyEngine,
    UncertaintyEngineConfig,
    UncertaintyEvaluationResult,
)
from src.prognostics.uncertainty.evidence import (
    EvidenceAssessment,
    EvidenceDimensionRecord,
    EvidenceEvaluator,
    EvidenceEvaluatorConfig,
)
from src.prognostics.uncertainty.extrapolation import (
    ExtrapolationEvaluator,
    ExtrapolationMetrics,
)
from src.prognostics.uncertainty.measurement import (
    MeasurementUncertaintyEvaluation,
    MeasurementUncertaintyEvaluator,
)
from src.prognostics.uncertainty.propagation import (
    RULPropagationResult,
    RULUncertaintyPropagator,
)
from src.prognostics.uncertainty.trajectory import (
    OLSTrendUncertaintyEvaluator,
    TrajectoryTrendStatistics,
)
from src.prognostics.uncertainty.types import (
    EvidenceStrength,
    MeasurementUncertaintyAvailability,
    UncertaintyBound,
    UncertaintyCombinationResult,
    UncertaintyComponent,
    UncertaintyIntervalType,
    UncertaintyRepresentationType,
    UncertaintySourceCategory,
    UncertaintyStatus,
)

__all__ = [
    # Taxonomies & Enums
    "UncertaintySourceCategory",
    "UncertaintyStatus",
    "EvidenceStrength",
    "MeasurementUncertaintyAvailability",
    "UncertaintyRepresentationType",
    "UncertaintyIntervalType",
    # Value Objects & Containers
    "UncertaintyBound",
    "UncertaintyComponent",
    "UncertaintyCombinationResult",
    "MeasurementUncertaintyEvaluation",
    "TrajectoryTrendStatistics",
    "ExtrapolationMetrics",
    "EvidenceDimensionRecord",
    "EvidenceAssessment",
    "EvidenceEvaluatorConfig",
    "RULPropagationResult",
    "UncertaintyEngineConfig",
    "UncertaintyEvaluationResult",
    # Evaluators & Engine
    "MeasurementUncertaintyEvaluator",
    "OLSTrendUncertaintyEvaluator",
    "ExtrapolationEvaluator",
    "EvidenceEvaluator",
    "RULUncertaintyPropagator",
    "PrognosticUncertaintyEngine",
]
