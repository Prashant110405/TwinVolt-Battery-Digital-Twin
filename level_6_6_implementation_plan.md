# Level 6.6 — Prognostic Decision & Recommendation Layer
## Architectural Specification & Implementation Plan

**Author:** TwinVolt Core Architecture Team  
**Status:** DESIGN-ONLY / PENDING IMPLEMENTATION APPROVAL  
**Layer:** Level 6.6 (Prognostic Decision & Recommendation Layer)  
**Target Package:** `src/prognostics/decision/`  
**Dependencies:** Level 0 through Level 6.5 (Strictly Locked & Read-Only)  

---

## Executive Summary

The **Prognostic Decision & Recommendation Layer (Level 6.6)** is the final analytical interpretation tier of the TwinVolt prognostics subsystem. Its single, unambiguous objective is to:
> **Interpret an already-evaluated, authoritative `PrognosticEvaluationResult` (from Level 6.5) and synthesize deterministic, auditable, and application-specific operational recommendations under an explicitly supplied `DecisionPolicy`.**

Level 6.6 operates strictly as a **decision-interpretation layer**. It introduces **zero** new degradation physics, **zero** RUL estimators, **zero** uncertainty approximations, and **zero** machine-learning heuristics. It enforces strict **safety authority separation**: all recommendations produced by Level 6.6 are explicitly advisory and analytical, leaving physical actuation, electrical disconnection, and safety-critical protection exclusively to the physical Battery Management System (BMS).

```
Level 6.1: Prognostic Domain Contracts (Enums, Horizons, Provenance, EOLDefinition)
        ↓
Level 6.2: Degradation Trajectories & Feature Extraction
        ↓
Level 6.3: Deterministic RUL Estimation (Historical Linear Baseline)
        ↓
Level 6.4: Metrological Uncertainty & Observational Evidence Auditing
        ↓
Level 6.5: Prognostic Evaluation, EOL Assessment & Multi-Dimensional Validity
        ↓
Level 6.6: Prognostic Decision & Recommendation Layer [THIS SPECIFICATION]
        ↓
[Future Tier]: Runtime Orchestration, REST API, Replay & Supervisory UI
```

---

## 1. Current Architecture Inspection

Inspection of the current repository verifies that Levels 0 through 6.5 are fully implemented, strictly tested, and locked.

### Verification Baseline
- **Level 6.5 Package:** `src/prognostics/evaluation/`
  - `types.py` (EvaluationStatus, EOLState, EOLAssessment, EvaluationValidity, PrognosticEvaluationResult)
  - `eol.py` (EOLEvaluator)
  - `validity.py` (EvaluationValidityEvaluator)
  - `evaluator.py` (PrognosticEvaluationEngine)
- **Test Suite Status:**
  - `tests/unit/prognostics/evaluation/`: 34 targeted tests passing.
  - `tests/unit/prognostics/`: 156 prognostics tests passing.
  - Full repository test suite: **783 tests passing, 0 failures, 2 pre-existing unraisable warnings**.
- **Architecture Invariant:**
  - All Level 6.1–6.5 domain contracts are immutable (`frozen=True`).
  - Metrological purity is preserved (no synthetic confidence percentages or uncalibrated probabilities).
  - Valid deterministic point estimates are never silently dropped when statistical uncertainty is unquantified.

---

## 2. Existing Level 6.1–6.5 Contract Map

Level 6.6 directly reuses and strictly preserves the following locked contracts:

| Layer | Contract / Component | Path | Responsibility in Level 6.6 |
| :--- | :--- | :--- | :--- |
| **6.1** | `PrognosticStatus` | `src/prognostics/types.py` | Input validity status evaluation (data quality, history sufficiency, out of domain) |
| **6.1** | `ComparisonOperator` | `src/prognostics/types.py` | Mathematical relational operator for policy threshold evaluation (`<=`, `>=`, `<`, `>`, `==`) |
| **6.1** | `HorizonDomain` | `src/prognostics/types.py` | RUL domain validation (`CYCLE`, `TIME`, `AMPERE_HOUR_THROUGHPUT`, `WATT_HOUR_THROUGHPUT`, `CUSTOM`) |
| **6.1** | `EOLCriterionType` | `src/prognostics/types.py` | EOL boundary type checking |
| **6.1** | `EOLDefinition` | `src/prognostics/prediction.py` | EOL threshold definition and metadata |
| **6.1** | `RULPredictionResult` | `src/prognostics/prediction.py` | Deterministic RUL value (`rul_value`), domain, unit, and method identity |
| **6.1** | `PredictionUncertainty` | `src/prognostics/prediction.py` | Statistical bounds and standard deviation |
| **6.2** | `DegradationTrajectory` | `src/prognostics/trajectory.py` | Trajectory metadata, span, and observation count |
| **6.2** | `DegradationFeatureSet` | `src/prognostics/features.py` | Trajectory features (rate of change, curvature, knee-point) |
| **6.3** | `AbstractRULEstimator` | `src/prognostics/estimators/base.py` | Locked estimator interface |
| **6.4** | `UncertaintyStatus` | `src/prognostics/uncertainty/types.py` | Uncertainty classification (`STATISTICALLY_SUPPORTED`, `ESTIMATED`, `DETERMINISTIC_ONLY`, `UNDEFINED`, etc.) |
| **6.4** | `EvidenceStrength` | `src/prognostics/uncertainty/types.py` | Observational depth classification (`INSUFFICIENT`, `VERY_WEAK`, `WEAK`, `MODERATE`, `STRONG`, `VERY_STRONG`) |
| **6.4** | `UncertaintyEvaluationResult` | `src/prognostics/uncertainty/engine.py` | Uncertainty bounds, trend statistics, extrapolation metrics |
| **6.4** | `EvidenceAssessment` | `src/prognostics/uncertainty/evidence.py` | Multi-dimensional evidence audit |
| **6.5** | `EvaluationStatus` | `src/prognostics/evaluation/types.py` | Top-level validity gate (`VALID`, `VALID_WITH_LIMITATIONS`, `DATA_QUALITY_FAILED`, `OUT_OF_DOMAIN`, etc.) |
| **6.5** | `EOLState` | `src/prognostics/evaluation/types.py` | Degradation boundary state (`NOT_REACHED`, `ALREADY_REACHED`, `PROJECTED`, `INDETERMINATE`, `INVALID`) |
| **6.5** | `EOLAssessment` | `src/prognostics/evaluation/types.py` | Metrological distance to EOL and projected crossing point |
| **6.5** | `EvaluationValidity` | `src/prognostics/evaluation/types.py` | Decision usability gate (`is_usable_for_decision`), limitations, and diagnostic notes |
| **6.5** | `PrognosticEvaluationResult` | `src/prognostics/evaluation/types.py` | **Primary Authoritative Input Container** entering Level 6.6 |

