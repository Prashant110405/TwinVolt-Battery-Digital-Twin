"""Battery Behavior Validation, Model-vs-Measurement Residual Analysis & Parameter Validation Package."""

from src.validation.auditor import SignalAlignmentAuditor, SignalAuditResult
from src.validation.engine import ModelValidationEngine
from src.validation.events import BatteryValidationUpdatedEvent
from src.validation.parameter_validator import ParameterValidationEvaluator
from src.validation.residuals import ResidualStatisticsAccumulator
from src.validation.shadow import ProspectiveECMBranchSimulator
from src.validation.types import (
    ModelValidationReport,
    ModelValidationState,
    ParameterEvidenceTier,
    ParameterValidationEvidence,
    SignalProvenance,
    SignalResidualMetrics,
    ValidationConfig,
    ValidationWindowReport,
)

__all__ = [
    # Types & Enums
    "SignalProvenance",
    "ModelValidationState",
    "ParameterEvidenceTier",
    "ValidationConfig",
    "SignalResidualMetrics",
    "ParameterValidationEvidence",
    "ValidationWindowReport",
    "ModelValidationReport",
    # Core Components
    "ResidualStatisticsAccumulator",
    "SignalAuditResult",
    "SignalAlignmentAuditor",
    "ProspectiveECMBranchSimulator",
    "ParameterValidationEvaluator",
    "ModelValidationEngine",
    # Events
    "BatteryValidationUpdatedEvent",
]
