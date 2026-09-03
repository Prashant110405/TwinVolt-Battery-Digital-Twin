"""Unit tests for EvidenceScoringEngine and evidence evaluation mathematics."""

import math
import unittest

from src.diagnostics.config import DiagnosticThresholdConfig
from src.diagnostics.evidence import EvidenceScoreResult, EvidenceScoringEngine
from src.diagnostics.types import (
    DiagnosticEvidenceItem,
    EvidenceEvaluationStatus,
)
from src.validation.types import SignalProvenance


class TestEvidenceScoringEngine(unittest.TestCase):
    """Test suite verifying deterministic evidence scoring, coverage separation, and confidence mapping."""

    def test_single_supporting_rule(self) -> None:
        """Single supporting rule evaluates to proportional score and coverage."""
        item = DiagnosticEvidenceItem(
            source_layer="telemetry",
            signal_name="voltage_rmse_v",
            observed_value=0.045,
            expected_value=0.010,
            provenance=SignalProvenance.MEASURED,
            status=EvidenceEvaluationStatus.SUPPORTING,
            weight=0.8,
            rationale="Measured voltage RMSE exceeds threshold",
        )
        result = EvidenceScoringEngine.evaluate_evidence(
            evidence_items=[item],
            required_signals=["voltage_rmse_v"],
            optional_signals=[],
            total_possible_supporting_weight=1.0,
        )

        self.assertAlmostEqual(result.evidence_score, 0.8)
        self.assertEqual(result.required_signal_coverage, 1.0)
        self.assertEqual(result.optional_signal_coverage, 1.0)
        self.assertEqual(result.confidence_level, "STRONG")
        self.assertEqual(len(result.supporting_evidence), 1)
        self.assertEqual(len(result.contraindicating_evidence), 0)

    def test_support_and_contraindication_penalty(self) -> None:
        """Contraindicating evidence deducts penalty weight from supporting weight."""
        item_sup = DiagnosticEvidenceItem(
            source_layer="telemetry",
            signal_name="voltage_rmse_v",
            observed_value=0.050,
            expected_value=0.010,
            provenance=SignalProvenance.MEASURED,
            status=EvidenceEvaluationStatus.SUPPORTING,
            weight=0.7,
            rationale="High residual supports fault",
        )
        item_contra = DiagnosticEvidenceItem(
            source_layer="validation",
            signal_name="model_validation_state",
            observed_value="DEGRADED",
            expected_value="VALIDATED",
            provenance=SignalProvenance.DERIVED,
            status=EvidenceEvaluationStatus.CONTRAINDICATING,
            weight=0.3,
            rationale="Model validation degraded penalizes physical attribution",
        )

        result = EvidenceScoringEngine.evaluate_evidence(
            evidence_items=[item_sup, item_contra],
            required_signals=["voltage_rmse_v", "model_validation_state"],
            optional_signals=[],
            total_possible_supporting_weight=1.0,
        )

        # Net score = (0.7 - 0.3) / 1.0 = 0.4
        self.assertAlmostEqual(result.evidence_score, 0.4)
        self.assertEqual(result.required_signal_coverage, 1.0)
        self.assertEqual(result.confidence_level, "WEAK")
        self.assertEqual(len(result.supporting_evidence), 1)
        self.assertEqual(len(result.contraindicating_evidence), 1)

    def test_exclusively_contraindicating_evidence(self) -> None:
        """Exclusively contraindicating evidence results in score 0.0 and REJECTED status."""
        item_contra = DiagnosticEvidenceItem(
            source_layer="validation",
            signal_name="model_validation_state",
            observed_value="DEGRADED",
            expected_value="VALIDATED",
            provenance=SignalProvenance.DERIVED,
            status=EvidenceEvaluationStatus.CONTRAINDICATING,
            weight=0.5,
            rationale="Active contraindication",
        )
        result = EvidenceScoringEngine.evaluate_evidence(
            evidence_items=[item_contra],
            required_signals=["model_validation_state"],
            optional_signals=[],
            total_possible_supporting_weight=1.0,
        )

        self.assertEqual(result.evidence_score, 0.0)
        self.assertEqual(result.confidence_level, "REJECTED")

    def test_zero_positive_supporting_evidence(self) -> None:
        """Zero positive supporting evidence produces EvidenceScore 0.0 and NO_EVIDENCE confidence."""
        item_neutral = DiagnosticEvidenceItem(
            source_layer="telemetry",
            signal_name="voltage_rmse_v",
            observed_value=0.005,
            expected_value=0.005,
            provenance=SignalProvenance.MEASURED,
            status=EvidenceEvaluationStatus.NO_EVIDENCE,
            weight=0.5,
            rationale="Signal within nominal bounds",
        )
        result = EvidenceScoringEngine.evaluate_evidence(
            evidence_items=[item_neutral],
            required_signals=["voltage_rmse_v"],
            optional_signals=[],
            total_possible_supporting_weight=1.0,
        )

        self.assertEqual(result.evidence_score, 0.0)
        self.assertEqual(result.confidence_level, "NO_EVIDENCE")

    def test_zero_configured_positive_weight(self) -> None:
        """Zero configured positive weight yields score 0.0 without division by zero."""
        result = EvidenceScoringEngine.evaluate_evidence(
            evidence_items=[],
            required_signals=[],
            optional_signals=[],
            total_possible_supporting_weight=0.0,
        )
        self.assertEqual(result.evidence_score, 0.0)
        self.assertEqual(result.confidence_level, "NO_EVIDENCE")

    def test_duplicate_signal_deduplication(self) -> None:
        """Duplicate canonical signal entries are deduped by canonical signal identifier."""
        item_old = DiagnosticEvidenceItem(
            source_layer="telemetry",
            signal_name="voltage_rmse_v",
            observed_value=0.030,
            expected_value=0.010,
            provenance=SignalProvenance.MEASURED,
            status=EvidenceEvaluationStatus.SUPPORTING,
            weight=0.4,
            rationale="Older sample",
        )
        item_new = DiagnosticEvidenceItem(
            source_layer="telemetry",
            signal_name="voltage_rmse_v",
            observed_value=0.060,
            expected_value=0.010,
            provenance=SignalProvenance.MEASURED,
            status=EvidenceEvaluationStatus.SUPPORTING,
            weight=0.8,
            rationale="Latest sample",
        )

        result = EvidenceScoringEngine.evaluate_evidence(
            evidence_items=[item_old, item_new],
            required_signals=["voltage_rmse_v"],
            optional_signals=[],
            total_possible_supporting_weight=1.0,
        )

        # Retains latest entry (weight = 0.8), does not sum to 1.2
        self.assertAlmostEqual(result.evidence_score, 0.8)
        self.assertEqual(len(result.supporting_evidence), 1)

    def test_required_coverage_shortage_clamps_score(self) -> None:
        """Missing required signal causes required_coverage < 1.0 and INSUFFICIENT_DATA."""
        item_sup = DiagnosticEvidenceItem(
            source_layer="telemetry",
            signal_name="pack_voltage_v",
            observed_value=3.2,
            expected_value=3.7,
            provenance=SignalProvenance.MEASURED,
            status=EvidenceEvaluationStatus.SUPPORTING,
            weight=0.8,
            rationale="Voltage drop observed",
        )
        # Required signals are ["pack_voltage_v", "pack_current_a"]
        result = EvidenceScoringEngine.evaluate_evidence(
            evidence_items=[item_sup],
            required_signals=["pack_voltage_v", "pack_current_a"],
            optional_signals=[],
            total_possible_supporting_weight=1.0,
        )

        self.assertEqual(result.required_signal_coverage, 0.5)
        self.assertEqual(result.evidence_score, 0.0)  # Clamped to 0.0 on incomplete required signals
        self.assertEqual(result.confidence_level, "INSUFFICIENT_DATA")

    def test_missing_optional_signals_do_not_invalidate_required_coverage(self) -> None:
        """Missing optional signals do not reduce required_signal_coverage."""
        item_req = DiagnosticEvidenceItem(
            source_layer="telemetry",
            signal_name="pack_voltage_v",
            observed_value=3.2,
            expected_value=3.7,
            provenance=SignalProvenance.MEASURED,
            status=EvidenceEvaluationStatus.SUPPORTING,
            weight=0.8,
            rationale="Voltage drop",
        )
        result = EvidenceScoringEngine.evaluate_evidence(
            evidence_items=[item_req],
            required_signals=["pack_voltage_v"],
            optional_signals=["avg_cell_temperature_c", "ocv_v"],
            total_possible_supporting_weight=1.0,
        )

        self.assertEqual(result.required_signal_coverage, 1.0)
        self.assertEqual(result.optional_signal_coverage, 0.0)
        # Moderate confidence when optional signals are absent but required is fully met
        self.assertAlmostEqual(result.evidence_score, 0.8)

    def test_score_and_coverage_invariants(self) -> None:
        """EvidenceScore and coverage fractions are strictly bounded within [0.0, 1.0]."""
        item_heavy_penalty = DiagnosticEvidenceItem(
            source_layer="validation",
            signal_name="sig_a",
            observed_value=1.0,
            expected_value=0.0,
            provenance=SignalProvenance.MEASURED,
            status=EvidenceEvaluationStatus.CONTRAINDICATING,
            weight=1.0,
            rationale="Severe penalty",
        )
        result = EvidenceScoringEngine.evaluate_evidence(
            evidence_items=[item_heavy_penalty],
            required_signals=["sig_a"],
            optional_signals=[],
            total_possible_supporting_weight=0.5,
        )
        self.assertGreaterEqual(result.evidence_score, 0.0)
        self.assertLessEqual(result.evidence_score, 1.0)
        self.assertGreaterEqual(result.required_signal_coverage, 0.0)
        self.assertLessEqual(result.required_signal_coverage, 1.0)


if __name__ == "__main__":
    unittest.main()
