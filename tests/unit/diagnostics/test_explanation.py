"""Unit tests for DiagnosticExplanationBuilder and structured narrative generation."""

import unittest

from src.diagnostics.explanation import DiagnosticExplanationBuilder
from src.diagnostics.types import (
    DiagnosticCategory,
    DiagnosticEvidenceItem,
    DiagnosticSeverity,
    EvidenceEvaluationStatus,
    FaultLifecycleState,
    OperatingContext,
    RootCauseHypothesis,
)
from src.validation.types import SignalProvenance


class TestDiagnosticExplanationBuilder(unittest.TestCase):
    """Test suite verifying explainable narrative construction, evidence grounding, and safety disclaimers."""

    def test_normal_state_explanation(self) -> None:
        """Normal state produces clean nominal summary with empty operator actions."""
        narrative, actions = DiagnosticExplanationBuilder.build_narrative(
            lifecycle_state=FaultLifecycleState.NORMAL,
            severity=DiagnosticSeverity.INFORMATIONAL,
            context=OperatingContext.REST,
            primary_hypothesis=None,
            alternative_hypotheses=(),
            corroborating_channels=(),
            data_quality_status="VALID",
        )
        self.assertIn("STATUS: NORMAL", narrative)
        self.assertIn("REST", narrative)
        self.assertEqual(len(actions), 0)

    def test_diagnosed_explanation_with_evidence_and_confounds(self) -> None:
        """Diagnosed hypothesis includes evidence provenance, rationale, and untestable confounds."""
        hyp = RootCauseHypothesis(
            hypothesis_id="HYP_APPARENT_OHMIC_GROWTH",
            title="Increased Apparent Ohmic Resistance",
            category=DiagnosticCategory.ELECTRICAL,
            evidence_score=0.85,
            confidence_level="STRONG",
            required_signal_coverage=1.0,
            optional_signal_coverage=0.5,
            supporting_evidence=(
                DiagnosticEvidenceItem(
                    source_layer="telemetry",
                    signal_name="pack_voltage_v",
                    observed_value=3.4,
                    expected_value=3.7,
                    provenance=SignalProvenance.MEASURED,
                    status=EvidenceEvaluationStatus.SUPPORTING,
                    weight=0.5,
                    rationale="Terminal IR drop under load",
                ),
            ),
            untestable_confounds=(
                "Cell internal ohmic growth indistinguishable from terminal busbar contact resistance.",
            ),
            suggested_investigations=(
                "Inspect high-current busbars and terminal connections.",
            ),
        )

        narrative, actions = DiagnosticExplanationBuilder.build_narrative(
            lifecycle_state=FaultLifecycleState.DIAGNOSED,
            severity=DiagnosticSeverity.WARNING,
            context=OperatingContext.DISCHARGE_CC,
            primary_hypothesis=hyp,
            alternative_hypotheses=(),
            corroborating_channels=("pack_voltage_v", "identified_r0_ohm"),
            data_quality_status="VALID",
        )

        self.assertIn("PRIMARY HYPOTHESIS: HYP_APPARENT_OHMIC_GROWTH", narrative)
        self.assertIn("SUPPORTING EVIDENCE", narrative)
        self.assertIn("MEASURED", narrative)
        self.assertIn("Independent Corroborating Channels: pack_voltage_v, identified_r0_ohm", narrative)
        self.assertIn("UNTESTABLE PHYSICAL CONFOUNDS", narrative)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0], "Inspect high-current busbars and terminal connections.")

    def test_critical_advisory_safety_disclaimer_present(self) -> None:
        """DIAGNOSED_CRITICAL includes mandatory analytical advisory disclaimer asserting BMS safety authority."""
        hyp = RootCauseHypothesis(
            hypothesis_id="HYP_THERMAL_IMPAIRMENT",
            title="Impaired Thermal Dissipation",
            category=DiagnosticCategory.THERMAL,
            evidence_score=0.90,
            confidence_level="STRONG",
            required_signal_coverage=1.0,
            optional_signal_coverage=1.0,
        )

        narrative, actions = DiagnosticExplanationBuilder.build_narrative(
            lifecycle_state=FaultLifecycleState.DIAGNOSED_CRITICAL,
            severity=DiagnosticSeverity.CRITICAL,
            context=OperatingContext.DYNAMIC_TRANSIENT,
            primary_hypothesis=hyp,
            alternative_hypotheses=(),
            corroborating_channels=("avg_cell_temperature_c", "thermal_residual_c"),
            data_quality_status="VALID",
        )

        self.assertIn("CRITICAL ADVISORY NOTICE", narrative)
        self.assertIn("NOT a physical safety certification", narrative)
        self.assertIn("physical BMS remains the authoritative safety system", narrative)

    def test_data_quality_failed_explanation(self) -> None:
        """DATA_QUALITY_FAILED explicitly explains telemetry suspension reason."""
        narrative, actions = DiagnosticExplanationBuilder.build_narrative(
            lifecycle_state=FaultLifecycleState.DATA_QUALITY_FAILED,
            severity=DiagnosticSeverity.UNKNOWN,
            context=OperatingContext.DATA_GAPPED,
            primary_hypothesis=None,
            alternative_hypotheses=(),
            corroborating_channels=(),
            data_quality_status="DATA_GAPPED",
        )
        self.assertIn("DATA QUALITY FAILURE", narrative)
        self.assertIn("DATA_GAPPED", narrative)
        self.assertIn("Inspect telemetry ingestion pipeline", actions[0])

    def test_insufficient_evidence_missing_signals_explanation(self) -> None:
        """INSUFFICIENT_EVIDENCE lists specific missing required signals."""
        narrative, actions = DiagnosticExplanationBuilder.build_narrative(
            lifecycle_state=FaultLifecycleState.INSUFFICIENT_EVIDENCE,
            severity=DiagnosticSeverity.UNKNOWN,
            context=OperatingContext.REST,
            primary_hypothesis=None,
            alternative_hypotheses=(),
            corroborating_channels=(),
            data_quality_status="VALID",
            missing_required_signals=("cell_voltages_v", "pack_current_a"),
        )
        self.assertIn("INSUFFICIENT EVIDENCE", narrative)
        self.assertIn("cell_voltages_v, pack_current_a", narrative)


if __name__ == "__main__":
    unittest.main()
