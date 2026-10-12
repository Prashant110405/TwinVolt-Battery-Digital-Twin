"""TwinVolt Level 6 — Battery Prognostics, Degradation Trajectories, and Feature Extraction.

Provides universal, chemistry-independent, and hardware-agnostic domain contracts,
degradation trajectories, multi-dimensional feature extraction, End-of-Life (EOL)
boundary specifications, prediction horizons, and immutable prediction value objects.
"""

from src.prognostics.estimators import (
    AbstractRULEstimator,
    EstimatorConfig,
    HistoricalLinearRULEstimator,
)
from src.prognostics.features import (
    DegradationFeatureSet,
    PrognosticFeature,
    TrajectoryFeatureExtractor,
)
from src.prognostics.horizon import PrognosticHorizon
from src.prognostics.prediction import (
    EOLDefinition,
    PredictionUncertainty,
    PrognosticMethodIdentity,
    RULPredictionResult,
)
from src.prognostics.provenance import (
    PrognosticQuantity,
    PrognosticValueProvenance,
)
from src.prognostics.state import (
    PrognosticOperatingContext,
    PrognosticStateSnapshot,
)
from src.prognostics.trajectory import (
    DegradationObservation,
    DegradationTrajectory,
    TrajectoryBuilder,
)
from src.prognostics.trajectory_types import (
    FeatureQualityStatus,
    RateDomain,
    TrajectoryOrderingStatus,
    TrajectoryQuantityType,
    TrendDirection,
)
from src.prognostics.types import (
    ComparisonOperator,
    EOLCriterionType,
    HorizonDomain,
    PrognosticStatus,
    QuantityAvailability,
    TimeUnit,
    UncertaintyType,
    ValueOriginType,
)
from src.prognostics.decision import (
    Actionability,
    DecisionClass,
    DecisionCondition,
    DecisionPolicy,
    DecisionRecommendation,
    DecisionRule,
    DecisionStatus,
    PrognosticDecisionEngine,
    PrognosticDecisionResult,
    RecommendationPriority,
    RecommendationSynthesizer,
    SecondaryAdvisory,
)
from src.prognostics.evaluation import (
    EOLAssessment,
    EOLEvaluator,
    EOLState,
    EvaluationStatus,
    EvaluationValidity,
    EvaluationValidityEvaluator,
    PrognosticEvaluationEngine,
    PrognosticEvaluationResult,
)
from src.prognostics.uncertainty import (
    EvidenceAssessment,
    EvidenceDimensionRecord,
    EvidenceEvaluator,
    EvidenceEvaluatorConfig,
    EvidenceStrength,
    ExtrapolationEvaluator,
    ExtrapolationMetrics,
    MeasurementUncertaintyAvailability,
    MeasurementUncertaintyEvaluation,
    MeasurementUncertaintyEvaluator,
    OLSTrendUncertaintyEvaluator,
    PrognosticUncertaintyEngine,
    RULPropagationResult,
    RULUncertaintyPropagator,
    TrajectoryTrendStatistics,
    UncertaintyBound,
    UncertaintyCombinationResult,
    UncertaintyComponent,
    UncertaintyEngineConfig,
    UncertaintyEvaluationResult,
    UncertaintyIntervalType,
    UncertaintyRepresentationType,
    UncertaintySourceCategory,
    UncertaintyStatus,
)

from src.prognostics.pipeline import (
    CriterionPrognosticEvaluation,
    EOLPortfolio,
    LimitingMechanismAssessment,
    LimitingMechanismResolver,
    LimitingResolutionStatus,
    LimitingResolutionStrategy,
    PipelineStatus,
    PrognosticAssessmentReport,
    PrognosticPipelineConfig,
    PrognosticPipelineEngine,
    StateHistoryTrajectoryAdapter,
)

__all__ = [
    # Level 6.1 Enums and Classifications
    "PrognosticStatus",
    "ValueOriginType",
    "QuantityAvailability",
    "EOLCriterionType",
    "ComparisonOperator",
    "HorizonDomain",
    "TimeUnit",
    "UncertaintyType",
    # Level 6.1 Value Objects
    "PrognosticValueProvenance",
    "PrognosticQuantity",
    "PrognosticHorizon",
    "PrognosticOperatingContext",
    "PrognosticStateSnapshot",
    "EOLDefinition",
    "PrognosticMethodIdentity",
    "PredictionUncertainty",
    "RULPredictionResult",
    # Level 6.2 Trajectory Enums and Types
    "TrajectoryQuantityType",
    "TrajectoryOrderingStatus",
    "RateDomain",
    "FeatureQualityStatus",
    "TrendDirection",
    # Level 6.2 Trajectory and Feature Value Objects
    "DegradationObservation",
    "DegradationTrajectory",
    "TrajectoryBuilder",
    "PrognosticFeature",
    "DegradationFeatureSet",
    "TrajectoryFeatureExtractor",
    # Level 6.3 Estimator Contracts
    "AbstractRULEstimator",
    "EstimatorConfig",
    "HistoricalLinearRULEstimator",
    # Level 6.4 Uncertainty and Evidence Contracts
    "UncertaintySourceCategory",
    "UncertaintyStatus",
    "EvidenceStrength",
    "MeasurementUncertaintyAvailability",
    "UncertaintyRepresentationType",
    "UncertaintyIntervalType",
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
    "MeasurementUncertaintyEvaluator",
    "OLSTrendUncertaintyEvaluator",
    "ExtrapolationEvaluator",
    "EvidenceEvaluator",
    "RULUncertaintyPropagator",
    "PrognosticUncertaintyEngine",
    # Level 6.5 Evaluation Contracts
    "EvaluationStatus",
    "EOLState",
    "EOLAssessment",
    "EvaluationValidity",
    "PrognosticEvaluationResult",
    "EOLEvaluator",
    "EvaluationValidityEvaluator",
    "PrognosticEvaluationEngine",
    # Level 6.6 Decision and Recommendation Contracts
    "DecisionStatus",
    "DecisionClass",
    "RecommendationPriority",
    "Actionability",
    "SecondaryAdvisory",
    "PrognosticDecisionResult",
    "DecisionCondition",
    "DecisionRule",
    "DecisionPolicy",
    "DecisionRecommendation",
    "RecommendationSynthesizer",
    "PrognosticDecisionEngine",
    # Level 6.7 Pipeline and Multi-Criterion Contracts
    "PipelineStatus",
    "LimitingResolutionStatus",
    "LimitingResolutionStrategy",
    "CriterionPrognosticEvaluation",
    "LimitingMechanismAssessment",
    "PrognosticAssessmentReport",
    "EOLPortfolio",
    "PrognosticPipelineConfig",
    "StateHistoryTrajectoryAdapter",
    "LimitingMechanismResolver",
    "PrognosticPipelineEngine",
]



