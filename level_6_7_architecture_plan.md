# Level 6.7 — Prognostic Pipeline Orchestration & Multi-Criterion Assessment Engine
## Architectural Planning & Specification Document

**Author:** TwinVolt Core Architecture Team  
**Status:** **PLANNING ONLY / DESIGN-ONLY (NO IMPLEMENTATION)**  
**Target Package:** `src/prognostics/pipeline/`  
**Target Tests:** `tests/unit/prognostics/pipeline/`  
**Dependencies:** Level 0 through Level 6.6 (Strictly Locked & Read-Only)  

---

## Executive Summary

Levels 6.1 through 6.6 of the TwinVolt Universal Battery Digital Twin platform establish a complete, scientifically rigorous, and metrologically pure prognostics toolchain:
- **Level 6.1:** Domain Contracts, Horizons, Metrological Provenance, and EOL Definitions.
- **Level 6.2:** Degradation Trajectories and Multi-Dimensional Feature Extraction.
- **Level 6.3:** Deterministic Remaining Useful Life (RUL) Estimation.
- **Level 6.4:** Metrological Uncertainty Propagation and Observational Evidence Auditing.
- **Level 6.5:** Single-Criterion EOL Boundary Assessment and Multi-Dimensional Validity Gating.
- **Level 6.6:** Single-Criterion Decision Policy Interpretation and Advisory Recommendation Synthesis.

However, in the current codebase, these six layers exist as **individual, decoupled analytical units**. Furthermore, every physical battery degrades simultaneously across **multiple competing physical degradation mechanisms** (e.g., active lithium loss resulting in capacity fading, SEI growth resulting in ohmic resistance increase, and cathode degradation resulting in peak power reduction). 

Evaluating a battery against only a single scalar End-of-Life (EOL) definition creates **single-criterion blindness**: if an operator only monitors capacity retention ($SOH_C \le 80\%$), the digital twin will fail to recognize an impending failure where internal resistance growth ($R_0 \ge 2.0\times$) crosses its critical threshold first.

**Level 6.7 (Prognostic Pipeline Orchestration & Multi-Criterion Assessment Engine)** is the logical and necessary capstone of the Level 6 prognostics subsystem. It accomplishes two fundamental architectural requirements:
1. **End-to-End Pipeline Orchestration:** Seamless, pure, and deterministic execution linking Level 6.2 feature extraction $\rightarrow$ Level 6.3 estimation $\rightarrow$ Level 6.4 uncertainty $\rightarrow$ Level 6.5 evaluation $\rightarrow$ Level 6.6 decision policy into a unified, reproducible workflow.
2. **Multi-Criterion Portfolio Assessment:** Concurrent evaluation of multi-mechanism EOL portfolios (e.g., Capacity, Resistance, Power, Throughput), deterministic resolution of the **Limiting Degradation Mechanism** (the shortest RUL / most urgent failure mode), and synthesis of a consolidated, top-level **`PrognosticAssessmentReport`**.

Level 6.7 remains a **pure, stateless domain layer**. It introduces zero machine learning, zero physical BMS actuation, and zero live Twin mutation.

```
┌────────────────────────────────────────────────────────────────────────┐
│               LEVEL 6 PROGNOSTICS ARCHITECTURE HIERARCHY               │
│                                                                        │
│  Level 6.1: Domain Contracts, Horizons, Provenance, EOLDefinition      │
│         ↓                                                              │
│  Level 6.2: Degradation Trajectories & Feature Extraction              │
│         ↓                                                              │
│  Level 6.3: Deterministic RUL Estimation Baseline                      │
│         ↓                                                              │
│  Level 6.4: Metrological Uncertainty & Evidence Strength Auditing      │
│         ↓                                                              │
│  Level 6.5: Single-Criterion Prognostic Evaluation & Validity Gating   │
│         ↓                                                              │
│  Level 6.6: Single-Criterion Decision Policy & Recommendation          │
│         ↓                                                              │
│ ╔════════════════════════════════════════════════════════════════════╗ │
│ ║ LEVEL 6.7: PIPELINE ORCHESTRATION & MULTI-CRITERION ASSESSMENT     ║ │
│ ║  - State-to-Trajectory Domain Adapter                              ║ │
│ ║  - Multi-Mechanism EOL Portfolio Dispatch (Capacity, R0, Power)    ║ │
│ ║  - Deterministic Limiting Degradation Mechanism Resolution         ║ │
│ ║  - Unified PrognosticAssessmentReport Top-Level Container          ║ │
│ ╚════════════════════════════════════════════════════════════════════╝ │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ↓
 [Future Application Tier: Runtime Instance / TwinApplicationService / REST API / UI]
```

---

## 1. Level 6.7 Objective