---

## 3. Proposed Level 6.6 Package Structure

The proposed package structure resides under `src/prognostics/decision/`:

```
src/prognostics/decision/
├── __init__.py             # Clean public API exports
├── types.py                # Domain Enums, SecondaryAdvisory, PrognosticDecisionResult
├── policy.py               # DecisionCondition, DecisionRule, DecisionPolicy, validation logic
├── recommendation.py       # Recommendation builder, advisory synthesizer, rationale generator
└── engine.py               # PrognosticDecisionEngine (stateless, pure, deterministic orchestrator)
```

### Module Responsibility Breakdown

1. `types.py`:
   - `DecisionStatus`: Execution and matching lifecycle status.
   - `DecisionClass`: Categorical classification of the decision.
   - `RecommendationPriority`: Urgency and triage ranking.
   - `Actionability`: Operational feasibility category.
   - `SecondaryAdvisory`: Immutable container for secondary warnings, limitations, and non-primary advisories.
   - `PrognosticDecisionResult`: Immutable top-level decision record.

2. `policy.py`:
   - `DecisionCondition`: Strongly-typed predicate container defining evaluation constraints (RUL threshold, EOL state, validity requirements, evidence gating).
   - `DecisionRule`: Immutable rule entity binding a condition to a `DecisionClass`, priority, actionability, template, and explicit integer `precedence_rank`.
   - `DecisionPolicy`: Immutable policy container specifying policy identity, target domain, default fallback rule, list of rules, and deterministic validation rules.

3. `recommendation.py`:
   - `DecisionRecommendation`: Formatted recommendation payload containing action text, rationale, limitations, and safety notices.
   - `RecommendationSynthesizer`: Pure helper functions for deterministic message template interpolation.

4. `engine.py`:
   - `PrognosticDecisionEngine`: Pure, stateless orchestrator that executes validation, validity gating, condition matching, precedence resolution, and immutability assembly.

5. `__init__.py`:
   - Exports all public symbols to `src.prognostics` and `src.prognostics.decision`.

---

## 4. Domain Contract Design

All Level 6.6 domain contracts are immutable Python `@dataclass(frozen=True)` and `str, Enum` classes.

### 4.1 Enumerations (`types.py`)

```python
class DecisionStatus(str, Enum):
    """Lifecycle and execution status of the prognostic decision evaluation."""
    EVALUATED = "EVALUATED"                     # Policy evaluated successfully; condition matched
    DEFAULT_RULE_APPLIED = "DEFAULT_RULE_APPLIED" # No specific rule matched; policy default rule was applied
    BLOCKED_BY_VALIDITY = "BLOCKED_BY_VALIDITY"   # Usability blocked by fatal Level 6.5 validity failure
    INCOMPATIBLE_EVALUATION = "INCOMPATIBLE_EVALUATION" # Evaluation result domain/unit incompatible with policy
    INVALID_POLICY = "INVALID_POLICY"           # Supplied policy failed structural or semantic validation


class DecisionClass(str, Enum):
    """Universal classification of operational prognostic recommendations."""
    CONTINUE_MONITORING = "CONTINUE_MONITORING"                   # Normal degradation; continue standard monitoring cadence
    INCREASE_MONITORING = "INCREASE_MONITORING"                   # Accelerated wear or approaching threshold; increase telemetry polling
    SCHEDULE_INSPECTION = "SCHEDULE_INSPECTION"                   # Non-urgent physical or diagnostic inspection recommended
    PLAN_MAINTENANCE = "PLAN_MAINTENANCE"                         # RUL indicates maintenance/pack overhaul needed within planning window
    APPROACHING_EOL = "APPROACHING_EOL"                           # RUL is critically low; impending end-of-life boundary
    EOL_REACHED = "EOL_REACHED"                                   # System degradation currently satisfies or exceeds EOL threshold
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"               # Observational data too sparse/scattered to support active maintenance action
    DATA_QUALITY_ACTION_REQUIRED = "DATA_QUALITY_ACTION_REQUIRED" # Telemetry/sensor integrity failed; investigate data stream
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"                               # Operating regime outside model validity envelope
    INDETERMINATE_STATE = "INDETERMINATE_STATE"                   # Prognostic state cannot be resolved from inputs
    CUSTOM = "CUSTOM"                                             # Application-specific custom decision category


class RecommendationPriority(str, Enum):
    """Operational triage urgency ranking for decision recommendations."""
    CRITICAL = "CRITICAL"       # Immediate action required (e.g. EOL reached, severe sensor data failure)
    HIGH = "HIGH"               # High priority; act in near-term maintenance window (e.g. approaching EOL)
    MEDIUM = "MEDIUM"           # Moderate priority; schedule within standard operational cycle (e.g. inspection)
    LOW = "LOW"                 # Low priority; informational advisory (e.g. increase monitoring frequency)
    INFORMATIONAL = "INFORMATIONAL" # Routine baseline; normal operation


class Actionability(str, Enum):
    """Operational actionability classification of the decision."""
    ACTIONABLE = "ACTIONABLE"                       # Clear, justified physical/operational workflow can be scheduled
    ADVISORY_ONLY = "ADVISORY_ONLY"                 # Contextual awareness; no immediate physical action warranted
    INVESTIGATION_REQUIRED = "INVESTIGATION_REQUIRED" # Data quality, sensor, or operational anomaly must be resolved first
    NON_ACTIONABLE = "NON_ACTIONABLE"               # Prediction invalid or uncharacterized; cannot base operational action on this result
```

