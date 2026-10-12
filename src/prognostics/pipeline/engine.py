"""Prognostic Pipeline Orchestration and Multi-Criterion Assessment Engine.

Orchestrates pure, deterministic, and auditable multi-criterion prognostic evaluations:
1. Multi-Criterion Degradation Dispatch (Level 6.2 trajectory -> Level 6.3/6.4/6.5 evaluation -> Level 6.6 decision).
2. Limiting Degradation Mechanism Resolution with explicit strategy and cross-domain protection.
3. Decision Aggregation & Secondary Advisory Consolidation.
4. Comprehensive Prognostic Assessment Report Synthesis.
5. Strict Safety Authority Separation (Physical BMS remains control authority).
"""

import datetime
from typing import Any, Mapping, Optional, Sequence, Union
import uuid

from src.prognostics.decision.engine import PrognosticDecisionEngine
from src.prognostics.decision.policy import DecisionPolicy
from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    DecisionStatus,
    PrognosticDecisionResult,
    RecommendationPriority,
    SecondaryAdvisory,
)
from src.prognostics.evaluation.eol import EOLEvaluator
from src.prognostics.evaluation.evaluator import PrognosticEvaluationEngine
from src.prognostics.evaluation.types import (
    EOLAssessment,
    EOLState,
    EvaluationStatus,
    EvaluationValidity,
    PrognosticEvaluationResult,
)
from src.prognostics.features import DegradationFeatureSet, TrajectoryFeatureExtractor
from src.prognostics.pipeline.adapter import StateHistoryTrajectoryAdapter
from src.prognostics.pipeline.config import EOLPortfolio, PrognosticPipelineConfig
from src.prognostics.pipeline.limiting import LimitingMechanismResolver
from src.prognostics.pipeline.types import (
    CriterionPrognosticEvaluation,
    LimitingMechanismAssessment,
    LimitingResolutionStatus,
    PipelineStatus,
    PrognosticAssessmentReport,
)
from src.prognostics.prediction import EOLDefinition, RULPredictionResult
from src.prognostics.trajectory import DegradationTrajectory
from src.prognostics.trajectory_types import TrajectoryQuantityType
from src.prognostics.types import (
    EOLCriterionType,
    HorizonDomain,
    PrognosticStatus,
)
from src.prognostics.uncertainty.types import EvidenceStrength, UncertaintyStatus
from src.storage.base import TwinStateRecord


_CRITERION_TO_TRAJECTORY_QTY: dict[EOLCriterionType, TrajectoryQuantityType] = {
    EOLCriterionType.CAPACITY_RETENTION_THRESHOLD: TrajectoryQuantityType.CAPACITY_RETENTION,
    EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD: TrajectoryQuantityType.CAPACITY,
    EOLCriterionType.RESISTANCE_GROWTH_RATIO_THRESHOLD: TrajectoryQuantityType.RESISTANCE_GROWTH_RATIO,
    EOLCriterionType.ABSOLUTE_RESISTANCE_THRESHOLD: TrajectoryQuantityType.INTERNAL_RESISTANCE,
    EOLCriterionType.PEAK_POWER_THRESHOLD: TrajectoryQuantityType.CUSTOM,
    EOLCriterionType.APPLICATION_SPECIFIC: TrajectoryQuantityType.CUSTOM,
    EOLCriterionType.CUSTOM: TrajectoryQuantityType.CUSTOM,
}