### 1.1 What Level 6.7 Accomplishes
1. **Unified Pipeline Orchestration:** Implements a single, pure, stateless domain entry point (`PrognosticPipelineEngine`) that coordinates the full prognostic execution from a raw degradation trajectory (or historical state sequence) to a final operational recommendation.
2. **Multi-Criterion EOL Portfolio Evaluation:** Evaluates a battery system simultaneously across an arbitrary portfolio of independent `EOLDefinition` criteria (e.g., Capacity Retention $\le 80\%$, Usable Capacity $\le 2.0\text{ Ah}$, Resistance Growth Ratio $\ge 2.0\times$, Peak Discharge Power $\le 50\text{ W}$).
3. **Limiting Mechanism Resolution:** Deterministically analyzes all evaluated criteria to identify the **Limiting Degradation Mechanism**—the specific degradation channel that establishes the shortest Remaining Useful Life, the nearest EOL crossing, or the highest recommendation triage priority.
4. **Multi-Mechanism Advisory Consolidation:** Synthesizes an authoritative primary operational recommendation based on the limiting mechanism while preserving secondary advisories and limitations from all non-limiting degradation channels.
5. **State History Trajectory Adapter:** Provides a pure, decoupled domain utility to transform sequences of historical `TwinStateRecord` or observation snapshots into strongly-typed, monotonically ordered `DegradationTrajectory` objects with metrological provenance tracking.
6. **Top-Level Prognostic Container:** Emits an immutable, fully serializable `PrognosticAssessmentReport` that encapsulates the complete multi-mechanism evaluation for downstream consumption by runtime services, replay engines, benchmarking suites, and supervisory UIs.

### 1.2 Why It Is Needed After Level 6.6
- **Elimination of Boilerplate in Application Services:** Currently, for an external caller (e.g., `TwinApplicationService` or a CLI evaluation script) to perform prognostics, it must manually instantiate and wire `TrajectoryFeatureExtractor` (6.2), `HistoricalLinearRULEstimator` (6.3), `PrognosticUncertaintyEngine` (6.4), `EOLEvaluator` (6.5), `EvaluationValidityEvaluator` (6.5), and `PrognosticDecisionEngine` (6.6). This violates domain encapsulation and risks inconsistent error handling.
- **Resolution of Real-World Competing Failure Modes:** Battery degradation is multi-dimensional. A battery under low-temperature cycling may suffer severe lithium plating and impedance rise ($R_0$) long before its nominal capacity drops to 80%. A digital twin restricted to single-criterion evaluation requires manual comparison of disjoint runs. Level 6.7 formalizes multi-criterion resolution inside the domain.

### 1.3 What Level 6.7 Explicitly Does NOT Solve
- **NO BMS Hardware Actuation:** Level 6.7 remains strictly analytical and advisory (`is_safety_critical_actuation = False`).
- **NO Background Polling or Daemon Threads:** Level 6.7 does not run internal threads, timers, or asynchronous event loops. It is invoked purely as a synchronous, deterministic function call.
- **NO Database / Disk Persistence:** Level 6.7 does not read from or write to disk, SQLite, or file repositories. It operates on memory-passed immutable objects.
- **NO REST API or WebSocket Endpoints:** Direct HTTP/WebSocket exposure belongs to the application API layer (`src/api/`).
- **NO Machine Learning / Neural Models:** Level 6.7 maintains complete scientific transparency and metrological auditability.

---

## 2. Gap Analysis

Inspection of the current repository reveals the exact architectural transition between the locked Level 6.6 state and the proposed Level 6.7 layer:

```
CURRENT ARCHITECTURE (Levels 0–6.6 Locked)
├── src/prognostics/
│   ├── types.py, horizon.py, prediction.py, provenance.py, state.py (Level 6.1)
│   ├── trajectory.py, trajectory_types.py, features.py (Level 6.2)
│   ├── estimators/ (Level 6.3 - HistoricalLinearRULEstimator)
│   ├── uncertainty/ (Level 6.4 - PrognosticUncertaintyEngine)
│   ├── evaluation/ (Level 6.5 - PrognosticEvaluationEngine, Single EOL)
│   └── decision/ (Level 6.6 - PrognosticDecisionEngine, Single Policy)
│
MISSING CAPABILITY (The Level 6.7 Gap)
├── No domain engine coordinates full pipeline from trajectory to recommendation in one call.
├── No contract exists to evaluate multi-mechanism EOL portfolios simultaneously.
├── No deterministic algorithm exists to resolve the limiting degradation failure mode.
├── No adapter transforms historical state repository records into degradation trajectories.
└── No unified top-level report container exists for fleet-level prognostic auditing.
│
PROPOSED LEVEL 6.7 BOUNDARY
└── src/prognostics/pipeline/
    ├── types.py (PipelineStatus, LimitingMechanismAssessment, PrognosticAssessmentReport)
    ├── config.py (PrognosticPipelineConfig, EOLPortfolio)
    ├── adapter.py (StateHistoryTrajectoryAdapter)
    ├── limiting.py (LimitingMechanismResolver)
    └── engine.py (PrognosticPipelineEngine)
```

