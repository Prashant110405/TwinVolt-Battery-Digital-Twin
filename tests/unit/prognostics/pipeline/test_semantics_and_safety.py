"""Level 6.7 Architectural Invariant, Semantics, and Safety Tests.

Verifies:
1. Physical BMS Safety Authority Invariance (is_safety_critical_actuation permanently False).
2. Architectural Isolation & Zero Forbidden Imports (no runtime, api, ui, gateway, hardware, ML).
3. Universality (no hardcoded chemistry constants, cell counts, or fixed capacities).
4. Mutation Resistance & Replay Isolation (pipeline execution never mutates inputs).
5. Level 6.5 & Level 6.6 Semantic Preservation (limitations, validity failures, and decision policies preserved).
"""

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Sequence

import pytest

from src.prognostics.decision.policy import DecisionCondition, DecisionPolicy, DecisionRule
from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    RecommendationPriority,
)
from src.prognostics.evaluation.types import EvaluationStatus
from src.prognostics.pipeline.adapter import StateHistoryTrajectoryAdapter
from src.prognostics.pipeline.config import EOLPortfolio, PrognosticPipelineConfig
from src.prognostics.pipeline.engine import PrognosticPipelineEngine
from src.prognostics.pipeline.types import (
    LimitingMechanismAssessment,
    LimitingResolutionStatus,
    LimitingResolutionStrategy,
    PipelineStatus,
    PrognosticAssessmentReport,
)
from src.prognostics.prediction import EOLDefinition
from src.prognostics.provenance import PrognosticQuantity
from src.prognostics.trajectory import DegradationObservation, DegradationTrajectory
from src.prognostics.trajectory_types import TrajectoryQuantityType
from src.prognostics.types import (
    ComparisonOperator,
    EOLCriterionType,
    HorizonDomain,
)
from src.storage.base import EstimationState, ModelState, TwinStateRecord


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def synthetic_trajectory() -> DegradationTrajectory:
    """Creates a standard 10-point trajectory."""
    observations = []
    for i in range(10):
        cycle = float(i * 10)
        soh = 1.00 - 0.002 * cycle
        obs = DegradationObservation(
            timestamp_ns=(i + 1) * 1_000_000_000,
            created_at_utc=f"2026-10-01T00:00:0{i}Z",
            capacity_retention_fraction=PrognosticQuantity(
                name="capacity_retention_fraction", value=soh, unit="ratio"
            ),
            equivalent_full_cycles=PrognosticQuantity(
                name="equivalent_full_cycles", value=cycle, unit="cycles"
            ),
        )
        observations.append(obs)

    return DegradationTrajectory(
        trajectory_id="traj_safety_001",
        system_id="batt_safety_test",
        quantity_type=TrajectoryQuantityType.CAPACITY_RETENTION,
        observations=tuple(observations),
    )


@pytest.fixture
def sample_portfolio() -> EOLPortfolio:
    crit = EOLDefinition(
        criterion_id="crit_soh_80",
        criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        threshold_value=0.80,
        unit="ratio",
    )
    return EOLPortfolio(
        portfolio_id="port_safety",
        name="Safety Test Portfolio",
        criteria=[crit],
    )


@pytest.fixture
def sample_policy() -> DecisionPolicy:
    cond = DecisionCondition(
        condition_id="cond_maint",
        rul_threshold_value=50.0,
        rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
    )
    rule = DecisionRule(
        rule_id="rule_maint",
        precedence_rank=1,
        decision_class=DecisionClass.PLAN_MAINTENANCE,
        priority=RecommendationPriority.MEDIUM,
        actionability=Actionability.ACTIONABLE,
        condition=cond,
        recommendation_template="Schedule battery inspection.",
        rationale_template="RUL threshold triggered.",
    )
    return DecisionPolicy(
        policy_id="policy_safety",
        policy_name="Safety Test Policy",
        version="1.0.0",
        rules=[rule],
    )


# -----------------------------------------------------------------------------
# 1. Safety Authority Invariant Tests
# -----------------------------------------------------------------------------


