"""Battery Decision Support, Fault Diagnosis & Explainable Intelligence Package."""

from src.diagnostics.config import DiagnosticThresholdConfig
from src.diagnostics.context import OperatingContextClassifier
from src.diagnostics.engine import DiagnosticEngine
from src.diagnostics.evidence import (
    EvidenceScoreResult,
    EvidenceScoringEngine,
)
from src.diagnostics.explanation import DiagnosticExplanationBuilder
from src.diagnostics.hypotheses import (
    AbstractDiagnosticHypothesis,
    ApparentOhmicResistanceGrowthHypothesis,
    CellDispersionImbalanceHypothesis,
    ModelFidelityMismatchHypothesis,
    SensorDriftHypothesis,
    ThermalDissipationImpairmentHypothesis,
    ThroughputAcceleratedFadeHypothesis,
    create_standard_hypotheses,
)
from src.diagnostics.lifecycle import (
    DiagnosticLifecycleTracker,
    LifecycleTransition,
)
from src.diagnostics.temporal import (
    TemporalPersistenceState,
    TemporalPersistenceTracker,
)
from src.diagnostics.types import (
    DiagnosticAssessmentReport,
    DiagnosticCategory,
    DiagnosticEvidenceItem,
    DiagnosticSeverity,
    EvidenceEvaluationStatus,
    FaultLifecycleState,
    OperatingContext,
    RootCauseHypothesis,
)

__all__ = [
    # Enumerations
    "DiagnosticSeverity",
    "FaultLifecycleState",
    "DiagnosticCategory",
    "OperatingContext",
    "EvidenceEvaluationStatus",
    # Data Models
    "DiagnosticEvidenceItem",
    "RootCauseHypothesis",
    "DiagnosticAssessmentReport",
    # Configuration & Context Classifier (Phase 1)
    "DiagnosticThresholdConfig",
    "OperatingContextClassifier",
    # Evidence Scoring (Phase 2)
    "EvidenceScoreResult",
    "EvidenceScoringEngine",
    # Temporal Persistence (Phase 2)
    "TemporalPersistenceState",
    "TemporalPersistenceTracker",
    # Diagnostic Hypotheses (Phase 2)
    "AbstractDiagnosticHypothesis",
    "SensorDriftHypothesis",
    "ModelFidelityMismatchHypothesis",
    "ApparentOhmicResistanceGrowthHypothesis",
    "ThermalDissipationImpairmentHypothesis",
    "CellDispersionImbalanceHypothesis",
    "ThroughputAcceleratedFadeHypothesis",
    "create_standard_hypotheses",
    # Lifecycle & Orchestration (Phase 3)
    "DiagnosticLifecycleTracker",
    "LifecycleTransition",
    "DiagnosticExplanationBuilder",
    "DiagnosticEngine",
]