### Why Existing Levels Cannot/Should Not Provide This:
1. **Level 6.5 (`src/prognostics/evaluation/`):** Strictly evaluates a single `EOLDefinition` and emits a single `PrognosticEvaluationResult`. Modifying it to handle multi-criterion portfolios or decision policies would violate single-responsibility principles and break locked contracts.
2. **Level 6.6 (`src/prognostics/decision/`):** Strictly interprets an already-evaluated `PrognosticEvaluationResult` against a `DecisionPolicy`. It cannot re-run lower-level estimators or manage multi-criterion portfolios without circular dependencies.
3. **Application Layer (`src/services/`):** If orchestration logic is placed in application services (`TwinApplicationService`), it becomes tightly coupled to service infrastructure and cannot be reused in pure offline benchmarking, CLI tools, or synthetic replay simulations.

**Conclusion:** Level 6.7 is the precise domain boundary for multi-criterion prognostic orchestration.

---

## 3. Architectural Role & Data Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                        DATA FLOW ARCHITECTURE                          │
└────────────────────────────────────────────────────────────────────────┘

 [Input 1: DegradationTrajectory]  OR  [Input 2: Sequence[TwinStateRecord]]
               │                                      │
               │                         (Via StateHistoryTrajectoryAdapter)
               │                                      │
               ▼                                      ▼
       [DegradationTrajectory (Validated Monotonic Time/Cycle Series)]
                                 │
                                 ▼
               ┌───────────────────────────────────┐
               │    PrognosticPipelineEngine       │
               └─────────────────┬─────────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │ 1. Extract Trajectory Features│ (Level 6.2 Feature Set)
                 └───────────────┬───────────────┘
                                 │
      ┌──────────────────────────┴──────────────────────────┐
      │ 2. Concurrent Multi-Criterion Evaluation Dispatch   │
      │                                                     │
      │   For each EOLDefinition in EOLPortfolio:           │
      │   ┌──────────────────────────────────────────────┐  │
      │   │ Level 6.3: RUL Point Estimation              │  │
      │   │ Level 6.4: Uncertainty & Evidence Audit      │  │
      │   │ Level 6.5: Single-Criterion Evaluation       │  │
      │   │ Level 6.6: Decision Policy Interpretation    │  │
      │   └──────────────────────┬───────────────────────┘  │
      └──────────────────────────┼──────────────────────────┘
                                 │
                                 ▼
      ┌─────────────────────────────────────────────────────┐
      │ Sequence[CriterionPrognosticEvaluation]             │
      │ (Map of Criterion ID → {Evaluation, Decision})      │
      └──────────────────────────┬──────────────────────────┘
                                 │
                                 ▼
      ┌─────────────────────────────────────────────────────┐
      │ 3. Limiting Mechanism Resolution                    │
      │    - Compares RUL values across identical domains   │
      │    - Resolves cross-domain precedence via policy    │
      │    - Identifies most restrictive failure mode       │
      │    - Synthesizes LimitingMechanismAssessment        │
      └──────────────────────────┬──────────────────────────┘
                                 │
                                 ▼
      ┌─────────────────────────────────────────────────────┐
      │ 4. Multi-Advisory Consolidation                     │
      │    - Primary recommendation from limiting mechanism │
      │    - Secondary advisories from non-limiting criteria│
      │    - Preserves all multi-dimensional limitations    │
      └──────────────────────────┬──────────────────────────┘
                                 │
                                 ▼
      ┌─────────────────────────────────────────────────────┐
      │ 5. Assemble Immutable PrognosticAssessmentReport    │
      └─────────────────────────────────────────────────────┘