### 4.2 Secondary Advisory Container (`types.py`)

```python
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
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "advisory_id": self.advisory_id,
            "decision_class": self.decision_class.value,
            "priority": self.priority.value,
            "actionability": self.actionability.value,
            "summary": self.summary,
            "rationale": self.rationale,
            "matched_condition_id": self.matched_condition_id,
            "metadata": dict(self.metadata),
        }
```

### 4.3 Output Container (`types.py`)

```python
@dataclass(frozen=True)
class PrognosticDecisionResult:
    """Immutable, auditable top-level prognostic decision and recommendation record.
    
    Guarantees:
    1. Zero synthetic confidence scores.
    2. Explicit safety authority declaration (advisory-only, physical BMS remains control authority).
    3. Full provenance linking back to Level 6.5 Evaluation ID and DecisionPolicy ID/version.
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
    secondary_advisories: Sequence[SecondaryAdvisory] = field(default_factory=tuple)
    validity_limitations: Sequence[str] = field(default_factory=tuple)
    evaluation_reference_id: str = ""
    is_safety_critical_actuation: bool = False
    safety_disclaimer: str = (
        "ADVISORY ONLY: TwinVolt analytical decisions do not command physical actuators. "
        "The physical Battery Management System (BMS) remains the sole safety and protection authority."
    )
    reproducibility_metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        """Returns True if the primary recommendation represents an actionable operational task."""
        return self.primary_actionability == Actionability.ACTIONABLE

    def to_dict(self) -> dict[str, Any]:
        """Serializes decision result to a pure dictionary."""
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
            "secondary_advisories": [a.to_dict() for a in self.secondary_advisories],
            "validity_limitations": list(self.validity_limitations),
            "evaluation_reference_id": self.evaluation_reference_id,
            "is_actionable": self.is_actionable,
            "is_safety_critical_actuation": self.is_safety_critical_actuation,
            "safety_disclaimer": self.safety_disclaimer,
            "reproducibility_metadata": dict(self.reproducibility_metadata),
        }
```

---

## 5. DecisionCondition Design

The `DecisionCondition` expresses the criteria required for a `DecisionRule` to match against a `PrognosticEvaluationResult`.

```python
@dataclass(frozen=True)
class DecisionCondition:
    """Immutable declarative matching condition for a prognostic decision rule.
    
    All specified fields must match (logical AND). Unspecified (None) fields are unconstrained.
    """
    condition_id: str
    # Evaluation Status Filtering
    required_evaluation_statuses: Optional[Sequence[EvaluationStatus]] = None
    forbidden_evaluation_statuses: Optional[Sequence[EvaluationStatus]] = None
    
    # EOL State Filtering
    required_eol_states: Optional[Sequence[EOLState]] = None
    
    # RUL Threshold Gating
    rul_threshold_value: Optional[float] = None
    rul_comparison_operator: Optional[ComparisonOperator] = None
    rul_domain: Optional[HorizonDomain] = None
    
    # Uncertainty & Evidence Gating
    required_uncertainty_statuses: Optional[Sequence[UncertaintyStatus]] = None
    min_evidence_strength: Optional[EvidenceStrength] = None
    max_evidence_strength: Optional[EvidenceStrength] = None
    
    # Data Quality Gating
    require_valid_data_quality: bool = False
    require_decision_usable: bool = False
    
    description: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.condition_id or not isinstance(self.condition_id, str):
            raise ValueError("condition_id must be a non-empty string.")
        
        # Validate numeric threshold pairing
        if self.rul_threshold_value is not None:
            if not isinstance(self.rul_threshold_value, (int, float)) or math.isnan(self.rul_threshold_value) or math.isinf(self.rul_threshold_value):
                raise ValueError(f"rul_threshold_value must be a finite float, got {self.rul_threshold_value}.")
            if self.rul_comparison_operator is None:
                raise ValueError("rul_comparison_operator is required when rul_threshold_value is specified.")
            if not isinstance(self.rul_comparison_operator, ComparisonOperator):
                raise TypeError(f"Expected ComparisonOperator, got {type(self.rul_comparison_operator).__name__}.")
        elif self.rul_comparison_operator is not None:
            raise ValueError("rul_threshold_value is required when rul_comparison_operator is specified.")

    def matches(self, evaluation: PrognosticEvaluationResult) -> tuple[bool, list[str]]:
        """Evaluates whether the given PrognosticEvaluationResult satisfies all constraints.
        
        Returns:
            (is_matched, reasons): Boolean match indicator and list of satisfied condition clauses.
        """
        reasons: list[str] = []
        
        # 1. Evaluation Status check
        if self.required_evaluation_statuses is not None:
            if evaluation.evaluation_status not in self.required_evaluation_statuses:
                return False, []
            reasons.append(f"Evaluation status is {evaluation.evaluation_status.value}.")
        
        if self.forbidden_evaluation_statuses is not None:
            if evaluation.evaluation_status in self.forbidden_evaluation_statuses:
                return False, []
        
        # 2. Usability gate
        if self.require_decision_usable and not evaluation.validity.is_usable_for_decision:
            return False, []
        
        # 3. Data quality gate
        if self.require_valid_data_quality and evaluation.validity.data_quality != PrognosticStatus.VALID:
            return False, []
        
        # 4. EOL State check
        if self.required_eol_states is not None:
            if evaluation.eol_assessment.eol_state not in self.required_eol_states:
                return False, []
            reasons.append(f"EOL state is {evaluation.eol_assessment.eol_state.value}.")
        
        # 5. Uncertainty status check
        if self.required_uncertainty_statuses is not None:
            unc_status = evaluation.uncertainty.status if evaluation.uncertainty else UncertaintyStatus.UNDEFINED
            if unc_status not in self.required_uncertainty_statuses:
                return False, []
            reasons.append(f"Uncertainty status is {unc_status.value}.")
        
        # 6. Evidence strength check
        if self.min_evidence_strength is not None or self.max_evidence_strength is not None:
            ev_strength = evaluation.evidence.overall_strength if evaluation.evidence else EvidenceStrength.INSUFFICIENT
            strength_order = [
                EvidenceStrength.INSUFFICIENT,
                EvidenceStrength.VERY_WEAK,
                EvidenceStrength.WEAK,
                EvidenceStrength.MODERATE,
                EvidenceStrength.STRONG,
                EvidenceStrength.VERY_STRONG,
            ]
            current_idx = strength_order.index(ev_strength)
            
            if self.min_evidence_strength is not None:
                min_idx = strength_order.index(self.min_evidence_strength)
                if current_idx < min_idx:
                    return False, []
                reasons.append(f"Evidence strength ({ev_strength.value}) meets minimum ({self.min_evidence_strength.value}).")
            
            if self.max_evidence_strength is not None:
                max_idx = strength_order.index(self.max_evidence_strength)
                if current_idx > max_idx:
                    return False, []
                reasons.append(f"Evidence strength ({ev_strength.value}) within maximum ({self.max_evidence_strength.value}).")
        
        # 7. RUL Threshold check
        if self.rul_threshold_value is not None:
            if not evaluation.prediction or evaluation.prediction.rul_value is None:
                return False, []
            
            # Domain check
            if self.rul_domain is not None and evaluation.prediction.rul_domain != self.rul_domain:
                return False, []
            
            val = evaluation.prediction.rul_value
            thresh = self.rul_threshold_value
            op = self.rul_comparison_operator
            
            matched = False
            if op == ComparisonOperator.LESS_THAN_OR_EQUAL:
                matched = val <= thresh
            elif op == ComparisonOperator.LESS_THAN:
                matched = val < thresh
            elif op == ComparisonOperator.GREATER_THAN_OR_EQUAL:
                matched = val >= thresh
            elif op == ComparisonOperator.GREATER_THAN:
                matched = val > thresh
            elif op == ComparisonOperator.EQUALS:
                matched = math.isclose(val, thresh, abs_tol=1e-9)
            
            if not matched:
                return False, []
            reasons.append(f"RUL ({val:.2f} {evaluation.prediction.rul_unit}) {op.value} {thresh:.2f}.")
        
        return True, reasons
```