class PrognosticPipelineEngine:
    """Pure, stateless orchestrator for multi-criterion prognostic portfolio assessment."""

    def __init__(
        self,
        engine_id: str = "twinvolt_prognostic_pipeline_engine",
        version: str = "1.0.0",
    ) -> None:
        self._engine_id = engine_id
        self._version = version
        self._evaluation_engine = PrognosticEvaluationEngine()
        self._decision_engine = PrognosticDecisionEngine()
        self._feature_extractor = TrajectoryFeatureExtractor()

    def assess(
        self,
        trajectories: Union[
            DegradationTrajectory,
            Sequence[DegradationTrajectory],
            Mapping[Any, DegradationTrajectory],
        ],
        portfolio: EOLPortfolio,
        policy: Union[DecisionPolicy, Mapping[str, DecisionPolicy]],
        config: Optional[PrognosticPipelineConfig] = None,
        report_id: Optional[str] = None,
        system_id: Optional[str] = None,
        report_timestamp_ns: Optional[int] = None,
        created_at_utc: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> PrognosticAssessmentReport:
        """Executes multi-criterion prognostic assessment over input degradation trajectories.

        Parameters
        ----------
        trajectories:
            Single trajectory, sequence of trajectories, or mapping of trajectories keyed
            by criterion ID, quantity name, or TrajectoryQuantityType.
        portfolio:
            Immutable multi-mechanism EOLPortfolio containing EOLDefinitions.
        policy:
            DecisionPolicy applied across all criteria, or a mapping of criterion_id -> DecisionPolicy.
        config:
            Optional pipeline configuration governing strategy, feature extraction, and fallbacks.
        report_id:
            Optional explicit report ID.
        system_id:
            Optional explicit system identifier.
        report_timestamp_ns:
            Optional explicit report timestamp in nanoseconds.
        created_at_utc:
            Optional ISO-8601 UTC creation timestamp.
        metadata:
            Optional additional metadata.

        Returns
        -------
        PrognosticAssessmentReport
            Immutable, consolidated multi-criterion assessment report.
        """
        # 1. Parameter Normalization & Validation
        if not isinstance(portfolio, EOLPortfolio):
            raise TypeError(f"Expected EOLPortfolio, got {type(portfolio).__name__}.")

        active_config = config or PrognosticPipelineConfig()
        rep_id = report_id or f"report_{uuid.uuid4().hex[:8]}"
        now_utc = created_at_utc or datetime.datetime.now(datetime.timezone.utc).isoformat()
        traj_map = self._normalize_trajectories(trajectories)

        # Resolve system ID
        sys_id = system_id
        if sys_id is None:
            for t in traj_map.values():
                if isinstance(t, DegradationTrajectory):
                    sys_id = t.system_id
                    break
        if sys_id is None:
            sys_id = "unknown_battery_system"

        # Resolve timestamp
        ts_ns = report_timestamp_ns
        if ts_ns is None:
            max_ts = 0
            for t in traj_map.values():
                if isinstance(t, DegradationTrajectory) and t.end_timestamp_ns:
                    max_ts = max(max_ts, t.end_timestamp_ns)
            ts_ns = max_ts

        # 2. Extract Features if Enabled
        feature_set: Optional[DegradationFeatureSet] = None
        primary_traj = next((t for t in traj_map.values() if isinstance(t, DegradationTrajectory)), None)
        if active_config.extract_features and primary_traj is not None and primary_traj.total_observations >= 2:
            try:
                feature_set = self._feature_extractor.extract_features(primary_traj)
            except Exception:
                feature_set = None

        # 3. Multi-Criterion Dispatch (Independent Evaluation)
        criteria_evals: dict[str, CriterionPrognosticEvaluation] = {}
        validity_limitations: list[str] = []

        for criterion in portfolio.criteria:
            crit_id = criterion.criterion_id
            matched_traj = self._match_trajectory_for_criterion(criterion, traj_map)

            # Resolve criterion policy
            if isinstance(policy, DecisionPolicy):
                crit_policy = policy
            elif isinstance(policy, Mapping):
                if crit_id in policy:
                    crit_policy = policy[crit_id]
                elif "default" in policy:
                    crit_policy = policy["default"]
                else:
                    raise ValueError(f"No DecisionPolicy supplied for criterion_id '{crit_id}'.")
            else:
                raise TypeError(f"Expected DecisionPolicy or Mapping, got {type(policy).__name__}.")

            target_field = EOLEvaluator._map_eol_field_name(criterion.criterion_type)

            if matched_traj is None or matched_traj.total_observations == 0:
                # Criterion quantity is unavailable in supplied trajectories
                eval_result = self._create_missing_data_evaluation(criterion, sys_id, ts_ns)
                decision_result = self._decision_engine.evaluate(eval_result, crit_policy)
                validity_limitations.append(
                    f"Criterion '{crit_id}': Required degradation quantity channel '{target_field}' unavailable."
                )
            else:
                # Execute Level 6.5 Evaluation
                eval_result = self._evaluation_engine.evaluate(
                    trajectory=matched_traj,
                    eol_definition=criterion,
                    estimator_config=active_config.estimator_config,
                    uncertainty_config=active_config.uncertainty_config,
                    extract_features=False,
                )
                # Execute Level 6.6 Decision Synthesis
                decision_result = self._decision_engine.evaluate(
                    evaluation=eval_result,
                    policy=crit_policy,
                )

                for diag in eval_result.diagnostics:
                    validity_limitations.append(f"Criterion '{crit_id}': {diag}")
                for lim in eval_result.validity.limitations:
                    validity_limitations.append(f"Criterion '{crit_id}': {lim}")

            bundle = CriterionPrognosticEvaluation(
                criterion_id=crit_id,
                eol_definition=criterion,
                evaluation_result=eval_result,
                decision_result=decision_result,
                is_limiting=False,
            )
            criteria_evals[crit_id] = bundle

        # 4. Limiting Mechanism Resolution
        eval_list = list(criteria_evals.values())
        limiting_assessment = LimitingMechanismResolver.resolve(
            criteria_evaluations=eval_list,
            strategy=active_config.resolution_strategy,
            allow_cross_domain_fallback_to_priority=active_config.allow_cross_domain_fallback_to_priority,
        )

        # Mark limiting flag on winning criterion
        if (
            limiting_assessment.status == LimitingResolutionStatus.RESOLVED
            and limiting_assessment.limiting_criterion_id in criteria_evals
        ):
            winner_id = limiting_assessment.limiting_criterion_id
            old_bundle = criteria_evals[winner_id]
            criteria_evals[winner_id] = CriterionPrognosticEvaluation(
                criterion_id=old_bundle.criterion_id,
                eol_definition=old_bundle.eol_definition,
                evaluation_result=old_bundle.evaluation_result,
                decision_result=old_bundle.decision_result,
                is_limiting=True,
                metadata=old_bundle.metadata,
            )

        # 5. Consolidated Secondary Advisories
        secondary_advisories: list[SecondaryAdvisory] = []
        for crit_id, bundle in criteria_evals.items():
            # Include criterion-level secondary advisories
            for adv in bundle.decision_result.secondary_advisories:
                secondary_advisories.append(adv)

            # If criterion is not limiting but produced an actionable recommendation, include as secondary advisory
            if not bundle.is_limiting and bundle.decision_result.is_actionable:
                rul_val = (
                    bundle.evaluation_result.prediction.rul_value
                    if bundle.evaluation_result.prediction
                    else None
                )
                sec_adv = SecondaryAdvisory(
                    advisory_id=f"adv_sec_{crit_id}_{uuid.uuid4().hex[:6]}",
                    decision_class=bundle.decision_result.primary_decision_class,
                    priority=bundle.decision_result.primary_priority,
                    actionability=bundle.decision_result.primary_actionability,
                    summary=f"Secondary Criterion '{crit_id}': {bundle.decision_result.primary_recommendation}",
                    rationale=bundle.decision_result.primary_rationale,
                    category="SECONDARY_CRITERION",
                    source=f"PORTFOLIO_CRITERION:{crit_id}",
                    metadata={"criterion_id": crit_id, "rul_value": rul_val},
                )
                secondary_advisories.append(sec_adv)

        # 6. Synthesize Primary Decision
        primary_decision: PrognosticDecisionResult
        if (
            limiting_assessment.status == LimitingResolutionStatus.RESOLVED
            and limiting_assessment.limiting_criterion_id in criteria_evals
        ):
            primary_decision = criteria_evals[limiting_assessment.limiting_criterion_id].decision_result
        else:
            primary_decision = self._create_indeterminate_decision(limiting_assessment, sys_id, ts_ns, now_utc)

        # 7. Determine PipelineStatus
        pipeline_status = self._determine_pipeline_status(criteria_evals, limiting_assessment)

        policy_id_str = policy.policy_id if isinstance(policy, DecisionPolicy) else "composite_policies"

        return PrognosticAssessmentReport(
            report_id=rep_id,
            system_id=sys_id,
            report_timestamp_ns=ts_ns,
            created_at_utc=now_utc,
            pipeline_status=pipeline_status,
            limiting_mechanism=limiting_assessment,
            criteria_evaluations=criteria_evals,
            primary_decision=primary_decision,
            feature_set=feature_set,
            consolidated_secondary_advisories=tuple(secondary_advisories),
            consolidated_validity_limitations=tuple(dict.fromkeys(validity_limitations)),
            portfolio_id=portfolio.portfolio_id,
            policy_id=policy_id_str,
            is_safety_critical_actuation=False,
            safety_authority="Physical BMS",
            reproducibility_metadata={
                "engine_id": self._engine_id,
                "engine_version": self._version,
                "criteria_count": len(portfolio.criteria),
                "resolution_strategy": active_config.resolution_strategy.value,
                "custom_parameters": dict(active_config.custom_parameters),
                "custom_metadata": dict(metadata or {}),
            },
        )

    def assess_from_state_history(
        self,
        records: Sequence[TwinStateRecord],
        portfolio: EOLPortfolio,
        policy: Union[DecisionPolicy, Mapping[str, DecisionPolicy]],
        config: Optional[PrognosticPipelineConfig] = None,
        report_id: Optional[str] = None,
        system_id: Optional[str] = None,
        report_timestamp_ns: Optional[int] = None,
        created_at_utc: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> PrognosticAssessmentReport:
        """Convenience method to extract trajectories from state history and execute assessment."""
        if not records:
            raise ValueError("records sequence cannot be empty.")

        # Adapt state history into multivariate trajectory containing all available channels
        multi_traj = StateHistoryTrajectoryAdapter.extract_multivariate_trajectory(
            records=records,
            system_id=system_id or records[0].system_id,
        )

        return self.assess(
            trajectories=multi_traj,
            portfolio=portfolio,
            policy=policy,
            config=config,
            report_id=report_id,
            system_id=system_id,
            report_timestamp_ns=report_timestamp_ns,
            created_at_utc=created_at_utc,
            metadata=metadata,
        )

    def _normalize_trajectories(
        self,
        trajectories: Union[
            DegradationTrajectory,
            Sequence[DegradationTrajectory],
            Mapping[Any, DegradationTrajectory],
        ],
    ) -> dict[Any, DegradationTrajectory]:
        """Normalizes various trajectory input forms into a structured dictionary."""
        if isinstance(trajectories, DegradationTrajectory):
            return {trajectories.quantity_type: trajectories, trajectories.trajectory_id: trajectories}
        elif isinstance(trajectories, Mapping):
            return dict(trajectories)
        elif isinstance(trajectories, Sequence):
            res: dict[Any, DegradationTrajectory] = {}
            for t in trajectories:
                if isinstance(t, DegradationTrajectory):
                    res[t.quantity_type] = t
                    res[t.trajectory_id] = t
            return res
        else:
            raise TypeError(f"Unsupported trajectories input type: {type(trajectories).__name__}.")

    def _match_trajectory_for_criterion(
        self,
        criterion: EOLDefinition,
        traj_map: Mapping[Any, DegradationTrajectory],
    ) -> Optional[DegradationTrajectory]:
        """Finds matching DegradationTrajectory for an EOLDefinition."""
        # 1. Match by criterion_id
        if criterion.criterion_id in traj_map:
            return traj_map[criterion.criterion_id]

        # 2. Match by TrajectoryQuantityType
        expected_qty = _CRITERION_TO_TRAJECTORY_QTY.get(criterion.criterion_type)
        if expected_qty in traj_map:
            return traj_map[expected_qty]

        # 3. If MULTIVARIATE trajectory present, check if it contains the needed quantity
        target_field = EOLEvaluator._map_eol_field_name(criterion.criterion_type)
        for t in traj_map.values():
            if isinstance(t, DegradationTrajectory):
                if t.quantity_type == TrajectoryQuantityType.MULTIVARIATE:
                    if any(obs.is_quantity_available(target_field) for obs in t.observations):
                        return t
                    # For resistance growth ratio, internal resistance with baseline in metadata is valid
                    if target_field == "resistance_growth_ratio" and any(
                        obs.is_quantity_available("internal_resistance_r0_ohm") for obs in t.observations
                    ):
                        return t

        # 4. Fallback: match by quantity_type on individual trajectory
        for t in traj_map.values():
            if isinstance(t, DegradationTrajectory):
                if t.quantity_type == expected_qty:
                    return t

        return None

    def _create_missing_data_evaluation(
        self,
        criterion: EOLDefinition,
        system_id: str,
        timestamp_ns: int,
    ) -> PrognosticEvaluationResult:
        """Constructs an explicit INSUFFICIENT_DATA evaluation result for missing channels."""
        target_field = EOLEvaluator._map_eol_field_name(criterion.criterion_type)
        eval_id = f"eval_missing_{criterion.criterion_id}_{uuid.uuid4().hex[:6]}"
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        pred = RULPredictionResult(
            prediction_id=f"pred_missing_{criterion.criterion_id}",
            prediction_timestamp_ns=timestamp_ns,
            created_at_utc=now_utc,
            system_id=system_id,
            status=PrognosticStatus.INSUFFICIENT_DATA,
            rul_value=None,
            rul_unit="cycle",
            rul_domain=HorizonDomain.CYCLE,
            eol_definition=criterion,
            diagnostic_message=f"Required degradation channel '{target_field}' is unavailable in telemetry.",
        )
        eol_ass = EOLAssessment(
            eol_state=EOLState.INDETERMINATE,
            eol_definition=criterion,
            threshold_value=float(criterion.threshold_value),
            comparison_operator=criterion.comparison_operator,
            unit=criterion.unit,
            quantity_name=target_field,
            diagnostic_message="Telemetry channel unavailable to assess EOL state.",
        )
        val = EvaluationValidity(
            data_quality=PrognosticStatus.INSUFFICIENT_DATA,
            history_sufficiency=PrognosticStatus.INSUFFICIENT_DATA,
            domain_validity=PrognosticStatus.INSUFFICIENT_DATA,
            eol_validity=True,
            prediction_validity=False,
            uncertainty_availability=UncertaintyStatus.UNDEFINED,
            evidence_strength=EvidenceStrength.INSUFFICIENT,
            limitations=(f"Channel '{target_field}' missing from telemetry.",),
            is_usable_for_decision=False,
        )
        return PrognosticEvaluationResult(
            evaluation_id=eval_id,
            system_id=system_id,
            evaluation_timestamp_ns=timestamp_ns,
            created_at_utc=now_utc,
            evaluation_status=EvaluationStatus.INSUFFICIENT_DATA,
            eol_assessment=eol_ass,
            validity=val,
            prediction=pred,
            diagnostics=(f"Degradation channel '{target_field}' unavailable.",),
        )

    def _create_indeterminate_decision(
        self,
        limiting_assessment: LimitingMechanismAssessment,
        system_id: str,
        timestamp_ns: int,
        created_at_utc: str,
    ) -> PrognosticDecisionResult:
        """Constructs an explicit non-actionable decision when limiting mechanism is indeterminate."""
        rationale = (
            limiting_assessment.rationale
            or "Limiting degradation mechanism could not be resolved from criteria evaluations."
        )
        return PrognosticDecisionResult(
            decision_id=f"dec_indet_{uuid.uuid4().hex[:6]}",
            system_id=system_id,
            decision_timestamp_ns=timestamp_ns,
            created_at_utc=created_at_utc,
            status=DecisionStatus.INDETERMINATE,
            primary_decision_class=DecisionClass.INDETERMINATE_STATE,
            primary_recommendation="Multi-criterion prognostic assessment is indeterminate.",
            primary_priority=RecommendationPriority.INFORMATIONAL,
            primary_actionability=Actionability.NON_ACTIONABLE,
            primary_rationale=rationale,
            policy_id="composite_indeterminate",
            policy_version="1.0.0",
            validity_limitations=(rationale,),
            is_safety_critical_actuation=False,
        )

    def _determine_pipeline_status(
        self,
        criteria_evals: Mapping[str, CriterionPrognosticEvaluation],
        limiting: LimitingMechanismAssessment,
    ) -> PipelineStatus:
        """Determines top-level PipelineStatus from criteria evaluations and limiting assessment."""
        statuses = [b.evaluation_result.evaluation_status for b in criteria_evals.values()]

        if limiting.status in (
            LimitingResolutionStatus.INCOMPATIBLE_DOMAINS,
            LimitingResolutionStatus.INCOMPATIBLE_UNITS,
        ):
            return PipelineStatus.INDETERMINATE_LIMITING

        if all(s == EvaluationStatus.VALID for s in statuses):
            return PipelineStatus.SUCCESS
        elif all(s in (EvaluationStatus.VALID, EvaluationStatus.VALID_WITH_LIMITATIONS) for s in statuses):
            return PipelineStatus.SUCCESS_WITH_LIMITATIONS
        elif any(s in (EvaluationStatus.VALID, EvaluationStatus.VALID_WITH_LIMITATIONS) for s in statuses):
            return PipelineStatus.PARTIAL_EVALUATION
        else:
            return PipelineStatus.BLOCKED_BY_VALIDITY