```

---

## 4. Input Contracts

Level 6.7 strictly consumes existing, locked domain contracts without redefining them:

| Input Parameter | Source Contract | Layer | Mutability | Required / Optional | Semantic Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `trajectory` | `DegradationTrajectory` | Level 6.2 | Immutable | Required (or `state_records`) | Degradation time/cycle observation series |
| `state_records` | `Sequence[TwinStateRecord]` | Level 0/1 | Immutable | Optional | Historical state records to be adapted into trajectory |
| `portfolio` | `EOLPortfolio` (or `Sequence[EOLDefinition]`) | Level 6.1 / 6.7 | Immutable | Required | Set of competing EOL boundary criteria |
| `policy` | `DecisionPolicy` | Level 6.6 | Immutable | Required | Application-specific decision policy rulebook |
| `estimator_config`| `EstimatorConfig` | Level 6.3 | Immutable | Optional | Linear baseline estimator parameters |
| `uncertainty_config`| `UncertaintyEngineConfig` | Level 6.4 | Immutable | Optional | Coverage parameters and evidence weights |
| `pipeline_config` | `PrognosticPipelineConfig` | Level 6.7 | Immutable | Optional | Limiting resolution mode and extraction options |

---

## 5. Output Contracts

Level 6.7 produces a single top-level container: **`PrognosticAssessmentReport`**.

### Properties of the Output:
- **`report_id`**: Deterministic unique identifier linking to system and timestamp.
- **`system_id`**: Battery pack / cell identifier.
- **`timestamp_ns`**: Execution timestamp in nanoseconds.
- **`overall_status`**: Top-level lifecycle status (`VALID`, `VALID_WITH_LIMITATIONS`, `DEGRADED`, `BLOCKED`).
- **`limiting_mechanism`**: Structured [LimitingMechanismAssessment](#6-domain-contract-design) identifying the critical degradation channel.
- **`criteria_evaluations`**: Mapping of `criterion_id` to individual [CriterionPrognosticEvaluation](#6-domain-contract-design) records (preserving individual Level 6.5 and Level 6.6 outputs).
- **`feature_set`**: Level 6.2 `DegradationFeatureSet` extracted from the trajectory.
- **`primary_decision`**: Authoritative Level 6.6 `PrognosticDecisionResult` derived from the limiting mechanism.
- **`consolidated_secondary_advisories`**: Consolidated tuple of all `SecondaryAdvisory` records across all evaluated criteria.
- **`consolidated_validity_limitations`**: Complete list of validity warnings, uncertainty limits, and data quality notes.
- **`safety_authority`**: `"Physical BMS"` (Enforcing strict safety authority separation).
- **`is_safety_critical_actuation`**: `False` (Immutable non-actuation invariant).
- **`reproducibility_metadata`**: End-to-end provenance dictionary recording engine versions, execution timestamps, and criteria count.

---

## 6. Domain Contract Design

All proposed Level 6.7 domain contracts will be implemented as immutable `@dataclass(frozen=True)` and `str, Enum` types in `src/prognostics/pipeline/types.py` and `config.py`.

### 6.1 Enumerations (`types.py`)

```python
class PipelineStatus(str, Enum):
    """Execution status of the end-to-end prognostic assessment pipeline."""
    SUCCESS = "SUCCESS"                                 # All criteria evaluated successfully
    SUCCESS_WITH_LIMITATIONS = "SUCCESS_WITH_LIMITATIONS" # Evaluated with valid RULs but noted evidence/uncertainty limitations
    PARTIAL_EVALUATION = "PARTIAL_EVALUATION"           # Some criteria evaluated; others failed validity gating
    BLOCKED_BY_VALIDITY = "BLOCKED_BY_VALIDITY"         # All criteria blocked by fatal data quality or history failures
    INCOMPATIBLE_PORTFOLIO = "INCOMPATIBLE_PORTFOLIO"   # Portfolio criteria incompatible with trajectory quantities
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"     # Pipeline configuration failed validation


class LimitingResolutionStrategy(str, Enum):
    """Deterministic strategy for selecting the limiting degradation mechanism."""
    SHORTEST_RUL = "SHORTEST_RUL"                       # Primary: Selects the criterion with the lowest numeric RUL value
    HIGHEST_DECISION_PRIORITY = "HIGHEST_DECISION_PRIORITY" # Primary: Selects the criterion producing the most urgent DecisionClass/Priority
    NEAREST_EOL_DISTANCE = "NEAREST_EOL_DISTANCE"       # Primary: Selects the criterion with the smallest current normalized distance to EOL