---

## 6. DecisionPolicy Design

The `DecisionPolicy` is the immutable, auditable entity that aggregates rules, enforces uniqueness, and defines deterministic precedence.

```python
@dataclass(frozen=True)
class DecisionRule:
    """Immutable rule entity binding a condition to a concrete operational decision."""
    rule_id: str
    precedence_rank: int                        # Explicit integer rank: lower integer = higher precedence (e.g. 1 before 10)
    decision_class: DecisionClass
    priority: RecommendationPriority
    actionability: Actionability
    condition: DecisionCondition
    recommendation_template: str               # Template supporting {rul_value}, {rul_unit}, {system_id}, {eol_state}
    rationale_template: str
    rule_name: str = ""
    description: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rule_id or not isinstance(self.rule_id, str):
            raise ValueError("rule_id must be a non-empty string.")
        if not isinstance(self.precedence_rank, int) or self.precedence_rank < 0:
            raise ValueError(f"precedence_rank must be a non-negative integer, got {self.precedence_rank}.")
        if not isinstance(self.decision_class, DecisionClass):
            raise TypeError(f"Expected DecisionClass, got {type(self.decision_class).__name__}.")
        if not isinstance(self.priority, RecommendationPriority):
            raise TypeError(f"Expected RecommendationPriority, got {type(self.priority).__name__}.")
        if not isinstance(self.actionability, Actionability):
            raise TypeError(f"Expected Actionability, got {type(self.actionability).__name__}.")
        if not isinstance(self.condition, DecisionCondition):
            raise TypeError(f"Expected DecisionCondition, got {type(self.condition).__name__}.")
        if not self.recommendation_template:
            raise ValueError("recommendation_template cannot be empty.")
        if not self.rationale_template:
            raise ValueError("rationale_template cannot be empty.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "precedence_rank": self.precedence_rank,
            "decision_class": self.decision_class.value,
            "priority": self.priority.value,
            "actionability": self.actionability.value,
            "condition_id": self.condition.condition_id,
            "recommendation_template": self.recommendation_template,
            "rationale_template": self.rationale_template,
            "rule_name": self.rule_name,
            "description": self.description,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class DecisionPolicy:
    """Immutable, fully-auditable decision policy for prognostic recommendation synthesis."""
    policy_id: str
    policy_name: str
    version: str
    target_domain: Optional[HorizonDomain]
    rules: Sequence[DecisionRule]
    default_decision_class: DecisionClass = DecisionClass.CONTINUE_MONITORING
    default_priority: RecommendationPriority = RecommendationPriority.INFORMATIONAL
    default_actionability: Actionability = Actionability.ADVISORY_ONLY
    default_recommendation: str = "Continue standard operational monitoring cadence."
    default_rationale: str = "Operating metrics within nominal degradation bounds; no condition threshold triggered."
    description: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.policy_id or not isinstance(self.policy_id, str):
            raise ValueError("policy_id must be a non-empty string.")
        if not self.policy_name or not isinstance(self.policy_name, str):
            raise ValueError("policy_name must be a non-empty string.")
        if not self.version or not isinstance(self.version, str):
            raise ValueError("version must be a non-empty string.")
        if self.target_domain is not None and not isinstance(self.target_domain, HorizonDomain):
            raise TypeError(f"Expected HorizonDomain, got {type(self.target_domain).__name__}.")
        
        # Policy Invariant Validations
        self.validate()

    def validate(self) -> None:
        """Validates all internal consistency and determinism invariants of the policy."""
        rule_ids = set()
        ranks = set()
        
        for rule in self.rules:
            if not isinstance(rule, DecisionRule):
                raise TypeError(f"Expected DecisionRule, got {type(rule).__name__}.")
            
            # 1. Enforce unique rule_ids
            if rule.rule_id in rule_ids:
                raise ValueError(f"Duplicate rule_id '{rule.rule_id}' in policy '{self.policy_id}'.")
            rule_ids.add(rule.rule_id)
            
            # 2. Enforce strictly unique precedence_rank for deterministic ordering
            if rule.precedence_rank in ranks:
                raise ValueError(
                    f"Duplicate precedence_rank {rule.precedence_rank} in policy '{self.policy_id}'. "
                    f"Rule ranks must be strictly unique to guarantee deterministic tie-breaking."
                )
            ranks.add(rule.precedence_rank)
            
            # 3. Domain compatibility validation
            if self.target_domain is not None and rule.condition.rul_domain is not None:
                if rule.condition.rul_domain != self.target_domain:
                    raise ValueError(
                        f"Rule '{rule.rule_id}' specifies domain '{rule.condition.rul_domain.value}' "
                        f"incompatible with policy target_domain '{self.target_domain.value}'."
                    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "version": self.version,
            "target_domain": self.target_domain.value if self.target_domain else None,
            "rules": [r.to_dict() for r in self.rules],
            "default_decision_class": self.default_decision_class.value,
            "default_priority": self.default_priority.value,
            "default_actionability": self.default_actionability.value,
            "default_recommendation": self.default_recommendation,
            "default_rationale": self.default_rationale,
            "description": self.description,
            "metadata": dict(self.metadata),
        }
```

