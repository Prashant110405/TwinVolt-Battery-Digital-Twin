"""TwinVolt Level 6.7 — Prognostic Pipeline Orchestration & Multi-Criterion Assessment Engine.

Provides immutable portfolio configuration, trajectory adaptation from twin state history,
multi-criterion degradation evaluation dispatch, deterministic limiting mechanism resolution,
and top-level prognostic assessment report generation.
"""

from src.prognostics.pipeline.adapter import StateHistoryTrajectoryAdapter
from src.prognostics.pipeline.config import EOLPortfolio, PrognosticPipelineConfig
from src.prognostics.pipeline.engine import PrognosticPipelineEngine
from src.prognostics.pipeline.limiting import LimitingMechanismResolver
from src.prognostics.pipeline.types import (
    CriterionPrognosticEvaluation,
    LimitingMechanismAssessment,
    LimitingResolutionStatus,
    LimitingResolutionStrategy,
    PipelineStatus,
    PrognosticAssessmentReport,
)

__all__ = [
    # Statuses and Enums
    "PipelineStatus",
    "LimitingResolutionStatus",
    "LimitingResolutionStrategy",
    # Domain Value Objects & Reports
    "CriterionPrognosticEvaluation",
    "LimitingMechanismAssessment",
    "PrognosticAssessmentReport",
    # Configuration & Portfolio
    "EOLPortfolio",
    "PrognosticPipelineConfig",
    # Adapters & Resolvers
    "StateHistoryTrajectoryAdapter",
    "LimitingMechanismResolver",
    # Pipeline Engine
    "PrognosticPipelineEngine",
]