```

### 6.2 Value Objects (`types.py` and `config.py`)

```python
@dataclass(frozen=True)
class CriterionPrognosticEvaluation:
    """Immutable evaluation bundle for a single EOL criterion within a portfolio."""
    criterion_id: str
    eol_definition: EOLDefinition
    evaluation_result: PrognosticEvaluationResult
    decision_result: PrognosticDecisionResult
    is_limiting: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "eol_definition": self.eol_definition.to_dict(),
            "evaluation_result": self.evaluation_result.to_dict(),
            "decision_result": self.decision_result.to_dict(),
            "is_limiting": self.is_limiting,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class LimitingMechanismAssessment:
    """Immutable assessment identifying the limiting degradation failure mode."""
    limiting_criterion_id: str
    limiting_criterion_type: EOLCriterionType
    limiting_rul_value: Optional[float]
    limiting_rul_unit: str
    limiting_rul_domain: HorizonDomain
    limiting_decision_class: DecisionClass
    limiting_priority: RecommendationPriority
    resolution_strategy: LimitingResolutionStrategy
    margin_to_secondary_rul: Optional[float] = None
    rationale: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "limiting_criterion_id": self.limiting_criterion_id,
            "limiting_criterion_type": self.limiting_criterion_type.value,
            "limiting_rul_value": round(float(self.limiting_rul_value), 6) if self.limiting_rul_value is not None else None,
            "limiting_rul_unit": self.limiting_rul_unit,
            "limiting_rul_domain": self.limiting_rul_domain.value,
            "limiting_decision_class": self.limiting_decision_class.value,
            "limiting_priority": self.limiting_priority.value,
            "resolution_strategy": self.resolution_strategy.value,
            "margin_to_secondary_rul": round(float(self.margin_to_secondary_rul), 6) if self.margin_to_secondary_rul is not None else None,
            "rationale": self.rationale,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class EOLPortfolio:
    """Immutable portfolio of multi-mechanism End-of-Life criteria."""
    portfolio_id: str
    name: str
    criteria: Sequence[EOLDefinition]
    description: Optional[str] = None
    version: str = "1.0.0"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.portfolio_id:
            raise ValueError("portfolio_id cannot be empty.")
        if not self.criteria:
            raise ValueError("EOLPortfolio must contain at least one EOLDefinition.")
        crit_ids = set()
        for c in self.criteria:
            if not isinstance(c, EOLDefinition):
                raise TypeError(f"Expected EOLDefinition, got {type(c).__name__}.")
            if c.criterion_id in crit_ids:
                raise ValueError(f"Duplicate criterion_id '{c.criterion_id}' in portfolio '{self.portfolio_id}'.")
            crit_ids.add(c.criterion_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "portfolio_id": self.portfolio_id,
            "name": self.name,
            "criteria": [c.to_dict() for c in self.criteria],
            "description": self.description,
            "version": self.version,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PrognosticPipelineConfig:
    """Configuration options governing end-to-end prognostic assessment pipeline."""
    resolution_strategy: LimitingResolutionStrategy = LimitingResolutionStrategy.SHORTEST_RUL
    extract_features: bool = True
    estimator_config: Optional[EstimatorConfig] = None
    uncertainty_config: Optional[UncertaintyEngineConfig] = None
    custom_parameters: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution_strategy": self.resolution_strategy.value,
            "extract_features": self.extract_features,
            "estimator_config": self.estimator_config.to_dict() if self.estimator_config else None,
            "uncertainty_config": self.uncertainty_config.to_dict() if self.uncertainty_config else None,
            "custom_parameters": dict(self.custom_parameters),
        }


@dataclass(frozen=True)
class PrognosticAssessmentReport:
    """Immutable top-level multi-mechanism prognostic assessment and lifecycle report."""
    report_id: str
    system_id: str
    report_timestamp_ns: int
    created_at_utc: str
    pipeline_status: PipelineStatus
    limiting_mechanism: Optional[LimitingMechanismAssessment]
    criteria_evaluations: Mapping[str, CriterionPrognosticEvaluation]
    primary_decision: PrognosticDecisionResult
    feature_set: Optional[DegradationFeatureSet] = None
    consolidated_secondary_advisories: Sequence[SecondaryAdvisory] = field(default_factory=tuple)
    consolidated_validity_limitations: Sequence[str] = field(default_factory=tuple)
    portfolio_id: str = ""
    policy_id: str = ""
    is_safety_critical_actuation: bool = False
    safety_authority: str = "Physical BMS"
    safety_disclaimer: str = (
        "ADVISORY ONLY: TwinVolt analytical decisions do not command physical actuators. "
        "The physical Battery Management System (BMS) remains the sole safety and protection authority."
    )
    reproducibility_metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        """Returns True if the limiting primary recommendation requires operational action."""
        return self.primary_decision.is_actionable

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "system_id": self.system_id,
            "report_timestamp_ns": self.report_timestamp_ns,
            "created_at_utc": self.created_at_utc,
            "pipeline_status": self.pipeline_status.value,
            "limiting_mechanism": self.limiting_mechanism.to_dict() if self.limiting_mechanism else None,
            "criteria_evaluations": {k: v.to_dict() for k, v in self.criteria_evaluations.items()},
            "primary_decision": self.primary_decision.to_dict(),
            "feature_set": self.feature_set.to_dict() if self.feature_set else None,
            "consolidated_secondary_advisories": [a.to_dict() for a in self.consolidated_secondary_advisories],
            "consolidated_validity_limitations": list(self.consolidated_validity_limitations),
            "portfolio_id": self.portfolio_id,
            "policy_id": self.policy_id,
            "is_actionable": self.is_actionable,
            "is_safety_critical_actuation": self.is_safety_critical_actuation,
            "safety_authority": self.safety_authority,
            "safety_disclaimer": self.safety_disclaimer,
            "reproducibility_metadata": dict(self.reproducibility_metadata),
        }
