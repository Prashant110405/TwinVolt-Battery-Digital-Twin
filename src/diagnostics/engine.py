"""Diagnostic Engine and Hypothesis Orchestration for Explainable Battery Intelligence.

Orchestrates multi-hypothesis evaluation, deterministic ranking, temporal debouncing,
lifecycle state machine transitions, and explainable diagnostic assessments.
"""

from typing import Any, Mapping, Optional, Sequence
import uuid

from src.diagnostics.config import DiagnosticThresholdConfig
from src.diagnostics.context import OperatingContextClassifier
from src.diagnostics.explanation import DiagnosticExplanationBuilder
from src.diagnostics.hypotheses import (
    AbstractDiagnosticHypothesis,
    create_standard_hypotheses,
)
from src.diagnostics.lifecycle import (
    DiagnosticLifecycleTracker,
    LifecycleTransition,
)
from src.diagnostics.temporal import (
    TemporalPersistenceState,
    TemporalPersistenceTracker,
)
from src.diagnostics.types import (
    DiagnosticAssessmentReport,
    DiagnosticCategory,
    DiagnosticEvidenceItem,
    DiagnosticSeverity,
    EvidenceEvaluationStatus,
    FaultLifecycleState,
    OperatingContext,
    RootCauseHypothesis,
)
from src.telemetry.snapshots import TelemetrySnapshot
from src.validation.types import ModelValidationReport, ModelValidationState


