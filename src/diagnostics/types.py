"""Data types, enumerations, and immutable report containers for Battery Diagnostics.

Defines strongly-typed representations for diagnostic severity levels, fault lifecycle states,
diagnostic categories, operating contexts, evidence items, root-cause hypotheses, and assessment reports.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping, Optional

from src.validation.types import SignalProvenance


class DiagnosticSeverity(str, Enum):
    """Advisory severity tier of an evaluated diagnostic condition."""

    INFORMATIONAL = "INFORMATIONAL"   # Diagnostic observation, no expected operational impact
    WARNING = "WARNING"               # Moderate anomaly requiring monitoring/observation
    CRITICAL = "CRITICAL"             # High-severity analytical condition requiring operator review
    UNKNOWN = "UNKNOWN"               # Insufficient telemetry to evaluate severity


class FaultLifecycleState(str, Enum):
    """Operational lifecycle state of a battery diagnostic condition."""

    NORMAL = "NORMAL"                                 # No anomalous signatures detected
    ANOMALY_DETECTED = "ANOMALY_DETECTED"             # Initial statistical anomaly observed, pending persistence
    SUSPECTED = "SUSPECTED"                           # Anomaly persisted across debounce window; hypothesis active
    DIAGNOSED = "DIAGNOSED"                           # Confirmed diagnostic pattern backed by supported hypothesis
    DIAGNOSED_CRITICAL = "DIAGNOSED_CRITICAL"         # High-severity condition meeting multi-signal analytical criteria
    RECOVERED = "RECOVERED"                           # Signals returned within nominal bounds across hysteresis window
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"   # Anomalous signature observed, but required data is missing
    DATA_QUALITY_FAILED = "DATA_QUALITY_FAILED"       # Upstream data quality failure; diagnostics suspended


class DiagnosticCategory(str, Enum):
    """Orthogonal category of a root-cause hypothesis."""

    SENSOR = "SENSOR"                                 # Instrumentation offset, noise, or drift
    MODEL = "MODEL"                                   # Parameter error or unmodeled physical dynamics
    ELECTRICAL = "ELECTRICAL"                         # Apparent ohmic resistance, contact impedance
    THERMAL = "THERMAL"                               # Heat dissipation impairment, thermal gradient
    CELL = "CELL"                                     # Cell voltage/temperature dispersion imbalance
    DEGRADATION = "DEGRADATION"                       # Cyclic or calendar capacity fade


class OperatingContext(str, Enum):
    """Operating electrical and thermal regime of the battery system."""

    REST = "REST"                                     # |I| < rest_current_threshold_a for rest_min_duration_s
    CHARGE_CC = "CHARGE_CC"                           # Sustained charge current with low variance
    DISCHARGE_CC = "DISCHARGE_CC"                     # Sustained discharge current with low variance
    DYNAMIC_TRANSIENT = "DYNAMIC_TRANSIENT"           # High current variance (drive cycle / pulsed load)
    THERMAL_TRANSIENT = "THERMAL_TRANSIENT"           # High ambient or cooling dynamic
    DATA_GAPPED = "DATA_GAPPED"                       # Step interval exceeded data_gap_threshold_s


class EvidenceEvaluationStatus(str, Enum):
    """Classification of empirical evidence for a specific signal."""

    SUPPORTING = "SUPPORTING"                         # Observation supports the hypothesis
    CONTRAINDICATING = "CONTRAINDICATING"             # Observation rules out or weakens the hypothesis
    NO_EVIDENCE = "NO_EVIDENCE"                       # Signal observed but within neutral bounds
    UNAVAILABLE = "UNAVAILABLE"                       # Required signal omitted from telemetry or unconfigured
    UNKNOWN = "UNKNOWN"                               # Signal quality invalid or data gapped


@dataclass(frozen=True)
class DiagnosticEvidenceItem:
    """Individual evidence record supporting or contraindicating a diagnostic hypothesis."""

    source_layer: str                                 # "telemetry", "anomaly", "analytics", "calibration", "validation"
    signal_name: str                                  # e.g., "voltage_rmse_v", "identified_r0_ohm", "temp_rate_c_s"
    observed_value: Any
    expected_value: Any
    provenance: SignalProvenance                      # MEASURED, ESTIMATED, MODEL_PREDICTED, DERIVED, MISSING
    status: EvidenceEvaluationStatus
    weight: float                                     # Relative evidentiary weight [0.0, 1.0]
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.weight, (int, float)) or math.isnan(self.weight) or math.isinf(self.weight):
            raise ValueError(f"weight must be a finite float, got {self.weight}.")
        if not (0.0 <= self.weight <= 1.0):
            raise ValueError(f"weight must be in range [0.0, 1.0], got {self.weight}.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes evidence item to dictionary."""
        return {
            "source_layer": self.source_layer,
            "signal_name": self.signal_name,
            "observed_value": self.observed_value,
            "expected_value": self.expected_value,
            "provenance": self.provenance.value,
            "status": self.status.value,
            "weight": round(self.weight, 4),
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class RootCauseHypothesis:
    """Candidate root-cause hypothesis with evidence breakdown and confidence rating."""

    hypothesis_id: str                               # e.g., "HYP_APPARENT_OHMIC_RESISTANCE_GROWTH"
    title: str                                       # Human-readable title
    category: DiagnosticCategory                     # Orthogonal category (SENSOR, MODEL, ELECTRICAL, etc.)
    evidence_score: float                            # Deterministic empirical score [0.0, 1.0]
    confidence_level: str                            # "STRONG", "MODERATE", "WEAK", "REJECTED", "INSUFFICIENT_DATA"
    required_signal_coverage: float                  # Fraction of required signals available [0.0, 1.0]
    optional_signal_coverage: float                  # Fraction of optional signals available [0.0, 1.0]
    supporting_evidence: tuple[DiagnosticEvidenceItem, ...] = field(default_factory=tuple)
    contraindicating_evidence: tuple[DiagnosticEvidenceItem, ...] = field(default_factory=tuple)
    untestable_confounds: tuple[str, ...] = field(default_factory=tuple)
    suggested_investigations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_score, (int, float)) or math.isnan(self.evidence_score) or math.isinf(self.evidence_score):
            raise ValueError(f"evidence_score must be a finite float, got {self.evidence_score}.")
        if not (0.0 <= self.evidence_score <= 1.0):
            raise ValueError(f"evidence_score must be in range [0.0, 1.0], got {self.evidence_score}.")

        if not isinstance(self.required_signal_coverage, (int, float)) or not (0.0 <= self.required_signal_coverage <= 1.0):
            raise ValueError(f"required_signal_coverage must be in range [0.0, 1.0], got {self.required_signal_coverage}.")

        if not isinstance(self.optional_signal_coverage, (int, float)) or not (0.0 <= self.optional_signal_coverage <= 1.0):
            raise ValueError(f"optional_signal_coverage must be in range [0.0, 1.0], got {self.optional_signal_coverage}.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes root-cause hypothesis to dictionary."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "category": self.category.value,
            "evidence_score": round(self.evidence_score, 4),
            "confidence_level": self.confidence_level,
            "required_signal_coverage": round(self.required_signal_coverage, 4),
            "optional_signal_coverage": round(self.optional_signal_coverage, 4),
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
            "contraindicating_evidence": [e.to_dict() for e in self.contraindicating_evidence],
            "untestable_confounds": list(self.untestable_confounds),
            "suggested_investigations": list(self.suggested_investigations),
        }