```

---

## 7. Decision & Pipeline Data Flow

The `PrognosticPipelineEngine.assess()` execution follows 10 pure, deterministic steps:

1. **Input Validation:** Verifies static types of `DegradationTrajectory` (or adapts `Sequence[TwinStateRecord]`), `EOLPortfolio`, `DecisionPolicy`, and `PrognosticPipelineConfig`.
2. **Trajectory Integrity Check:** Validates observation count, domain monotonicity, and physical non-negativity.
3. **Optional Feature Extraction:** Executes `TrajectoryFeatureExtractor.extract_features(trajectory)` (Level 6.2).
4. **Portfolio Dispatch:** Iterates through every `EOLDefinition` in `EOLPortfolio`:
   - Runs `PrognosticEvaluationEngine.evaluate()` (Level 6.5) producing `PrognosticEvaluationResult`.
   - Runs `PrognosticDecisionEngine.evaluate()` (Level 6.6) producing `PrognosticDecisionResult`.
   - Assembles `CriterionPrognosticEvaluation`.
5. **Limiting Mechanism Resolution:**
   - Filters criteria with valid RUL estimates.
   - If `resolution_strategy == SHORTEST_RUL`: selects criterion with $\min(\text{RUL})$. Calculates `margin_to_secondary_rul` ($\text{RUL}_2 - \text{RUL}_1$).
   - If `resolution_strategy == HIGHEST_DECISION_PRIORITY`: selects criterion with highest `RecommendationPriority` (e.g. `CRITICAL` over `HIGH`).
   - If an EOL criterion is `ALREADY_REACHED`, it immediately takes top limiting priority.
6. **Primary Decision Selection:** Designates the limiting criterion's `PrognosticDecisionResult` as the top-level `primary_decision`.
7. **Secondary Advisory Aggregation:** Collects all `secondary_advisories` from all criteria, plus adds synthetic cross-mechanism advisories for non-limiting criteria that have notable wear.
8. **Limitation Consolidation:** Deduplicates and aggregates all `validity_limitations` across all criteria evaluations.
9. **Provenance & Metadata Assembly:** Injects trajectory span, criteria count, limiting mechanism ID, engine versions, and timestamps.
10. **Report Construction:** Emits immutable `PrognosticAssessmentReport`.

---

## 8. Failure & Edge-Case Matrix

| Failure Mode | Pipeline Behavior | Pipeline Status | Limiting Mechanism | Actionability |
| :--- | :--- | :--- | :--- | :--- |
| **Empty Trajectory** | Rejects at input validation | `BLOCKED_BY_VALIDITY` | `None` | `INVESTIGATION_REQUIRED` |
| **Empty EOL Portfolio** | Rejects at config validation | `INVALID_CONFIGURATION` | `None` | `NON_ACTIONABLE` |
| **Incompatible Quantity in Portfolio** | Individual criterion returns `INVALID_EOL_CRITERION`; others proceed | `PARTIAL_EVALUATION` | Selected from valid criteria | Per valid limiting criterion |
| **All Criteria Invalid / Blocked** | Returns blocked report with aggregated validity errors | `BLOCKED_BY_VALIDITY` | `None` | `INVESTIGATION_REQUIRED` |
| **Single Criterion Portfolio** | Evaluates criterion; trivially selected as limiting mechanism | `SUCCESS` | Single criterion | Per policy rule |
| **Tied Shortest RUL** | Deterministic tie-breaking by `criterion_id` alphabetical sort | `SUCCESS` | First tied criterion | Per policy rule |
| **Different RUL Domains in Portfolio** (e.g. Cycles vs Hours) | Normalized comparison or policy-ordered priority resolution | `SUCCESS` | Resolved by strategy | Per limiting domain |
| **Degradation Rate $\le 0$ (No EOL Crossing)** | RUL is None; EOL not reached; nominal monitoring applied | `SUCCESS` | Selected by lowest wear margin | `ADVISORY_ONLY` |

---

## 9. Universality & Chemistry Independence

Level 6.7 strictly upholds TwinVolt's universal core principles:
1. **No Chemistry Constants:** Contains zero references to Li-ion, LFP, NMC, NCA, Sodium-ion, or Lead-acid chemistry.
2. **No Hardcoded Capacities or Voltages:** Usable capacity, cell counts, and voltage envelopes are purely parameterized via the supplied `EOLDefinition` and `DegradationTrajectory`.
3. **Domain Agnostic:** Works interchangeably across `HorizonDomain.CYCLE`, `TIME`, `AMPERE_HOUR_THROUGHPUT`, and `WATT_HOUR_THROUGHPUT`.
4. **Hardware Agnostic:** Telemetry origin (real test bench, synthetic simulation, or historical replay) has zero impact on mathematical execution.

---

## 10. Safety Authority Separation

```
┌────────────────────────────────────────────────────────┐
│                   PHYSICAL BMS                         │
│           (Sole Safety & Actuation Authority)          │
│  - Contactor Tripping       - Over-Voltage Protection  │
│  - Short-Circuit Cutoff     - Thermal Runaway Defense  │
└───────────────────────────▲────────────────────────────┘
                            │ (Analytical Telemetry Only)