---

## 7. Policy Validation Model

A policy is rejected **at construction time** (raising explicit exceptions) if any of the following validation rules fail:

| Violation | Exception Raised | Prevention Guarantee |
| :--- | :--- | :--- |
| Empty `policy_id`, `policy_name`, or `version` | `ValueError` | Complete provenance and identity tracking |
| Duplicate `rule_id` | `ValueError` | Unambiguous rule identification in audit trails |
| Duplicate `precedence_rank` | `ValueError` | **Zero ambiguity in tie-breaking; 100% deterministic ranking** |
| Negative `precedence_rank` | `ValueError` | Well-defined total ordering |
| Non-finite or NaN threshold values | `ValueError` | Numerical IEEE-754 safety |
| Threshold specified without `ComparisonOperator` | `ValueError` | Complete mathematical predicate specification |
| Rule domain incompatible with Policy `target_domain` | `ValueError` | Prevention of cross-domain unit errors |
| Invalid object types in rule collections | `TypeError` | Strict static type integrity |

---

## 8. Decision Precedence Model

When evaluating a `PrognosticEvaluationResult`, multiple rules may match simultaneously (e.g. `EOL_REACHED` is true, data quality has warnings, and RUL is below threshold).

### Deterministic 4-Stage Precedence Pipeline

```
[PrognosticEvaluationResult] + [DecisionPolicy]
                     │
       STAGE 1: Compatibility Validation
                     │
       STAGE 2: Fatal Validity Gating
                     │
       STAGE 3: Deterministic Rule Matching (Ordered by Precedence Rank)
                     │
       STAGE 4: Primary Selection & Secondary Preservation
                     │
         [PrognosticDecisionResult]
```

### Stage Details

1. **Stage 1: Policy Compatibility Check**
   - If the evaluation result's `prediction.rul_domain` contradicts the policy's `target_domain`, the engine does not perform numerical comparisons. It produces a `DecisionStatus.INCOMPATIBLE_EVALUATION` with `DecisionClass.INDETERMINATE_STATE`.

2. **Stage 2: Fatal Validity Gating**
   - If `evaluation.validity.is_usable_for_decision == False` (e.g. `DATA_QUALITY_FAILED`, `INSUFFICIENT_DATA`, `INVALID_EOL_CRITERION`), degradation-based action rules (e.g. `PLAN_MAINTENANCE` triggered by a nominal RUL number) are **prohibited from becoming primary actions**.
   - If the policy contains an explicit data-quality / validity-handling rule matching this state, that rule matches.
   - If no explicit rule matches the invalid state, the engine defaults to:
     - Status: `DecisionStatus.BLOCKED_BY_VALIDITY`
     - Decision Class: `DATA_QUALITY_ACTION_REQUIRED` (if data quality failed) or `OUT_OF_DOMAIN` / `INSUFFICIENT_EVIDENCE` (corresponding to the Level 6.5 status)
     - Priority: `RecommendationPriority.HIGH`
     - Actionability: `Actionability.INVESTIGATION_REQUIRED`
     - Primary Rationale: Direct extraction from `evaluation.validity.limitations`.

3. **Stage 3: Rule Matching & Rank Sorting**
   - The engine iterates through `policy.rules`, sorted strictly by `rule.precedence_rank` in ascending order (rank 1 evaluated before rank 2).
   - For every rule where `rule.condition.matches(evaluation)` returns `True`, the rule is recorded into `matched_rules`.

4. **Stage 4: Primary Selection & Secondary Advisory Assembly**
   - **Primary Decision**: The matched rule with the lowest `precedence_rank` becomes the `primary_decision_class`, `primary_recommendation`, `primary_priority`, `primary_actionability`, and `primary_rationale`.
   - **Secondary Advisories**: All *other* matched rules (lower precedence) are transformed into structured `SecondaryAdvisory` records.
   - **Limitations & Diagnostics**: All Level 6.5 `validity.limitations` and `validity.diagnostic_notes` are preserved into `validity_limitations`.

---

## 9. Validity Interaction Model

The decision layer rigorously handles all 13 Level 6.5 evaluation states:

