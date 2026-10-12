"""Enumerations and Value Objects for Prognostic Decision and Recommendation Layer.

Defines strongly-typed, immutable value objects, statuses, priorities, actionabilities,
secondary advisories, and the top-level PrognosticDecisionResult container.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping, Optional, Sequence


class DecisionStatus(str, Enum):
    """Execution and lifecycle status of the prognostic decision evaluation."""

    EVALUATED = "EVALUATED"                             # Policy evaluated successfully; rule condition matched
    DEFAULT_RULE_APPLIED = "DEFAULT_RULE_APPLIED"       # No specific rule matched; policy default rule applied
    BLOCKED_BY_VALIDITY = "BLOCKED_BY_VALIDITY"         # Usability blocked by Level 6.5 data quality or validity failure
    INCOMPATIBLE_EVALUATION = "INCOMPATIBLE_EVALUATION" # Evaluation result domain/unit incompatible with policy
    INVALID_POLICY = "INVALID_POLICY"                   # Supplied policy failed structural or semantic validation
    NO_MATCH = "NO_MATCH"                               # No rule matched and no default rule available
    INDETERMINATE = "INDETERMINATE"                     # Decision state cannot be determined from available inputs


class DecisionClass(str, Enum):
    """Universal metrological and operational decision classifications."""

    CONTINUE_MONITORING = "CONTINUE_MONITORING"                   # Nominal degradation; standard monitoring cadence
    INCREASE_MONITORING = "INCREASE_MONITORING"                   # Accelerated degradation; increase telemetry polling
    SCHEDULE_INSPECTION = "SCHEDULE_INSPECTION"                   # Non-urgent physical or diagnostic inspection
    PLAN_MAINTENANCE = "PLAN_MAINTENANCE"                         # RUL indicates maintenance/pack overhaul needed
    APPROACHING_EOL = "APPROACHING_EOL"                           # RUL is critically low; impending end-of-life boundary
    EOL_REACHED = "EOL_REACHED"                                   # System degradation currently satisfies or exceeds EOL
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"               # Observational data insufficient for actionable maintenance
    DATA_QUALITY_ACTION_REQUIRED = "DATA_QUALITY_ACTION_REQUIRED" # Telemetry/sensor integrity failed; data stream investigation required
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"                               # Operating regime outside model validity envelope
    INDETERMINATE_STATE = "INDETERMINATE_STATE"                   # Prognostic state cannot be resolved from inputs
    NO_ACTION = "NO_ACTION"                                       # Explicitly no operational action required
    CUSTOM = "CUSTOM"                                             # Application-specific custom decision category


class RecommendationPriority(str, Enum):
    """Operational triage urgency ranking for decision recommendations."""

    CRITICAL = "CRITICAL"           # Immediate action required (e.g. EOL reached, severe sensor failure)
    HIGH = "HIGH"                   # High priority; act in near-term maintenance window (e.g. approaching EOL)
    MEDIUM = "MEDIUM"               # Moderate priority; schedule within standard operational cycle
    LOW = "LOW"                     # Low priority; informational advisory (e.g. increase monitoring cadence)
    INFORMATIONAL = "INFORMATIONAL" # Routine baseline; normal operation


class Actionability(str, Enum):
    """Operational actionability classification of the decision recommendation."""

    ACTIONABLE = "ACTIONABLE"                                 # Clear, justified operational task can be scheduled
    ADVISORY_ONLY = "ADVISORY_ONLY"                           # Contextual awareness; no immediate physical action warranted
    INVESTIGATION_REQUIRED = "INVESTIGATION_REQUIRED"         # Sensor or telemetry anomaly must be resolved first
    NON_ACTIONABLE = "NON_ACTIONABLE"                         # Evaluation invalid or uncharacterized; cannot act
    MAINTENANCE_RECOMMENDATION = "MAINTENANCE_RECOMMENDATION" # Explicit physical maintenance task recommendation
    DATA_QUALITY_ACTION = "DATA_QUALITY_ACTION"               # Telemetry/instrumentation investigation action
    INFORMATIONAL = "INFORMATIONAL"                           # Informational notification only


@dataclass(frozen=True)
class SecondaryAdvisory:
    """Immutable secondary advisory, limitation, or non-primary matched condition."""

    advisory_id: str
    decision_class: DecisionClass
    priority: RecommendationPriority
    actionability: Actionability
    summary: str
    rationale: str
    matched_condition_id: Optional[str] = None
    category: str = "ADVISORY"
    source: str = "POLICY_RULE"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.advisory_id or not isinstance(self.advisory_id, str):
            raise ValueError("advisory_id must be a non-empty string.")
        if not isinstance(self.decision_class, DecisionClass):
            raise TypeError(f"Expected DecisionClass, got {type(self.decision_class).__name__}.")
        if not isinstance(self.priority, RecommendationPriority):
            raise TypeError(f"Expected RecommendationPriority, got {type(self.priority).__name__}.")
        if not isinstance(self.actionability, Actionability):
            raise TypeError(f"Expected Actionability, got {type(self.actionability).__name__}.")
        if not self.summary or not isinstance(self.summary, str):
            raise ValueError("summary must be a non-empty string.")
        if not self.rationale or not isinstance(self.rationale, str):
            raise ValueError("rationale must be a non-empty string.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes secondary advisory to dictionary."""
        return {
            "advisory_id": self.advisory_id,
            "decision_class": self.decision_class.value,
            "priority": self.priority.value,
            "actionability": self.actionability.value,
            "summary": self.summary,
            "rationale": self.rationale,
            "matched_condition_id": self.matched_condition_id,
            "category": self.category,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PrognosticDecisionResult:
    """Immutable, auditable top-level prognostic decision and recommendation container.

    Strict Guarantees:
    1. Zero synthetic confidence percentages or uncalibrated probabilities.
    2. Strict safety authority separation (physical BMS remains sole safety and actuation authority).
    3. Pure reproducibility linking back to Level 6.5 Evaluation ID and DecisionPolicy ID/version.
    4. Deterministic primary decision plus preserved secondary advisories and validity limitations.
    """

    decision_id: str
    system_id: str
    decision_timestamp_ns: int
    created_at_utc: str
    status: DecisionStatus
    primary_decision_class: DecisionClass
    primary_recommendation: str
    primary_priority: RecommendationPriority
    primary_actionability: Actionability
    primary_rationale: str
    policy_id: str
    policy_version: str
    primary_rule_id: Optional[str] = None
    matched_rule_ids: Sequence[str] = field(default_factory=tuple)
    triggering_conditions: Sequence[str] = field(default_factory=tuple)
    secondary_advisories: Sequence[SecondaryAdvisory] = field(default_factory=tuple)
    validity_limitations: Sequence[str] = field(default_factory=tuple)
    evaluation_reference_id: str = ""
    is_safety_critical_actuation: bool = False
    safety_authority: str = "Physical BMS"
    safety_disclaimer: str = (
        "ADVISORY ONLY: TwinVolt analytical decisions do not command physical actuators. "
        "The physical Battery Management System (BMS) remains the sole safety and protection authority."
    )
    reproducibility_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.decision_id or not isinstance(self.decision_id, str):
            raise ValueError("decision_id must be a non-empty string.")
        if not self.system_id or not isinstance(self.system_id, str):
            raise ValueError("system_id must be a non-empty string.")
        if not isinstance(self.decision_timestamp_ns, int) or self.decision_timestamp_ns < 0:
            raise ValueError(
                f"decision_timestamp_ns must be a non-negative integer, got {self.decision_timestamp_ns}."
            )
        if not self.created_at_utc or not isinstance(self.created_at_utc, str):
            raise ValueError("created_at_utc must be a non-empty string.")
        if not isinstance(self.status, DecisionStatus):
            raise TypeError(f"Expected DecisionStatus, got {type(self.status).__name__}.")
        if not isinstance(self.primary_decision_class, DecisionClass):
            raise TypeError(f"Expected DecisionClass, got {type(self.primary_decision_class).__name__}.")
        if not self.primary_recommendation or not isinstance(self.primary_recommendation, str):
            raise ValueError("primary_recommendation must be a non-empty string.")
        if not isinstance(self.primary_priority, RecommendationPriority):
            raise TypeError(f"Expected RecommendationPriority, got {type(self.primary_priority).__name__}.")
        if not isinstance(self.primary_actionability, Actionability):
            raise TypeError(f"Expected Actionability, got {type(self.primary_actionability).__name__}.")
        if not self.primary_rationale or not isinstance(self.primary_rationale, str):
            raise ValueError("primary_rationale must be a non-empty string.")
        if not self.policy_id or not isinstance(self.policy_id, str):
            raise ValueError("policy_id must be a non-empty string.")
        if not self.policy_version or not isinstance(self.policy_version, str):
            raise ValueError("policy_version must be a non-empty string.")

        # Invariant: Safety actuation flag must never be True in analytical digital twin
        if self.is_safety_critical_actuation is not False:
            raise ValueError("is_safety_critical_actuation must be False. Digital twin cannot perform physical actuation.")

    @property
    def is_actionable(self) -> bool:
        """Returns True if the primary recommendation represents an actionable operational task."""
        return self.primary_actionability in (
            Actionability.ACTIONABLE,
            Actionability.MAINTENANCE_RECOMMENDATION,
            Actionability.DATA_QUALITY_ACTION,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializes prognostic decision result to dictionary."""
        return {
            "decision_id": self.decision_id,
            "system_id": self.system_id,
            "decision_timestamp_ns": self.decision_timestamp_ns,
            "created_at_utc": self.created_at_utc,
            "status": self.status.value,
            "primary_decision_class": self.primary_decision_class.value,
            "primary_recommendation": self.primary_recommendation,
            "primary_priority": self.primary_priority.value,
            "primary_actionability": self.primary_actionability.value,
            "primary_rationale": self.primary_rationale,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "primary_rule_id": self.primary_rule_id,
            "matched_rule_ids": list(self.matched_rule_ids),
            "triggering_conditions": list(self.triggering_conditions),
            "secondary_advisories": [a.to_dict() for a in self.secondary_advisories],
            "validity_limitations": list(self.validity_limitations),
            "evaluation_reference_id": self.evaluation_reference_id,
            "is_actionable": self.is_actionable,
            "is_safety_critical_actuation": self.is_safety_critical_actuation,
            "safety_authority": self.safety_authority,
            "safety_disclaimer": self.safety_disclaimer,
            "reproducibility_metadata": dict(self.reproducibility_metadata),
        }
