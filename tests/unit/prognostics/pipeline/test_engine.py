"""Unit Tests for Level 6.7 PrognosticPipelineEngine.

Validates:
- End-to-end multi-criterion prognostic portfolio execution
- Single criterion vs multi-criteria execution
- Concurrent failure mode dispatch (capacity fade, resistance growth)
- Deterministic limiting mechanism resolution across strategies
- Cross-domain comparison protection (CYCLE vs TIME)
- Margin tracking between limiting and secondary failure modes
- Partial portfolio evaluation and criterion failure isolation
- Preservation of Level 6.5 validity gating and Level 6.6 decision policies
- State history adaptation via assess_from_state_history
- Deterministic repeated execution without mutation
"""

import pytest

from src.estimators.base import EstimationState
from src.models.types import ModelState
from src.prognostics.decision.policy import DecisionCondition, DecisionPolicy, DecisionRule
from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    RecommendationPriority,
)
from src.prognostics.evaluation.types import EvaluationStatus
from src.prognostics.pipeline.config import EOLPortfolio, PrognosticPipelineConfig
from src.prognostics.pipeline.engine import PrognosticPipelineEngine
from src.prognostics.pipeline.types import (
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
from src.storage.base import TwinStateRecord


@pytest.fixture
def dual_degradation_trajectory() -> DegradationTrajectory:
    """Creates a trajectory where capacity drops linearly and resistance rises linearly."""
    # 10 observations: cycle 0 to 45
    # Capacity starts at 1.00 (ratio), drops by 0.002 per cycle -> at cycle 45: 0.910
    # Threshold 0.80 -> delta = 0.110 -> RUL = 55 cycles
    # Resistance starts at 1.00 (ratio), rises by 0.01 per cycle -> at cycle 45: 1.450
    # Threshold 2.00 -> delta = 0.550 -> RUL = 55 cycles
    observations = []
    for i in range(10):
        cycle = float(i * 5)
        soh = 1.00 - 0.002 * cycle
        r_ratio = 1.00 + 0.01 * cycle
        r_ohm = 0.020 * r_ratio

        obs = DegradationObservation(
            timestamp_ns=(i + 1) * 1_000_000_000,
            created_at_utc=f"2026-10-01T00:00:0{i}Z",
            capacity_retention_fraction=PrognosticQuantity(
                name="capacity_retention_fraction", value=soh, unit="ratio"
            ),
            resistance_growth_ratio=PrognosticQuantity(
                name="resistance_growth_ratio", value=r_ratio, unit="ratio"
            ),
            internal_resistance_r0_ohm=PrognosticQuantity(
                name="internal_resistance_r0_ohm", value=r_ohm, unit="ohm"
            ),
            equivalent_full_cycles=PrognosticQuantity(
                name="equivalent_full_cycles", value=cycle, unit="cycles"
            ),
        )
        observations.append(obs)

    return DegradationTrajectory(
        trajectory_id="traj_dual_001",
        system_id="batt_cell_X1",
        quantity_type=TrajectoryQuantityType.MULTIVARIATE,
        observations=tuple(observations),
    )


@pytest.fixture
def standard_policy() -> DecisionPolicy:
    """Decision policy that triggers maintenance when RUL <= 60 cycles."""
    cond_urgent = DecisionCondition(
        condition_id="cond_urgent_maint",
        rul_threshold_value=60.0,
        rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
    )
    rule_urgent = DecisionRule(
        rule_id="rule_urgent_maint",
        precedence_rank=1,
        decision_class=DecisionClass.PLAN_MAINTENANCE,
        priority=RecommendationPriority.HIGH,
        actionability=Actionability.ACTIONABLE,
        condition=cond_urgent,
        recommendation_template="Plan pack maintenance within the next operational window.",
        rationale_template="Remaining Useful Life is within the critical threshold.",
    )
    return DecisionPolicy(
        policy_id="policy_standard_ev",
        policy_name="Standard EV Maintenance Policy",
        version="1.0.0",
        rules=[rule_urgent],
    )


class TestPrognosticPipelineEngine:
    """Test suite for PrognosticPipelineEngine orchestration."""

    def test_single_criterion_pipeline_execution(
        self,
        dual_degradation_trajectory: DegradationTrajectory,
        standard_policy: DecisionPolicy,
    ) -> None:
        crit_soh = EOLDefinition(
            criterion_id="crit_soh_80",
            criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
            threshold_value=0.80,
            unit="ratio",
        )
        portfolio = EOLPortfolio(
            portfolio_id="port_single",
            name="Single Capacity Portfolio",
            criteria=[crit_soh],
        )

        engine = PrognosticPipelineEngine()
        report = engine.assess(
            trajectories=dual_degradation_trajectory,
            portfolio=portfolio,
            policy=standard_policy,
        )

        assert isinstance(report, PrognosticAssessmentReport)
        assert report.pipeline_status in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_LIMITATIONS)
        assert report.limiting_mechanism.status == LimitingResolutionStatus.RESOLVED
        assert report.limiting_mechanism.limiting_criterion_id == "crit_soh_80"
        assert pytest.approx(report.limiting_mechanism.limiting_rul_value, abs=1e-2) == 55.0
        assert report.limiting_mechanism.margin_to_secondary_rul is None

        # Verify primary decision
        assert report.primary_decision.primary_decision_class == DecisionClass.PLAN_MAINTENANCE
        assert report.primary_decision.primary_priority == RecommendationPriority.HIGH
        assert report.is_actionable is True
        assert report.is_safety_critical_actuation is False

    def test_multi_criteria_limiting_mechanism_resolution(
        self,
        dual_degradation_trajectory: DegradationTrajectory,
        standard_policy: DecisionPolicy,
    ) -> None:
        # Criterion 1: SOH drops to 0.80 -> RUL is 55 cycles
        crit_soh = EOLDefinition(
            criterion_id="crit_soh_80",
            criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
            threshold_value=0.80,
            unit="ratio",
        )
        # Criterion 2: Resistance ratio rises to 2.50 (slower failure)
        # At cycle 45, ratio is 1.45, rate is 0.01/cycle -> RUL = (2.50 - 1.45)/0.01 = 105 cycles
        crit_res = EOLDefinition(
            criterion_id="crit_res_250",
            criterion_type=EOLCriterionType.RESISTANCE_GROWTH_RATIO_THRESHOLD,
            threshold_value=2.50,
            unit="ratio",
        )
        portfolio = EOLPortfolio(
            portfolio_id="port_dual",
            name="Dual Mechanism Portfolio",
            criteria=[crit_soh, crit_res],
        )

        engine = PrognosticPipelineEngine()
        config = PrognosticPipelineConfig(
            resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL
        )
        report = engine.assess(
            trajectories=dual_degradation_trajectory,
            portfolio=portfolio,
            policy=standard_policy,
            config=config,
        )

        assert report.pipeline_status in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_LIMITATIONS)
        assert report.limiting_mechanism.status == LimitingResolutionStatus.RESOLVED
        assert report.limiting_mechanism.limiting_criterion_id == "crit_soh_80"
        assert pytest.approx(report.limiting_mechanism.limiting_rul_value, abs=1e-2) == 55.0
        assert report.limiting_mechanism.secondary_criterion_id == "crit_res_250"
        # Margin: 105 - 55 = 50 cycles
        assert pytest.approx(report.limiting_mechanism.margin_to_secondary_rul, abs=1e-2) == 50.0

        # Criteria evaluations both preserved
        assert "crit_soh_80" in report.criteria_evaluations
        assert "crit_res_250" in report.criteria_evaluations
        assert report.criteria_evaluations["crit_soh_80"].is_limiting is True
        assert report.criteria_evaluations["crit_res_250"].is_limiting is False

    def test_incompatible_domains_cross_domain_protection(
        self,
        dual_degradation_trajectory: DegradationTrajectory,
        standard_policy: DecisionPolicy,
    ) -> None:
        # Create a second trajectory with TIME domain
        time_observations = []
        for i in range(10):
            elapsed_days = float(i * 10)
            soh = 1.00 - 0.001 * elapsed_days
            obs = DegradationObservation(
                timestamp_ns=(i + 1) * 1_000_000_000,
                created_at_utc=f"2026-10-01T00:00:0{i}Z",
                capacity_retention_fraction=PrognosticQuantity(
                    name="capacity_retention_fraction", value=soh, unit="ratio"
                ),
                calendar_age_seconds=PrognosticQuantity(
                    name="calendar_age_seconds", value=elapsed_days * 86400.0, unit="s"
                ),
            )
            time_observations.append(obs)

        time_traj = DegradationTrajectory(
            trajectory_id="traj_time_001",
            system_id="batt_cell_X1",
            quantity_type=TrajectoryQuantityType.MULTIVARIATE,
            observations=tuple(time_observations),
        )

        crit_cycle = EOLDefinition(
            criterion_id="crit_cycle_soh",
            criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
            threshold_value=0.80,
            unit="ratio",
        )
        crit_time = EOLDefinition(
            criterion_id="crit_time_soh",
            criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
            threshold_value=0.80,
            unit="ratio",
        )
        portfolio = EOLPortfolio(
            portfolio_id="port_cross_domain",
            name="Cross Domain Portfolio",
            criteria=[crit_cycle, crit_time],
        )

        engine = PrognosticPipelineEngine()
        # Trajectories mapped by criterion ID
        report = engine.assess(
            trajectories={
                "crit_cycle_soh": dual_degradation_trajectory,
                "crit_time_soh": time_traj,
            },
            portfolio=portfolio,
            policy=standard_policy,
            config=PrognosticPipelineConfig(
                resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
                allow_cross_domain_fallback_to_priority=False,
            ),
        )

        # Cross-domain protection: must NOT compare cycles vs days directly
        assert report.limiting_mechanism.status == LimitingResolutionStatus.INCOMPATIBLE_DOMAINS
        assert report.pipeline_status == PipelineStatus.INDETERMINATE_LIMITING
        assert report.limiting_mechanism.margin_to_secondary_rul is None
        assert "Incompatible horizon domains" in report.limiting_mechanism.rationale

        # Individual evaluations are fully preserved
        assert "crit_cycle_soh" in report.criteria_evaluations
        assert "crit_time_soh" in report.criteria_evaluations
        assert report.criteria_evaluations["crit_cycle_soh"].evaluation_result.prediction.is_valid
        assert report.criteria_evaluations["crit_time_soh"].evaluation_result.prediction.is_valid

    def test_partial_portfolio_evaluation_with_missing_channel(
        self,
        dual_degradation_trajectory: DegradationTrajectory,
        standard_policy: DecisionPolicy,
    ) -> None:
        crit_valid = EOLDefinition(
            criterion_id="crit_soh_80",
            criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
            threshold_value=0.80,
            unit="ratio",
        )
        crit_missing = EOLDefinition(
            criterion_id="crit_power_peak",
            criterion_type=EOLCriterionType.PEAK_POWER_THRESHOLD,
            threshold_value=50.0,
            unit="W",
        )
        portfolio = EOLPortfolio(
            portfolio_id="port_partial",
            name="Partial Portfolio",
            criteria=[crit_valid, crit_missing],
        )

        engine = PrognosticPipelineEngine()
        report = engine.assess(
            trajectories=dual_degradation_trajectory,
            portfolio=portfolio,
            policy=standard_policy,
        )

        # One valid, one missing -> PARTIAL_EVALUATION
        assert report.pipeline_status == PipelineStatus.PARTIAL_EVALUATION
        assert report.limiting_mechanism.status == LimitingResolutionStatus.RESOLVED
        assert report.limiting_mechanism.limiting_criterion_id == "crit_soh_80"

        # Missing criterion is recorded as INSUFFICIENT_DATA
        missing_bundle = report.criteria_evaluations["crit_power_peak"]
        assert missing_bundle.evaluation_result.evaluation_status == EvaluationStatus.INSUFFICIENT_DATA
        assert any("unavailable" in lim.lower() for lim in report.consolidated_validity_limitations)

    def test_all_criteria_unavailable(
        self,
        standard_policy: DecisionPolicy,
    ) -> None:
        crit1 = EOLDefinition(
            criterion_id="crit_missing_1",
            criterion_type=EOLCriterionType.PEAK_POWER_THRESHOLD,
            threshold_value=50.0,
            unit="W",
        )
        portfolio = EOLPortfolio(
            portfolio_id="port_none",
            name="No Channels Portfolio",
            criteria=[crit1],
        )

        # Empty trajectory
        empty_traj = DegradationTrajectory(
            trajectory_id="traj_empty",
            system_id="batt_01",
            observations=(),
        )

        engine = PrognosticPipelineEngine()
        report = engine.assess(
            trajectories=empty_traj,
            portfolio=portfolio,
            policy=standard_policy,
        )

        assert report.pipeline_status == PipelineStatus.BLOCKED_BY_VALIDITY
        assert report.limiting_mechanism.status == LimitingResolutionStatus.ALL_CRITERIA_UNAVAILABLE
        assert report.is_actionable is False

    def test_assess_from_state_history(
        self,
        standard_policy: DecisionPolicy,
    ) -> None:
        records = []
        for i in range(10):
            cycle = float(i * 10)
            soh = 1.00 - 0.002 * cycle
            r_mohm = 20.0 * (1.00 + 0.01 * cycle)

            model_st = ModelState(soc_fraction=0.8, temperature_c=25.0)
            est_st = EstimationState(
                soc_fraction=0.8,
                soh_fraction=soh,
                internal_resistance_mohm=r_mohm,
                custom_estimates={
                    "cycle": cycle,
                    "usable_capacity_ah": 5.0 * soh,
                    "resistance_growth_ratio": r_mohm / 20.0,
                },
            )
            rec = TwinStateRecord(
                record_id=f"rec_{i:03d}",
                system_id="batt_from_history",
                timestamp_ns=(i + 1) * 1_000_000_000,
                model_state=model_st,
                estimation_state=est_st,
                quality="VALID",
                metadata={"cycle": str(cycle)},
            )
            records.append(rec)

        crit_soh = EOLDefinition(
            criterion_id="crit_hist_soh",
            criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
            threshold_value=0.80,
            unit="ratio",
        )
        portfolio = EOLPortfolio(
            portfolio_id="port_hist",
            name="History Portfolio",
            criteria=[crit_soh],
        )

        engine = PrognosticPipelineEngine()
        report = engine.assess_from_state_history(
            records=records,
            portfolio=portfolio,
            policy=standard_policy,
        )

        assert report.pipeline_status in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_LIMITATIONS)
        assert report.system_id == "batt_from_history"
        assert report.limiting_mechanism.status == LimitingResolutionStatus.RESOLVED

    def test_deterministic_reproducibility(
        self,
        dual_degradation_trajectory: DegradationTrajectory,
        standard_policy: DecisionPolicy,
    ) -> None:
        crit_soh = EOLDefinition(
            criterion_id="crit_soh_80",
            criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
            threshold_value=0.80,
            unit="ratio",
        )
        portfolio = EOLPortfolio(
            portfolio_id="port_det",
            name="Deterministic Portfolio",
            criteria=[crit_soh],
        )

        engine = PrognosticPipelineEngine()
        report1 = engine.assess(
            trajectories=dual_degradation_trajectory,
            portfolio=portfolio,
            policy=standard_policy,
            report_id="fixed_report_id",
            created_at_utc="2026-10-01T00:00:00Z",
        )
        report2 = engine.assess(
            trajectories=dual_degradation_trajectory,
            portfolio=portfolio,
            policy=standard_policy,
            report_id="fixed_report_id",
            created_at_utc="2026-10-01T00:00:00Z",
        )

        # Prognostic assessments must be 100% deterministically identical
        assert report1.pipeline_status == report2.pipeline_status
        assert report1.system_id == report2.system_id
        assert report1.portfolio_id == report2.portfolio_id
        assert report1.policy_id == report2.policy_id
        assert report1.limiting_mechanism.status == report2.limiting_mechanism.status
        assert report1.limiting_mechanism.limiting_criterion_id == report2.limiting_mechanism.limiting_criterion_id
        assert report1.limiting_mechanism.limiting_rul_value == report2.limiting_mechanism.limiting_rul_value
        assert report1.limiting_mechanism.margin_to_secondary_rul == report2.limiting_mechanism.margin_to_secondary_rul
        assert report1.primary_decision.primary_decision_class == report2.primary_decision.primary_decision_class
        assert report1.primary_decision.primary_priority == report2.primary_decision.primary_priority
        assert report1.primary_decision.primary_recommendation == report2.primary_decision.primary_recommendation
        assert report1.primary_decision.primary_rationale == report2.primary_decision.primary_rationale
        assert report1.is_actionable == report2.is_actionable
        assert report1.is_safety_critical_actuation == report2.is_safety_critical_actuation

        # Criteria evaluations determinism
        for cid in report1.criteria_evaluations:
            e1 = report1.criteria_evaluations[cid]
            e2 = report2.criteria_evaluations[cid]
            assert e1.is_limiting == e2.is_limiting
            assert e1.evaluation_result.evaluation_status == e2.evaluation_result.evaluation_status
            assert e1.evaluation_result.prediction.rul_value == e2.evaluation_result.prediction.rul_value
            assert e1.decision_result.primary_decision_class == e2.decision_result.primary_decision_class

    def test_highest_decision_priority_strategy(
        self,
        dual_degradation_trajectory: DegradationTrajectory,
    ) -> None:
        crit1 = EOLDefinition(
            criterion_id="crit_soh_80",
            criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
            threshold_value=0.80,
            unit="ratio",
        )
        crit2 = EOLDefinition(
            criterion_id="crit_res_200",
            criterion_type=EOLCriterionType.RESISTANCE_GROWTH_RATIO_THRESHOLD,
            threshold_value=2.00,
            unit="ratio",
        )
        portfolio = EOLPortfolio(
            portfolio_id="port_prio",
            name="Priority Portfolio",
            criteria=[crit1, crit2],
        )

        # Policy gives crit2 higher priority
        cond = DecisionCondition(
            condition_id="cond_any",
            rul_threshold_value=100.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        rule_crit = DecisionRule(
            rule_id="rule_critical",
            precedence_rank=1,
            decision_class=DecisionClass.EOL_REACHED,
            priority=RecommendationPriority.CRITICAL,
            actionability=Actionability.MAINTENANCE_RECOMMENDATION,
            condition=cond,
            recommendation_template="Critical",
            rationale_template="Critical",
        )
        policy_crit = DecisionPolicy(
            policy_id="policy_crit",
            policy_name="Critical Policy",
            version="1.0.0",
            rules=[rule_crit],
        )
        policy_nom = DecisionPolicy(
            policy_id="policy_nom",
            policy_name="Nominal Policy",
            version="1.0.0",
            rules=[],
        )

        engine = PrognosticPipelineEngine()
        report = engine.assess(
            trajectories=dual_degradation_trajectory,
            portfolio=portfolio,
            policy={"crit_soh_80": policy_nom, "crit_res_200": policy_crit},
            config=PrognosticPipelineConfig(
                resolution_strategy=LimitingResolutionStrategy.HIGHEST_DECISION_PRIORITY
            ),
        )

        assert report.limiting_mechanism.status == LimitingResolutionStatus.RESOLVED
        assert report.limiting_mechanism.limiting_criterion_id == "crit_res_200"
        assert report.limiting_mechanism.limiting_priority == RecommendationPriority.CRITICAL