| Level 6.5 State | Evaluation Usability | Policy Gating Behavior | Default Primary Decision Class | Default Priority | Actionability |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Valid RUL (Nominal)** | `True` | Standard RUL threshold rules evaluated | `CONTINUE_MONITORING` (or matched RUL rule) | `INFORMATIONAL` / `HIGH` | `ACTIONABLE` / `ADVISORY_ONLY` |
| **2. Valid RUL + Unavailable Uncertainty** | `True` | Point estimate usable; uncertainty limitation recorded | `CONTINUE_MONITORING` (or matched RUL rule) | Per policy rule | `ADVISORY_ONLY` (with limitation note) |
| **3. Valid RUL + Weak Evidence** | `True` | Action rules gated if policy requires min evidence | `INSUFFICIENT_EVIDENCE` (if gated) or matched rule | `MEDIUM` | `ADVISORY_ONLY` |
| **4. VALID_WITH_LIMITATIONS** | `True` | Actionable, but secondary advisories capture limitations | Evaluates matched rules; captures limitations | Per policy rule | `ACTIONABLE` |
| **5. INSUFFICIENT_DATA** | `False` | **Blocked**: RUL rules cannot fire | `DATA_QUALITY_ACTION_REQUIRED` | `HIGH` | `INVESTIGATION_REQUIRED` |
| **6. INSUFFICIENT_HISTORY** | `False` | **Blocked**: Extrapolation ungrounded | `INSUFFICIENT_EVIDENCE` | `MEDIUM` | `ADVISORY_ONLY` |
| **7. DATA_QUALITY_FAILED** | `False` | **Blocked**: Sensor/telemetry integrity compromised | `DATA_QUALITY_ACTION_REQUIRED` | `CRITICAL` / `HIGH` | `INVESTIGATION_REQUIRED` |
| **8. OUT_OF_DOMAIN** | `False` | **Blocked**: Operating regime outside valid envelope | `OUT_OF_DOMAIN` | `HIGH` | `INVESTIGATION_REQUIRED` |
| **9. Invalid EOL Criterion** | `False` | **Blocked**: Configuration invalid | `DATA_QUALITY_ACTION_REQUIRED` | `HIGH` | `INVESTIGATION_REQUIRED` |
| **10. EOL_ALREADY_REACHED** | `True` / `False` | EOL rules match immediately; takes highest precedence | `EOL_REACHED` / `PLAN_MAINTENANCE` | `CRITICAL` | `ACTIONABLE` |
| **11. EOL_NOT_REACHED** | `True` | Normal RUL threshold rules apply | Per policy rule | Per policy rule | `ACTIONABLE` |
| **12. EOL_PROJECTED** | `True` | Normal RUL threshold rules apply | Per policy rule | Per policy rule | `ACTIONABLE` |
| **13. Indeterminate EOL State** | `False` | **Blocked**: State uncharacterized | `INDETERMINATE_STATE` | `MEDIUM` | `NON_ACTIONABLE` |

---

## 10. Single vs. Multiple Recommendation Analysis (Design Question #1)

### Architectural Evaluation

- **Option A: Single Recommendation Only**
  - *Pros:* Simple flat UI output.
  - *Cons:* Destructive information loss. If a battery has low RUL *and* weak observational evidence *and* severe sensor drift warnings, picking only one suppresses critical diagnostics.
- **Option B: Primary Recommendation PLUS Structured Secondary Advisories (SELECTED)**
  - *Pros:*
    1. Delivers one definitive primary triage recommendation for operational workflows.
    2. Preserves every secondary matched rule as an auditable `SecondaryAdvisory`.
    3. Preserves all Level 6.5 validity limitations and diagnostic notes.
    4. Enables rich dashboards, deep-dive root cause analysis, and automated fleet alerts without collapsing failure modes.
  - *Cons:* Slightly richer result container (fully mitigated by clean dataclass design).

**Architectural Decision:** **Option B is selected**.

---

## 11. Safety Authority Separation

```
┌────────────────────────────────────────────────────────┐
│                   PHYSICAL BMS                         │
│           (Sole Safety & Actuation Authority)          │
│  - Contactor Control        - Short-Circuit Protection │
│  - Over-Current Cutoff      - Thermal Runaway Shutdown │
│  - Cell Balancing           - Hardware Interlocks      │
└───────────────────────────▲────────────────────────────┘
                            │ (Telemetry Ingestion Only)
┌───────────────────────────┴────────────────────────────┐
│                    TWINVOLT                            │
│           (Analytical Digital Twin Platform)           │
│  Level 6.6: Prognostic Decision & Recommendation       │
│  - Analytical Advisory Only                            │
│  - Maintenance Planning Support                        │
│  - Monitoring Cadence Recommendations                  │
│  - Sensor Data Quality Investigation Advisories        │
└────────────────────────────────────────────────────────┘
```

### Safety Guarantees
1. `is_safety_critical_actuation` is permanently set to `False` on all decision results.
2. Every output carries an immutable `safety_disclaimer` string.
3. Level 6.6 has **zero** driver, hardware, CAN bus, GPIO, or actuator interfaces.
4. Recommendations are semantic strings and enums intended for human operators, maintenance management systems (CMMS), or supervisory planners.

---

## 12. Determinism Model

Given identical `PrognosticEvaluationResult` and `DecisionPolicy` inputs, Level 6.6 produces **byte-for-byte identical decisions and rationales**:

1. **Pure Stateless Execution:** `PrognosticDecisionEngine.evaluate()` has no internal mutable state.
2. **Deterministic Precedence:** Strict uniqueness of `precedence_rank` prevents non-deterministic dictionary or set iteration order.
3. **No External Dependencies:** Zero calls to random number generators, wall-clock time within math evaluation, network endpoints, or environment variables.
4. **Deterministic Timestamp Handling:** The evaluation timestamp is derived directly from the input trajectory's `evaluation_timestamp_ns` (or explicitly supplied integer). `created_at_utc` is preserved or explicitly generated for tracking.

---

## 13. Reproducibility Model

Every `PrognosticDecisionResult` contains complete provenance to answer: *"Why did TwinVolt produce this recommendation?"*

- `policy_id` and `policy_version`: Identifies the exact rulebook used.
- `primary_rule_id`: Identifies the specific winning rule.
- `matched_rule_ids`: Lists all rules that met threshold conditions.
- `evaluation_reference_id`: Points directly to Level 6.5 `PrognosticEvaluationResult.evaluation_id`.
- `reproducibility_metadata`: Contains:
  - Input RUL value, domain, and unit.
  - EOL state and threshold value.
  - Uncertainty status and evidence strength.
  - Validity flags (`data_quality`, `history_sufficiency`, `domain_validity`).
  - Precedence resolution log.

---

## 14. Immutability Strategy

1. All domain classes (`DecisionStatus`, `DecisionClass`, `RecommendationPriority`, `Actionability`, `SecondaryAdvisory`, `DecisionCondition`, `DecisionRule`, `DecisionPolicy`, `PrognosticDecisionResult`) are `@dataclass(frozen=True)` or `Enum`.
2. Sequence fields use `tuple` (or immutable sequences) rather than mutable lists.
3. Metadata dictionaries are copied and wrapped as read-only mappings on instantiation.
4. The engine **never mutates** the incoming `PrognosticEvaluationResult`, `DegradationTrajectory`, or `RULPredictionResult`.