┌───────────────────────────┴────────────────────────────┐
│                    TWINVOLT                            │
│           (Analytical Digital Twin Platform)           │
│  Level 6.7: Prognostic Pipeline & Portfolio Engine     │
│  - is_safety_critical_actuation = False                │
│  - Analytical Advisory & Fleet Triage Support          │
│  - Multi-Criterion Lifecycle Assessment                │
└────────────────────────────────────────────────────────┘
```

- Every `PrognosticAssessmentReport` contains an immutable `safety_disclaimer` and `is_safety_critical_actuation = False`.
- Level 6.7 contains zero actuation drivers, CAN messages, GPIO triggers, or power cutoff pathways.

---

## 11. Runtime / Application / API Integration Strategy

### Architectural Decision: Keep Level 6.7 a Pure Domain Layer
- `src/prognostics/pipeline/` will be implemented as a **pure scientific domain package** with zero dependencies on FastAPI, WebSockets, or runtime databases.
- This ensures Level 6.7 can be executed in:
  1. Offline batch processing and validation benchmarks (`src/benchmarking/`).
  2. Historical replay pipelines (`src/replay/`).
  3. Real-time Digital Twin instances (`src/runtime/instance.py`).
  4. Application services (`src/services/twin_service.py`).
  5. CLI utilities and edge diagnostic containers.

Future integration of Level 6.7 into `TwinApplicationService` (e.g. `twin_service.assess_prognostics(system_id)`) or REST routes (`/api/v1/twins/{id}/prognostics`) will occur cleanly at the application tier in Level 7.

---

## 12. Proposed File & Package Plan

```
src/prognostics/pipeline/
├── __init__.py             # Public exports for Level 6.7
├── types.py                # PipelineStatus, LimitingMechanismAssessment, PrognosticAssessmentReport
├── config.py               # EOLPortfolio, PrognosticPipelineConfig, LimitingResolutionStrategy
├── adapter.py              # StateHistoryTrajectoryAdapter (TwinStateRecord -> DegradationTrajectory)
├── limiting.py             # LimitingMechanismResolver (deterministic multi-criterion selection)
└── engine.py               # PrognosticPipelineEngine (stateless top-level orchestrator)

tests/unit/prognostics/pipeline/
├── __init__.py             # Test package initialization
├── test_types.py           # Value object immutability, validation, and serialization
├── test_config.py          # EOLPortfolio and PipelineConfig validation and duplicate rejection
├── test_adapter.py         # StateHistoryTrajectoryAdapter validation and provenance mapping
├── test_limiting.py        # LimitingMechanismResolver (shortest RUL, priority, tie-breaking)
├── test_engine.py          # End-to-end pipeline execution across single and multi-criterion portfolios
└── test_semantics_and_safety.py # Safety authority separation, zero-actuation, universality, isolation
```

---

## 13. Dependency Rules

### Allowed Imports:
- Standard library (`dataclasses`, `enum`, `math`, `typing`, `datetime`, `uuid`).
- `src.domain.battery.*` (Domain entities and value objects).
- `src.storage.base` (`TwinStateRecord` for the adapter).
- `src.prognostics.types` (Level 6.1 enums).
- `src.prognostics.prediction` (Level 6.1 prediction types).
- `src.prognostics.trajectory` & `src.prognostics.trajectory_types` (Level 6.2).
- `src.prognostics.features` (Level 6.2).
- `src.prognostics.estimators.*` (Level 6.3).
- `src.prognostics.uncertainty.*` (Level 6.4).
- `src.prognostics.evaluation.*` (Level 6.5).
- `src.prognostics.decision.*` (Level 6.6).

### Forbidden Imports:
- `src.runtime.*` (No runtime instance dependencies).
- `src.api.*` / `fastapi` / `uvicorn` / `starlette` (No web frameworks).
- `src.ui.*` (No UI widgets).
- `src.gateway.*` / `serial` / `can` (No hardware protocols).
- `torch` / `sklearn` / `tensorflow` (No ML frameworks).

---

## 14. Comprehensive Test Strategy

The Level 6.7 test suite will contain **35+ targeted unit tests**:

1. **Contract Tests (`test_types.py`):**
   - Immutability of `CriterionPrognosticEvaluation`, `LimitingMechanismAssessment`, `PrognosticAssessmentReport`.
   - Rejection of invalid field types, negative timestamps, empty IDs.
   - Pure JSON serialization round-trip.
2. **Portfolio & Config Tests (`test_config.py`):**
   - Rejection of duplicate `criterion_id` in `EOLPortfolio`.
   - Rejection of empty portfolio.
   - Serialization and deserialization of `EOLPortfolio` and `PrognosticPipelineConfig`.
3. **State History Adapter Tests (`test_adapter.py`):**
   - Valid conversion of `TwinStateRecord` sequence to `DegradationTrajectory`.
   - Monotonic domain sorting and duplicate timestamp handling.
   - Missing channel filtering and provenance tagging.
4. **Limiting Mechanism Resolver Tests (`test_limiting.py`):**
   - Shortest RUL resolution ($RUL_1 = 30 < RUL_2 = 80 \implies \text{Criterion 1 limiting}$).
   - EOL Already Reached override (takes immediate precedence).
   - Tied RUL deterministic tie-breaking.
   - Margin to secondary RUL calculation.
5. **Pipeline Engine Tests (`test_engine.py`):**
   - Single-criterion pipeline run matching Level 6.5/6.6 output.
   - Multi-criterion portfolio run with concurrent Capacity + Resistance evaluation.
   - Deterministic identical output on identical inputs.
   - Partial evaluation handling when one criterion fails data quality.
6. **Semantics, Safety & Isolation Tests (`test_semantics_and_safety.py`):**
   - Permanent `is_safety_critical_actuation == False`.
   - Presence of immutable safety disclaimer.
   - Verification of zero imports from `runtime`, `api`, `ui`, `gateway`.
   - Input trajectory and policy immutability verification.

---

## 15. Scientific Validity & Non-Fabrication Guarantees

- **No Synthetic Accuracy Claims:** Level 6.7 explicitly preserves the metrological truth that RUL projections are extrapolated statistical estimations under explicit assumptions, not guaranteed physical crystal balls.
- **Limiting Margin Metric:** The `margin_to_secondary_rul` metric provides transparent insight into whether failure modes are clustered (e.g. capacity and resistance expiring simultaneously) or decoupled.
- **Preservation of Level 6.4/6.5 Evidence Audits:** Multi-criterion aggregation never masks a weak evidence rating in one channel behind a strong rating in another. Each channel's evidence assessment remains independently auditable.

---

## 16. Resource & Edge Considerations (Raspberry Pi 4)

- **Computational Complexity:** $O(M \cdot N)$ where $M$ is the number of criteria in the portfolio (typically $1 \le M \le 5$) and $N$ is the number of trajectory observations (typically $N < 500$). On a 1.5 GHz ARM Cortex-A72 (Raspberry Pi 4), a full 5-criterion pipeline evaluation executes in $< 10\text{ ms}$.
- **Memory Footprint:** Fully bounded; memory allocations are ephemeral and garbage-collected immediately. No unbounded caching or memory leaks.
- **Deterministic Float Operations:** Pure IEEE-754 arithmetic ensures consistency between edge execution (ARM64) and cloud/desktop verification (x86_64).

---

## 17. Replay & Benchmark Compatibility

- Because `PrognosticPipelineEngine` is completely pure and stateless, it can be executed inside batch replay loops (`src/replay/`) and validation benchmarking suites (`src/benchmarking/`) over thousands of historical battery cycles without side-effects or state accumulation.

---

## 18. Security & Trust Boundary

- **Untrusted Telemetry Protection:** Input trajectory observations are sanitized and validated against NaN, Inf, and negative timestamps at the adapter boundary.
- **Config Injection Safety:** All config parameters (thresholds, weights, strategies) are strongly typed and validated upon construction, preventing injection anomalies.

---

## 19. Implementation Phases

When approved for implementation, Level 6.7 will be executed in 6 sequential phases:

```
Phase 1: Create types.py and config.py (Domain Enums, EOLPortfolio, LimitingMechanismAssessment, PrognosticAssessmentReport)
   ↓
