"""Diagnostic Explanation Builder for Explainable Battery Intelligence.

Assembles structured, evidence-backed narratives explaining what was observed, why it is anomalous,
evaluated supporting/contraindicating evidence, competing hypotheses, untestable confounds,
and non-actuating operator investigations.
"""

from typing import Optional, Sequence

from src.diagnostics.types import (
    DiagnosticCategory,
    DiagnosticEvidenceItem,
    DiagnosticSeverity,
    EvidenceEvaluationStatus,
    FaultLifecycleState,
    OperatingContext,
    RootCauseHypothesis,
)


class DiagnosticExplanationBuilder:
    """Constructs structured, cautious, evidence-grounded diagnostic assessment narratives."""

    @staticmethod
    def build_narrative(
        lifecycle_state: FaultLifecycleState,
        severity: DiagnosticSeverity,
        context: OperatingContext,
        primary_hypothesis: Optional[RootCauseHypothesis],
        alternative_hypotheses: Sequence[RootCauseHypothesis],
        corroborating_channels: Sequence[str],
        data_quality_status: str,
        missing_required_signals: Sequence[str] = (),
    ) -> tuple[str, tuple[str, ...]]:
        """Builds a structured explanatory narrative and list of suggested operator actions.

        Args:
            lifecycle_state: Active FaultLifecycleState.
            severity: Active DiagnosticSeverity.
            context: OperatingContext of the battery system.
            primary_hypothesis: Leading RootCauseHypothesis or None.
            alternative_hypotheses: Competing RootCauseHypothesis instances.
            corroborating_channels: Canonical identifiers of corroborating signal channels.
            data_quality_status: Data quality flag string.
            missing_required_signals: List of missing required signal names if any.

        Returns:
            Tuple of (explanation_narrative_text, tuple_of_recommended_operator_actions).
        """
        lines: list[str] = []
        actions: list[str] = []

        # 1. Diagnostic Summary
        lines.append(f"=== BATTERY DIAGNOSTIC ASSESSMENT ===")
        lines.append(f"Lifecycle State: {lifecycle_state.value}")
        lines.append(f"Advisory Severity: {severity.value}")
        lines.append(f"Operating Context: {context.value}")

        # 2. Data Quality & Insufficient Evidence Explanations
        if lifecycle_state == FaultLifecycleState.DATA_QUALITY_FAILED:
            lines.append("\n[DATA QUALITY FAILURE]")
            lines.append(
                f"Diagnostic evaluation is suspended due to data quality state '{data_quality_status}'. "
                "Telemetry stream contains gaps, retrograde timestamps, or invalid sensor flags."
            )
            actions.append("Inspect telemetry ingestion pipeline, communication bus integrity, and sensor power rails.")
            return "\n".join(lines), tuple(actions)

        if lifecycle_state == FaultLifecycleState.INSUFFICIENT_EVIDENCE:
            lines.append("\n[INSUFFICIENT EVIDENCE]")
            if missing_required_signals:
                lines.append(
                    f"Required telemetry signals are unavailable for full evaluation: {', '.join(missing_required_signals)}. "
                    "Diagnostic engine cannot evaluate hypothesis rules without required instrumentation."
                )
            else:
                lines.append("Telemetry is valid, but empirical evidence coverage is insufficient for reliable hypothesis evaluation.")
            actions.append("Verify sensor channel configuration and ensure required physical measurements are instrumented.")
            return "\n".join(lines), tuple(actions)

        if lifecycle_state == FaultLifecycleState.NORMAL:
            lines.append("\n[STATUS: NORMAL]")
            lines.append("No actionable analytical anomaly is currently established. All evaluated signals reside within nominal bounds.")
            return "\n".join(lines), tuple()

        # 3. Primary Hypothesis Breakdown
        if primary_hypothesis is not None:
            lines.append(f"\n[PRIMARY HYPOTHESIS: {primary_hypothesis.hypothesis_id}]")
            lines.append(f"Title: {primary_hypothesis.title}")
            lines.append(f"Category: {primary_hypothesis.category.value}")
            lines.append(
                f"Evidence Score: {primary_hypothesis.evidence_score:.4f} "
                f"({primary_hypothesis.confidence_level} empirical evidence strength under configured analytical rules)"
            )
            lines.append(f"Required Signal Coverage: {primary_hypothesis.required_signal_coverage * 100:.1f}%")
            lines.append(f"Optional Signal Coverage: {primary_hypothesis.optional_signal_coverage * 100:.1f}%")

            # Evidence details
            if primary_hypothesis.supporting_evidence:
                lines.append("\n[SUPPORTING EVIDENCE]")
                for item in primary_hypothesis.supporting_evidence:
                    lines.append(
                        f" - {item.signal_name} ({item.provenance.value}): observed={item.observed_value}, "
                        f"expected={item.expected_value} | {item.rationale}"
                    )

            if primary_hypothesis.contraindicating_evidence:
                lines.append("\n[CONTRAINDICATING EVIDENCE]")
                for item in primary_hypothesis.contraindicating_evidence:
                    lines.append(
                        f" - {item.signal_name} ({item.provenance.value}): observed={item.observed_value}, "
                        f"expected={item.expected_value} | {item.rationale}"
                    )

            if corroborating_channels:
                lines.append(f"\nIndependent Corroborating Channels: {', '.join(corroborating_channels)}")

            # Untestable confounds
            if primary_hypothesis.untestable_confounds:
                lines.append("\n[UNTESTABLE PHYSICAL CONFOUNDS]")
                for confound in primary_hypothesis.untestable_confounds:
                    lines.append(f" * {confound}")

            # Collect suggested actions
            actions.extend(primary_hypothesis.suggested_investigations)

        # 4. Competing Alternative Hypotheses
        plausible_alternatives = [
            h for h in alternative_hypotheses
            if h.evidence_score >= 0.20 or h.confidence_level in ("STRONG", "MODERATE", "WEAK")
        ]
        if plausible_alternatives:
            lines.append("\n[COMPETING ALTERNATIVE HYPOTHESES]")
            for alt in plausible_alternatives:
                lines.append(
                    f" - {alt.hypothesis_id} ({alt.category.value}): evidence_score={alt.evidence_score:.4f} "
                    f"[{alt.confidence_level}]. Observed evidence is compatible with multiple candidate explanations."
                )

        # 5. Critical Advisory Safety Notice
        if lifecycle_state == FaultLifecycleState.DIAGNOSED_CRITICAL:
            lines.append("\n" + "=" * 60)
            lines.append("CRITICAL ADVISORY NOTICE:")
            lines.append("This is an analytical critical advisory classification based on configured engineering criteria.")
            lines.append("It is NOT a physical safety certification, replacement for the physical BMS, guarantee of imminent failure,")
            lines.append("or command to disconnect the battery. The physical BMS remains the authoritative safety system.")
            lines.append("=" * 60)

        return "\n".join(lines), tuple(actions)