---

## 15. Universality & Chemistry Independence

Level 6.6 contains **zero** hardcoded battery constants:
- No hardcoded capacity values (e.g. 2.4 Ah).
- No hardcoded cycle-life thresholds (e.g. 100 cycles).
- No chemistry-specific assumptions (LFP, NMC, NCA, Sodium-ion, Lead-acid).
- All physical units, threshold numbers, and domain rules are injected exclusively via `DecisionPolicy`.

---

## 16. Unit & Domain Compatibility

1. The policy defines `target_domain: Optional[HorizonDomain]`.
2. When evaluating RUL rules, the rule condition's `rul_domain` is validated against `prediction.rul_domain`.
3. If an RUL rule specifies `HorizonDomain.CYCLE` and the prediction is in `HorizonDomain.TIME`, the condition matches `False` and logs an incompatible domain advisory. Cross-domain scalar comparisons are strictly forbidden.

---

## 17. Serialization Strategy

All Level 6.6 value objects implement `.to_dict()` producing pure, standard Python types (`dict`, `list`, `str`, `int`, `float`, `bool`, `None`).
- Enums are serialized to their string `.value`.
- Floats are rounded to 6 decimal places for deterministic JSON export.
- Dict outputs are 100% JSON-serializable via `json.dumps()` without custom encoders.

---

## 18. Comprehensive Test Strategy

The test suite will be implemented in `tests/unit/prognostics/decision/`:

```
tests/unit/prognostics/decision/
├── __init__.py
├── test_types.py                   # Enums, SecondaryAdvisory, PrognosticDecisionResult contracts
├── test_policy.py                  # Policy validation, duplicate detection, boundary conditions
├── test_engine.py                  # Evaluation engine, precedence resolution, deterministic outputs
├── test_validity_interaction.py    # All 13 Level 6.5 validity states and gating behaviors
└── test_semantics_and_safety.py    # Safety authority separation, immutability, zero-mutation, universality
```

### Specific Test Cases (35 Mandatory Areas)

1. `test_immutable_contracts`: Verify `FrozenInstanceError` on modification of types, policies, rules, and results.
2. `test_policy_validation_success`: Valid policy passes validation.
3. `test_policy_validation_empty_fields`: Empty IDs/names raise `ValueError`.
4. `test_policy_validation_duplicate_rule_ids`: Duplicate `rule_id` raises `ValueError`.
5. `test_policy_validation_duplicate_precedence_ranks`: Duplicate `precedence_rank` raises `ValueError`.
6. `test_policy_validation_incompatible_domain`: Rule domain mismatch raises `ValueError`.
7. `test_deterministic_evaluation_identical_inputs`: Identical runs produce identical dictionaries.
8. `test_valid_rul_matching_policy`: RUL below threshold triggers expected `PLAN_MAINTENANCE` rule.
9. `test_valid_rul_no_matching_policy`: Fallback to default policy rule (`CONTINUE_MONITORING`).
10. `test_valid_rul_unavailable_uncertainty`: Point estimate triggers rule; advisory notes unquantified uncertainty.
11. `test_valid_rul_weak_evidence`: Evidence gating correctly suppresses actionable maintenance if configured.
12. `test_valid_with_limitations`: Produces recommendation while capturing all Level 6.5 limitations.
13. `test_insufficient_data_gating`: `INSUFFICIENT_DATA` blocks RUL action rule; returns `DATA_QUALITY_ACTION_REQUIRED`.
14. `test_insufficient_history_gating`: `INSUFFICIENT_HISTORY` blocks RUL action rule; returns `INSUFFICIENT_EVIDENCE`.
15. `test_data_quality_failed_gating`: `DATA_QUALITY_FAILED` blocks RUL action rule; returns `DATA_QUALITY_ACTION_REQUIRED` with `CRITICAL` priority.
16. `test_out_of_domain_gating`: `OUT_OF_DOMAIN` blocks RUL action rule; returns `OUT_OF_DOMAIN` advisory.
17. `test_invalid_eol_criterion`: Blocks decision; returns `INVESTIGATION_REQUIRED`.
18. `test_eol_already_reached`: `EOLState.ALREADY_REACHED` triggers `EOL_REACHED` rule with `CRITICAL` priority.
19. `test_eol_not_reached`: Standard degradation rule matching.
20. `test_eol_projected`: Standard projection rule matching.
21. `test_indeterminate_eol`: Returns `INDETERMINATE_STATE`.
22. `test_numeric_boundary_less_than_or_equal`: Verifies exact threshold boundary inclusion.
23. `test_numeric_boundary_less_than`: Verifies exact threshold boundary exclusion.
24. `test_multiple_matching_conditions`: Lower `precedence_rank` wins; remaining matches preserved in `secondary_advisories`.
25. `test_poor_evidence_gating`: Poor evidence never silently produces actionable physical maintenance.
26. `test_no_hidden_default_thresholds`: Changing policy thresholds directly changes decision boundary.
27. `test_chemistry_independence`: Works identically across arbitrary chemistry metadata.
28. `test_provenance_preservation`: `policy_id`, `version`, and `evaluation_reference_id` match inputs.
29. `test_matched_condition_preservation`: All matching condition IDs appear in `matched_rule_ids`.
30. `test_rationale_template_formatting`: `{rul_value}`, `{rul_unit}`, `{system_id}` interpolated accurately.
31. `test_serialization_round_trip`: `to_dict()` outputs valid, JSON-serializable dictionary.
32. `test_no_live_twin_mutation`: Zero side-effects on Twin state.
33. `test_no_level65_mutation`: Input `PrognosticEvaluationResult` unmodified after evaluation.
34. `test_zero_runtime_and_hardware_imports`: Verify module does not import `runtime`, `api`, `ui`, or `gateway`.
35. `test_safety_authority_disclaimer`: Disclaimer present and `is_safety_critical_actuation == False`.

---

## 19. Failure & Edge-Case Matrix