class DiagnosticEngine:
    """Central orchestrator for Battery Diagnostics and Explainable Intelligence."""

    def __init__(
        self,
        system_id: str,
        config: Optional[DiagnosticThresholdConfig] = None,
        hypotheses: Optional[Sequence[AbstractDiagnosticHypothesis]] = None,
    ) -> None:
        if not system_id or not isinstance(system_id, str):
            raise ValueError("system_id must be a non-empty string.")

        self._system_id = system_id
        self._config = config or DiagnosticThresholdConfig()
        self._context_classifier = OperatingContextClassifier(config=self._config)
        self._hypotheses: tuple[AbstractDiagnosticHypothesis, ...] = (
            tuple(hypotheses) if hypotheses is not None else create_standard_hypotheses()
        )

        # Instance-local temporal trackers (one per hypothesis)
        self._trackers: dict[str, TemporalPersistenceTracker] = {
            h.hypothesis_id: TemporalPersistenceTracker(hypothesis_id=h.hypothesis_id, config=self._config)
            for h in self._hypotheses
        }
        self._lifecycle_tracker = DiagnosticLifecycleTracker()
        self._latest_assessment: Optional[DiagnosticAssessmentReport] = None

    @property
    def system_id(self) -> str:
        """System identifier."""
        return self._system_id

    @property
    def config(self) -> DiagnosticThresholdConfig:
        """Attached threshold configuration."""
        return self._config

    @property
    def latest_assessment(self) -> Optional[DiagnosticAssessmentReport]:
        """Most recent diagnostic assessment report."""
        return self._latest_assessment

    @property
    def lifecycle_tracker(self) -> DiagnosticLifecycleTracker:
        """Attached lifecycle state tracker."""
        return self._lifecycle_tracker

    def step(
        self,
        telemetry: TelemetrySnapshot,
        evidence_items: Sequence[DiagnosticEvidenceItem] = (),
        model_validation_report: Optional[ModelValidationReport] = None,
        dt_s: Optional[float] = None,
    ) -> DiagnosticAssessmentReport:
        """Executes a complete diagnostic evaluation cycle for a telemetry step.

        Args:
            telemetry: Incoming TelemetrySnapshot.
            evidence_items: Sequence of evaluated DiagnosticEvidenceItem instances.
            model_validation_report: Optional ModelValidationReport from Level 5.3.
            dt_s: Optional step interval in seconds.

        Returns:
            Immutable DiagnosticAssessmentReport.
        """
        if not isinstance(telemetry, TelemetrySnapshot):
            raise TypeError(f"Expected TelemetrySnapshot, got {type(telemetry).__name__}.")

        ts_ns = telemetry.timestamp_ns
        assessment_id = f"diag_{self._system_id}_{ts_ns}_{uuid.uuid4().hex[:8]}"

        # 1. Classify Operating Context
        context = self._context_classifier.classify(telemetry, dt_s=dt_s)

        # 2. Check Data Quality
        data_quality_status = "VALID"
        if context == OperatingContext.DATA_GAPPED:
            data_quality_status = "DATA_GAPPED"
            new_state = self._lifecycle_tracker.transition_to(
                new_state=FaultLifecycleState.DATA_QUALITY_FAILED,
                reason="Telemetry data gap exceeded allowable threshold",
                timestamp_ns=ts_ns,
            )
            narrative, actions = DiagnosticExplanationBuilder.build_narrative(
                lifecycle_state=new_state,
                severity=DiagnosticSeverity.UNKNOWN,
                context=context,
                primary_hypothesis=None,
                alternative_hypotheses=(),
                corroborating_channels=(),
                data_quality_status=data_quality_status,
            )
            report = DiagnosticAssessmentReport(
                assessment_id=assessment_id,
                system_id=self._system_id,
                timestamp_ns=ts_ns,
                lifecycle_state=new_state,
                severity=DiagnosticSeverity.UNKNOWN,
                operating_context=context,
                primary_hypothesis=None,
                alternative_hypotheses=(),
                explanation_narrative=narrative,
                recommended_operator_actions=actions,
                active_anomalies_count=0,
                data_quality_status=data_quality_status,
            )
            self._latest_assessment = report
            return report

        # 3. Model Validation Gating Influence
        val_state = (
            model_validation_report.active_window.state
            if model_validation_report is not None and hasattr(model_validation_report, "active_window")
            else None
        )
        val_state_name = val_state.value if val_state is not None else "UNKNOWN"
        is_model_val_failed = val_state in (
            ModelValidationState.DATA_QUALITY_FAILED,
            ModelValidationState.INSUFFICIENT_DATA,
        )

        # 4. Evaluate Hypotheses and Update Temporal Trackers
        evaluated_hypotheses: list[RootCauseHypothesis] = []
        corroborating_map: dict[str, tuple[str, ...]] = {}

        for hyp in self._hypotheses:
            eval_hyp = hyp.evaluate(
                evidence_items=evidence_items,
                context=context,
                config=self._config,
            )
            evaluated_hypotheses.append(eval_hyp)

            # Determine distinct corroborating channels (deduped canonical signal names)
            supporting_channels = tuple(
                sorted({item.signal_name for item in eval_hyp.supporting_evidence if item.weight > 0})
            )
            corroborating_map[hyp.hypothesis_id] = supporting_channels

            # Update temporal persistence tracker
            tracker = self._trackers[hyp.hypothesis_id]
            is_supporting = (
                eval_hyp.required_signal_coverage == 1.0
                and eval_hyp.evidence_score >= self._config.diagnosis_evidence_score_threshold
            )
            tracker.update(
                timestamp_ns=ts_ns,
                evidence_score=eval_hyp.evidence_score,
                confidence_level=eval_hyp.confidence_level,
                is_supporting=is_supporting,
            )

        # 5. Deterministic Hypothesis Ranking
        # Priority:
        # 1. Full required coverage (1.0 vs <1.0)
        # 2. Evidence score (descending)
        # 3. Persisted status (True vs False)
        # 4. Corroborating channels count (descending)
        # 5. Hypothesis ID tie-breaker
        def ranking_key(h: RootCauseHypothesis) -> tuple[int, float, int, int, str]:
            cov_int = 1 if h.required_signal_coverage == 1.0 else 0
            persisted_int = 1 if self._trackers[h.hypothesis_id].get_state().is_persisted else 0
            channels_count = len(corroborating_map.get(h.hypothesis_id, ()))
            # Negative ID string to invert descending sort order for tie-breaker
            return (cov_int, h.evidence_score, persisted_int, channels_count, h.hypothesis_id)

        ranked_hypotheses = sorted(evaluated_hypotheses, key=ranking_key, reverse=True)

        # Leading hypothesis
        leading_candidate = ranked_hypotheses[0] if ranked_hypotheses else None
        primary_hypothesis: Optional[RootCauseHypothesis] = None
        if leading_candidate and leading_candidate.evidence_score > 0.0 and leading_candidate.required_signal_coverage == 1.0:
            primary_hypothesis = leading_candidate

        alternative_hypotheses = tuple(
            h for h in ranked_hypotheses if primary_hypothesis is None or h.hypothesis_id != primary_hypothesis.hypothesis_id
        )

        leading_channels = (
            corroborating_map.get(primary_hypothesis.hypothesis_id, ())
            if primary_hypothesis is not None
            else ()
        )

        # 6. Critical Advisory Criteria Evaluation (ALL 7 mandatory conditions)
        is_critical_eligible = False
        critical_reasons: list[str] = []

        if primary_hypothesis is not None:
            leading_tracker_state = self._trackers[primary_hypothesis.hypothesis_id].get_state()
            c1_cov = primary_hypothesis.required_signal_coverage == 1.0
            c2_score = primary_hypothesis.evidence_score >= self._config.critical_evidence_score_threshold
            c3_contra = len(primary_hypothesis.contraindicating_evidence) == 0
            c4_channels = len(leading_channels) >= self._config.critical_min_corroborating_channels
            c5_val = not is_model_val_failed
            c6_persist = leading_tracker_state.is_persisted

            if c1_cov and c2_score and c3_contra and c4_channels and c5_val and c6_persist:
                is_critical_eligible = True
            else:
                if not c1_cov:
                    critical_reasons.append("Incomplete required signal coverage")
                if not c2_score:
                    critical_reasons.append(f"Evidence score ({primary_hypothesis.evidence_score:.2f}) < {self._config.critical_evidence_score_threshold}")
                if not c3_contra:
                    critical_reasons.append("Active contraindicating evidence present")
                if not c4_channels:
                    critical_reasons.append(f"Corroborating channels ({len(leading_channels)}) < {self._config.critical_min_corroborating_channels}")
                if not c5_val:
                    critical_reasons.append("Upstream model validation state failed or insufficient")
                if not c6_persist:
                    critical_reasons.append("Persistence debounce threshold not yet reached")

        # 7. Drive Lifecycle State Transitions
        if primary_hypothesis is None:
            # Check if any hypothesis has incomplete required coverage with supporting evidence
            any_insufficient = any(
                h.required_signal_coverage < 1.0 and len(h.supporting_evidence) > 0
                for h in evaluated_hypotheses
            )
            # Check if recovering
            any_recovered = any(
                t.get_state().is_recovered for t in self._trackers.values()
            )

            if any_insufficient:
                new_state = self._lifecycle_tracker.transition_to(
                    new_state=FaultLifecycleState.INSUFFICIENT_EVIDENCE,
                    reason="Required evidence signals unavailable for complete hypothesis evaluation",
                    timestamp_ns=ts_ns,
                )
            elif any_recovered:
                new_state = self._lifecycle_tracker.transition_to(
                    new_state=FaultLifecycleState.RECOVERED,
                    reason="Previous anomaly cleared across configured recovery hysteresis steps",
                    timestamp_ns=ts_ns,
                )
            else:
                new_state = self._lifecycle_tracker.transition_to(
                    new_state=FaultLifecycleState.NORMAL,
                    reason="All evaluated signals within nominal bounds",
                    timestamp_ns=ts_ns,
                )
        else:
            leading_tracker_state = self._trackers[primary_hypothesis.hypothesis_id].get_state()

            if is_critical_eligible:
                new_state = self._lifecycle_tracker.transition_to(
                    new_state=FaultLifecycleState.DIAGNOSED_CRITICAL,
                    reason=f"Critical advisory criteria satisfied for {primary_hypothesis.hypothesis_id}",
                    timestamp_ns=ts_ns,
                )
            elif (
                primary_hypothesis.evidence_score >= self._config.diagnosis_evidence_score_threshold
                and leading_tracker_state.is_persisted
            ):
                new_state = self._lifecycle_tracker.transition_to(
                    new_state=FaultLifecycleState.DIAGNOSED,
                    reason=f"Diagnosed condition established for {primary_hypothesis.hypothesis_id}",
                    timestamp_ns=ts_ns,
                )
            elif leading_tracker_state.is_persisted:
                new_state = self._lifecycle_tracker.transition_to(
                    new_state=FaultLifecycleState.SUSPECTED,
                    reason=f"Persistent evidence accumulated for {primary_hypothesis.hypothesis_id}",
                    timestamp_ns=ts_ns,
                )
            else:
                new_state = self._lifecycle_tracker.transition_to(
                    new_state=FaultLifecycleState.ANOMALY_DETECTED,
                    reason=f"Preliminary anomaly observed for {primary_hypothesis.hypothesis_id}, pending persistence",
                    timestamp_ns=ts_ns,
                )

        # 8. Assign Advisory Severity
        if new_state == FaultLifecycleState.DIAGNOSED_CRITICAL:
            severity = DiagnosticSeverity.CRITICAL
        elif new_state == FaultLifecycleState.DIAGNOSED:
            severity = DiagnosticSeverity.WARNING
        elif new_state in (FaultLifecycleState.SUSPECTED, FaultLifecycleState.ANOMALY_DETECTED):
            severity = DiagnosticSeverity.INFORMATIONAL
        elif new_state in (FaultLifecycleState.DATA_QUALITY_FAILED, FaultLifecycleState.INSUFFICIENT_EVIDENCE):
            severity = DiagnosticSeverity.UNKNOWN
        else:
            severity = DiagnosticSeverity.INFORMATIONAL

        # 9. Build Explainability Narrative
        narrative, actions = DiagnosticExplanationBuilder.build_narrative(
            lifecycle_state=new_state,
            severity=severity,
            context=context,
            primary_hypothesis=primary_hypothesis,
            alternative_hypotheses=alternative_hypotheses,
            corroborating_channels=leading_channels,
            data_quality_status=data_quality_status,
        )

        active_anomalies_count = sum(
            1 for h in evaluated_hypotheses if len(h.supporting_evidence) > 0
        )

        report = DiagnosticAssessmentReport(
            assessment_id=assessment_id,
            system_id=self._system_id,
            timestamp_ns=ts_ns,
            lifecycle_state=new_state,
            severity=severity,
            operating_context=context,
            primary_hypothesis=primary_hypothesis,
            alternative_hypotheses=alternative_hypotheses,
            explanation_narrative=narrative,
            recommended_operator_actions=actions,
            active_anomalies_count=active_anomalies_count,
            data_quality_status=data_quality_status,
            diagnostics={
                "corroborating_channels": list(leading_channels),
                "is_critical_eligible": is_critical_eligible,
                "critical_ineligibility_reasons": critical_reasons,
                "model_validation_state": val_state_name,
                "last_transition_reason": self._lifecycle_tracker.last_transition_reason,
            },
        )

        self._latest_assessment = report
        return report

    def reset(self) -> None:
        """Resets all internal trackers, lifecycle states, and context classifier to initial condition."""
        self._context_classifier.reset()
        for tracker in self._trackers.values():
            tracker.reset()
        self._lifecycle_tracker.reset()
        self._latest_assessment = None