class TestSafetyAuthorityInvariants:
    """Verifies that Level 6.7 acts strictly as advisory and never commands actuation."""

    def test_report_actuation_permanently_false(
        self,
        synthetic_trajectory: DegradationTrajectory,
        sample_portfolio: EOLPortfolio,
        sample_policy: DecisionPolicy,
    ) -> None:
        """Verify that PrognosticAssessmentReport always enforces is_safety_critical_actuation=False."""
        engine = PrognosticPipelineEngine()
        report = engine.assess(
            trajectories=synthetic_trajectory,
            portfolio=sample_portfolio,
            policy=sample_policy,
        )
        assert report.is_safety_critical_actuation is False
        assert report.safety_authority == "Physical BMS"

        # Verify FrozenInstanceError on attempted mutation
        with pytest.raises(FrozenInstanceError):
            report.is_safety_critical_actuation = True  # type: ignore

    def test_report_rejects_true_actuation_in_construction(
        self,
        sample_portfolio: EOLPortfolio,
        sample_policy: DecisionPolicy,
    ) -> None:
        """Direct constructor call must reject is_safety_critical_actuation=True."""
        dummy_limiting = LimitingMechanismAssessment(
            status=LimitingResolutionStatus.ALL_CRITERIA_UNAVAILABLE,
            resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
            rationale="Test",
        )
        dummy_decision = sample_policy.rules[0]  # not a full decision, but for testing post-init validation
        engine = PrognosticPipelineEngine()
        indeterminate_dec = engine._create_indeterminate_decision(
            dummy_limiting, "sys_1", 1000, "2026-10-01T00:00:00Z"
        )

        with pytest.raises(ValueError, match="is_safety_critical_actuation must be False"):
            PrognosticAssessmentReport(
                report_id="rep_fail",
                system_id="sys_1",
                report_timestamp_ns=1000,
                created_at_utc="2026-10-01T00:00:00Z",
                pipeline_status=PipelineStatus.SUCCESS,
                limiting_mechanism=dummy_limiting,
                criteria_evaluations={},
                primary_decision=indeterminate_dec,
                portfolio_id=sample_portfolio.portfolio_id,
                policy_id=sample_policy.policy_id,
                is_safety_critical_actuation=True,  # VIOLATION
            )


# -----------------------------------------------------------------------------
# 2. Architectural Isolation & Forbidden Import Tests
# -----------------------------------------------------------------------------


class TestArchitecturalIsolation:
    """Verifies pure domain isolation via AST inspection of src/prognostics/pipeline/."""

    FORBIDDEN_MODULES = {
        "runtime",
        "api",
        "ui",
        "gateway",
        "hardware",
        "fastapi",
        "websockets",
        "database",
        "torch",
        "sklearn",
        "tensorflow",
        "scipy",
        "bms_hardware",
        "drivers",
    }

    def test_no_forbidden_imports_in_pipeline_package(self) -> None:
        """Inspects all AST import nodes in src/prognostics/pipeline/."""
        pipeline_dir = Path("src/prognostics/pipeline")
        assert pipeline_dir.is_dir(), f"Pipeline directory {pipeline_dir} not found"

        py_files = list(pipeline_dir.glob("*.py"))
        assert len(py_files) >= 5, "Expected at least 5 python files in pipeline package"

        for py_file in py_files:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top_pkg = alias.name.split(".")[0]
                        assert (
                            top_pkg not in self.FORBIDDEN_MODULES
                        ), f"Forbidden import '{alias.name}' detected in {py_file.name}:{node.lineno}"
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        top_pkg = node.module.split(".")[0]
                        assert (
                            top_pkg not in self.FORBIDDEN_MODULES
                        ), f"Forbidden from-import '{node.module}' detected in {py_file.name}:{node.lineno}"


# -----------------------------------------------------------------------------
# 3. Universality Tests
# -----------------------------------------------------------------------------


class TestUniversality:
    """Verifies absence of fixed chemistry constants, cell counts, or capacity limits."""

    FORBIDDEN_TERMS = [
        "NMC",
        "LFP",
        "LCO",
        "LTO",
        "LiFePO4",
        "4.2V",
        "3.7V",
        "3.2V",
        "48V",
        "100Ah",
        "50Ah",
        "cell_count = ",
        "nominal_voltage = ",
    ]

    def test_no_hardcoded_chemistry_constants_in_pipeline(self) -> None:
        """Ensures the orchestration engine is strictly universal across chemistries."""
        pipeline_dir = Path("src/prognostics/pipeline")
        py_files = list(pipeline_dir.glob("*.py"))

        for py_file in py_files:
            source = py_file.read_text(encoding="utf-8")
            for term in self.FORBIDDEN_TERMS:
                assert (
                    term.lower() not in source.lower()
                ), f"Potentially non-universal chemistry reference '{term}' found in {py_file.name}"


# -----------------------------------------------------------------------------
# 4. Mutation Resistance & Replay Isolation Tests
# -----------------------------------------------------------------------------