| Failure / Edge Case | System Behavior | Result Status | Result Class | Priority | Actionability |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Missing / Empty Policy Rules** | Uses policy default rule | `DEFAULT_RULE_APPLIED` | `CONTINUE_MONITORING` | `INFORMATIONAL` | `ADVISORY_ONLY` |
| **No Condition Matched** | Uses policy default rule | `DEFAULT_RULE_APPLIED` | `CONTINUE_MONITORING` | `INFORMATIONAL` | `ADVISORY_ONLY` |
| **Domain Mismatch** (e.g. Cycle vs Time) | Skips incompatible rule; logs note | `INCOMPATIBLE_EVALUATION` / `DEFAULT_RULE_APPLIED` | `INDETERMINATE_STATE` | `MEDIUM` | `ADVISORY_ONLY` |
| **RUL = 0.0 (Valid Crossing)** | Matches `<= threshold` rules | `EVALUATED` | `APPROACHING_EOL` / `EOL_REACHED` | `CRITICAL` | `ACTIONABLE` |
| **RUL = None (Failed Prediction)** | Numerical conditions evaluate `False` | `BLOCKED_BY_VALIDITY` | Derived from Level 6.5 status | `HIGH` | `INVESTIGATION_REQUIRED` |
| **Degradation Rate = 0.0 (Infinite RUL)** | RUL is None; EOL not reached | `EVALUATED` | `CONTINUE_MONITORING` | `INFORMATIONAL` | `ADVISORY_ONLY` |
| **Degradation Improving (Negative Rate)** | RUL is None; EOL not reached | `EVALUATED` | `CONTINUE_MONITORING` | `INFORMATIONAL` | `ADVISORY_ONLY` |
| **Conflicting Rules Match** | Resolved strictly by `precedence_rank` | `EVALUATED` | Top-ranked rule class | Per top rule | Per top rule |

---

## 20. Explicit Non-Goals

To maintain strict architectural isolation, the following are **explicit non-goals** for Level 6.6:
1. **NO New RUL Estimator:** Level 6.6 does not calculate or adjust RUL values.
2. **NO New Uncertainty Quantification:** Level 6.6 does not calculate variance, standard errors, or coverage bounds.
3. **NO Machine Learning / Bayesian Decision Networks:** No opaque classifiers or probability heuristics.
4. **NO BMS Actuation or Hardware Control:** No contactor commands, current limits, or balancing triggers.
5. **NO Hardcoded Universal Thresholds:** No embedded domain assumptions outside of explicit policies.
6. **NO Live Twin / Repository Mutation:** Pure stateless analytical evaluation only.
7. **NO Framework / Web Service Integration:** No FastAPI routes, WebSockets, or UI widgets in Level 6.6.

---

## 21. Implementation Sequence

When implementation approval is granted, execution will proceed in strict order:

```
Step 1: Create types.py (DecisionStatus, DecisionClass, RecommendationPriority, Actionability, SecondaryAdvisory, PrognosticDecisionResult)
   ↓
Step 2: Create policy.py (DecisionCondition, DecisionRule, DecisionPolicy, validation invariants)
   ↓
Step 3: Create recommendation.py (DecisionRecommendation, template synthesizers)
   ↓
Step 4: Create engine.py (PrognosticDecisionEngine)
   ↓
Step 5: Create __init__.py exports for src/prognostics/decision/ and update src/prognostics/__init__.py
   ↓
Step 6: Create comprehensive unit test suite in tests/unit/prognostics/decision/ (test_types.py, test_policy.py, test_engine.py, test_validity_interaction.py, test_semantics_and_safety.py)
   ↓
Step 7: Execute full test verification (target: >35 new tests passing, 0 regressions across 783 baseline tests)
```

---

## 22. Verification Commands

```powershell
# 1. Run targeted Level 6.6 decision unit tests
python -m pytest tests/unit/prognostics/decision/ -v

# 2. Run entire Level 6 prognostics test suite
python -m pytest tests/unit/prognostics/ -v

# 3. Run full TwinVolt repository regression suite
python -m pytest
```

---

## 23. Risks and Mitigations

| Risk | Severity | Mitigation |
| :--- | :--- | :--- |
| **Rule Collision / Ambiguous Precedence** | High | Enforce strictly unique `precedence_rank` at policy validation time. |
| **Silent Suppression of Data Quality Failures** | Critical | Enforce fatal validity gating: invalid Level 6.5 evaluations cannot trigger physical maintenance action rules. |
| **Cross-Domain Unit Comparison Errors** | Medium | Validate rule `rul_domain` against policy `target_domain` and evaluation result `prediction.rul_domain`. |
| **Misinterpretation as BMS Control** | Critical | Prominently stamp every result with `safety_disclaimer` and `is_safety_critical_actuation = False`. |

---

## ARCHITECTURAL DECISION

1. **Recommended Package Structure:**
   - `src/prognostics/decision/` containing `__init__.py`, `types.py`, `policy.py`, `recommendation.py`, and `engine.py`.
2. **Recommended Domain Contracts:**
   - `DecisionStatus`, `DecisionClass`, `RecommendationPriority`, `Actionability`, `SecondaryAdvisory`, `DecisionCondition`, `DecisionRule`, `DecisionPolicy`, `PrognosticDecisionResult`.
3. **Recommended Precedence Strategy:**
   - Deterministic 4-stage pipeline combining fatal validity gating with strictly unique integer `precedence_rank` sorting.
4. **Recommended Recommendation Output Strategy:**
   - Primary decision recommendation plus structured collection of secondary advisories and validity limitations (Option B).
5. **Locked Contract Compatibility Status:**
   - **100% Compatible.** Levels 6.1 through 6.5 provide complete, strongly-typed inputs (`PrognosticEvaluationResult`, `EvaluationValidity`, `EOLAssessment`, `RULPredictionResult`, `UncertaintyEvaluationResult`). No locked contract requires modification.
6. **Unresolved Questions:**
   - None. All 5 Critical Design Questions have been resolved with strict, auditable architectural guarantees.
7. **Implementation Readiness:**
   - **READY.** Implementation can proceed immediately upon user instruction without altering any locked layer.

---
*END OF SPECIFICATION — DESIGN-ONLY / NO IMPLEMENTATION PERFORMED*