@dataclass(frozen=True)
class DiagnosticAssessmentReport:
    """Comprehensive explainable battery diagnostic assessment snapshot."""

    assessment_id: str
    system_id: str
    timestamp_ns: int
    lifecycle_state: FaultLifecycleState
    severity: DiagnosticSeverity
    operating_context: OperatingContext
    primary_hypothesis: Optional[RootCauseHypothesis] = None
    alternative_hypotheses: tuple[RootCauseHypothesis, ...] = field(default_factory=tuple)
    explanation_narrative: str = ""
    recommended_operator_actions: tuple[str, ...] = field(default_factory=tuple)
    active_anomalies_count: int = 0
    data_quality_status: str = "VALID"
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes diagnostic assessment report to dictionary."""
        return {
            "assessment_id": self.assessment_id,
            "system_id": self.system_id,
            "timestamp_ns": self.timestamp_ns,
            "lifecycle_state": self.lifecycle_state.value,
            "severity": self.severity.value,
            "operating_context": self.operating_context.value,
            "primary_hypothesis": self.primary_hypothesis.to_dict() if self.primary_hypothesis else None,
            "alternative_hypotheses": [h.to_dict() for h in self.alternative_hypotheses],
            "explanation_narrative": self.explanation_narrative,
            "recommended_operator_actions": list(self.recommended_operator_actions),
            "active_anomalies_count": self.active_anomalies_count,
            "data_quality_status": self.data_quality_status,
            "diagnostics": dict(self.diagnostics),
        }