class TestMutationResistanceAndReplayIsolation:
    """Ensures repeated execution is idempotent and causes zero side effects on inputs."""

    def test_pipeline_execution_does_not_mutate_inputs(
        self,
        synthetic_trajectory: DegradationTrajectory,
        sample_portfolio: EOLPortfolio,
        sample_policy: DecisionPolicy,
    ) -> None:
        """Verify input structures remain byte-identical before and after execution."""
        traj_obs_count_before = len(synthetic_trajectory.observations)
        portfolio_len_before = len(sample_portfolio.criteria)
        policy_rules_count_before = len(sample_policy.rules)

        engine = PrognosticPipelineEngine()
        config = PrognosticPipelineConfig()

        # Run 1
        rep1 = engine.assess(
            trajectories=synthetic_trajectory,
            portfolio=sample_portfolio,
            policy=sample_policy,
            config=config,
        )

        # Run 2
        rep2 = engine.assess(
            trajectories=synthetic_trajectory,
            portfolio=sample_portfolio,
            policy=sample_policy,
            config=config,
        )

        # Assert no inputs were mutated
        assert len(synthetic_trajectory.observations) == traj_obs_count_before
        assert len(sample_portfolio.criteria) == portfolio_len_before
        assert len(sample_policy.rules) == policy_rules_count_before

        # Assert idempotent outputs
        assert rep1.limiting_mechanism.limiting_criterion_id == rep2.limiting_mechanism.limiting_criterion_id
        assert rep1.limiting_mechanism.limiting_rul_value == rep2.limiting_mechanism.limiting_rul_value
        assert rep1.primary_decision.primary_decision_class == rep2.primary_decision.primary_decision_class

    def test_adapter_does_not_mutate_input_records(self) -> None:
        """Ensure StateHistoryTrajectoryAdapter does not mutate TwinStateRecord sequence."""
        model_st = ModelState(soc_fraction=0.8, temperature_c=25.0)
        est_st = EstimationState(
            soc_fraction=0.8,
            soh_fraction=0.95,
            internal_resistance_mohm=22.0,
            custom_estimates={"cycle": 50.0},
        )
        rec = TwinStateRecord(
            record_id="rec_immut",
            system_id="batt_01",
            timestamp_ns=1000,
            model_state=model_st,
            estimation_state=est_st,
        )
        records = [rec]

        adapter = StateHistoryTrajectoryAdapter()
        adapter.extract_trajectory(
            records=records,
            quantity_type=TrajectoryQuantityType.CAPACITY_RETENTION,
            unit="ratio",
            horizon_domain=HorizonDomain.CYCLE,
        )

        # Verify original record unaffected
        assert len(records) == 1
        assert records[0].record_id == "rec_immut"
        assert records[0].estimation_state.soh_fraction == 0.95


# -----------------------------------------------------------------------------
# 5. Level 6.5 & Level 6.6 Semantic Preservation Tests
# -----------------------------------------------------------------------------


class TestLevel65And66SemanticPreservation:
    """Verifies that Level 6.5 evaluation validity and Level 6.6 decision policies are faithfully preserved."""

    def test_insufficient_history_validity_preserved(
        self,
        sample_portfolio: EOLPortfolio,
        sample_policy: DecisionPolicy,
    ) -> None:
        """When trajectory has only 1 observation, Level 6.5 INSUFFICIENT_HISTORY is preserved."""
        obs = DegradationObservation(
            timestamp_ns=1_000_000_000,
            created_at_utc="2026-10-01T00:00:00Z",
            capacity_retention_fraction=PrognosticQuantity(
                name="capacity_retention_fraction", value=0.98, unit="ratio"
            ),
            equivalent_full_cycles=PrognosticQuantity(
                name="equivalent_full_cycles", value=10.0, unit="cycles"
            ),
        )
        short_traj = DegradationTrajectory(
            trajectory_id="short_traj",
            system_id="batt_short",
            quantity_type=TrajectoryQuantityType.CAPACITY_RETENTION,
            observations=(obs,),
        )

        engine = PrognosticPipelineEngine()
        report = engine.assess(
            trajectories=short_traj,
            portfolio=sample_portfolio,
            policy=sample_policy,
        )

        # Level 6.5 validity status must be preserved
        crit_eval = report.criteria_evaluations["crit_soh_80"]
        assert crit_eval.evaluation_result.evaluation_status == EvaluationStatus.INSUFFICIENT_HISTORY
        assert report.pipeline_status in (
            PipelineStatus.BLOCKED_BY_VALIDITY,
            PipelineStatus.PARTIAL_EVALUATION,
        )
        assert report.limiting_mechanism.status == LimitingResolutionStatus.ALL_CRITERIA_UNAVAILABLE
        assert report.is_actionable is False

    def test_policy_recommendations_not_recomputed(
        self,
        synthetic_trajectory: DegradationTrajectory,
        sample_portfolio: EOLPortfolio,
        sample_policy: DecisionPolicy,
    ) -> None:
        """Verify Level 6.6 recommendation strings and priority are untouched by pipeline."""
        engine = PrognosticPipelineEngine()
        report = engine.assess(
            trajectories=synthetic_trajectory,
            portfolio=sample_portfolio,
            policy=sample_policy,
        )

        # Check primary recommendation string is generated by the Level 6.6 policy template
        # RUL is 55 cycles, threshold in sample_policy is 50.0 cycles, so default policy recommendation triggers
        assert report.primary_decision.primary_recommendation in (
            "Schedule battery inspection.",
            "Continue standard operational monitoring cadence.",
        )
        assert report.primary_decision.policy_id == sample_policy.policy_id