Phase 2: Create adapter.py (StateHistoryTrajectoryAdapter)
   ↓
Phase 3: Create limiting.py (LimitingMechanismResolver)
   ↓
Phase 4: Create engine.py (PrognosticPipelineEngine)
   ↓
Phase 5: Create __init__.py exports and update src/prognostics/__init__.py
   ↓
Phase 6: Create comprehensive unit test suite in tests/unit/prognostics/pipeline/ and verify zero regressions across full repository (814+ tests)
```

---

## 20. Acceptance Criteria

Level 6.7 will be considered **COMPLETE AND LOCKED** when:
1. `src/prognostics/pipeline/` is fully implemented with all domain contracts, adapter, resolver, and engine.
2. All 35+ targeted Level 6.7 unit tests pass.
3. Full prognostics test suite passes (>220 tests).
4. Full repository test suite passes with **0 failures and 0 regressions** (>845 tests).
5. All domain contracts are immutable (`frozen=True`) and implement `.to_dict()`.
6. Strict architectural isolation is proven (no runtime, API, UI, or gateway imports).
7. Safety authority separation is confirmed (`is_safety_critical_actuation == False`).

---

## 21. Open Questions for Review

1. **Portfolio Criterion Weights:** Should `LimitingResolutionStrategy` support an optional policy-defined weighted composite score, or should it strictly remain categorical (e.g., Shortest RUL vs Highest Priority)? *(Recommendation: Keep strictly categorical for Level 6.7 to preserve transparent explainability without synthetic weight tuning).*
2. **Adapter Channel Mapping:** Should `StateHistoryTrajectoryAdapter` support custom field extractors for application-specific quantities, or use standard named getters on `TwinStateRecord`? *(Recommendation: Support standard named properties with fallback to `state_record.metadata` dictionary).*

---
*END OF SPECIFICATION — DESIGN-ONLY / NO IMPLEMENTATION PERFORMED*
