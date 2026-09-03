"""Unit tests for standard diagnostic root-cause hypotheses and rule evaluation."""

import unittest

from src.diagnostics.config import DiagnosticThresholdConfig
from src.diagnostics.hypotheses import (
    ApparentOhmicResistanceGrowthHypothesis,
    CellDispersionImbalanceHypothesis,
    ModelFidelityMismatchHypothesis,
    SensorDriftHypothesis,
    ThermalDissipationImpairmentHypothesis,
    ThroughputAcceleratedFadeHypothesis,
    create_standard_hypotheses,
)
from src.diagnostics.types import (
    DiagnosticCategory,
    DiagnosticEvidenceItem,
    EvidenceEvaluationStatus,
    OperatingContext,
)
from src.validation.types import SignalProvenance


class TestDiagnosticHypotheses(unittest.TestCase):
    """Test suite verifying hypothesis contracts, signal requirements, and evidence evaluation."""

    def test_standard_hypothesis_catalog_instantiation(self) -> None:
        """Standard hypothesis catalog creates all 6 orthogonal diagnostic categories."""
        catalog = create_standard_hypotheses()
        self.assertEqual(len(catalog), 6)

        categories = {h.category for h in catalog}
        self.assertEqual(
            categories,
            {
                DiagnosticCategory.SENSOR,
                DiagnosticCategory.MODEL,
                DiagnosticCategory.ELECTRICAL,
                DiagnosticCategory.THERMAL,
                DiagnosticCategory.CELL,
                DiagnosticCategory.DEGRADATION,
            },
        )

        for h in catalog:
            self.assertTrue(len(h.hypothesis_id) > 0)
            self.assertTrue(len(h.title) > 0)
            self.assertTrue(len(h.required_signals) > 0)
            self.assertTrue(len(h.untestable_confounds) > 0)
            self.assertTrue(len(h.suggested_investigations) > 0)

    def test_sensor_drift_hypothesis_evaluation(self) -> None:
        """SensorDriftHypothesis evaluates DC voltage residual in REST context."""
        hyp = SensorDriftHypothesis()
        items = [
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="pack_voltage_v",
                observed_value=3.85,
                expected_value=3.80,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.6,
                rationale="Persistent resting offset",
            ),
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="pack_current_a",
                observed_value=0.01,
                expected_value=0.00,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.4,
                rationale="Confirmed quiescent current",
            ),
        ]

        result = hyp.evaluate(items, context=OperatingContext.REST)
        self.assertEqual(result.hypothesis_id, "HYP_SENSOR_DRIFT")
        self.assertEqual(result.category, DiagnosticCategory.SENSOR)
        self.assertAlmostEqual(result.evidence_score, 1.0)
        self.assertEqual(result.confidence_level, "STRONG")
        self.assertEqual(result.required_signal_coverage, 1.0)

    def test_missing_required_signal_yields_insufficient_data(self) -> None:
        """Missing required signal clamps score to 0.0 and sets INSUFFICIENT_DATA."""
        hyp = SensorDriftHypothesis()
        # Only voltage provided, pack_current_a missing
        items = [
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="pack_voltage_v",
                observed_value=3.85,
                expected_value=3.80,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.8,
                rationale="Voltage offset",
            )
        ]

        result = hyp.evaluate(items, context=OperatingContext.REST)
        self.assertEqual(result.required_signal_coverage, 0.5)
        self.assertEqual(result.evidence_score, 0.0)
        self.assertEqual(result.confidence_level, "INSUFFICIENT_DATA")

    def test_cell_imbalance_unavailable_on_uninstrumented_pack(self) -> None:
        """CellDispersionImbalanceHypothesis evaluates as INSUFFICIENT_DATA when cell voltages are missing."""
        hyp = CellDispersionImbalanceHypothesis()
        items = [
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="cell_voltages_v",
                observed_value=None,
                expected_value=None,
                provenance=SignalProvenance.MISSING,
                status=EvidenceEvaluationStatus.UNAVAILABLE,
                weight=0.0,
                rationale="Monolithic pack without per-cell instrumentation",
            )
        ]

        result = hyp.evaluate(items, context=OperatingContext.REST)
        self.assertEqual(result.required_signal_coverage, 0.0)
        self.assertEqual(result.confidence_level, "INSUFFICIENT_DATA")

    def test_apparent_ohmic_growth_evaluation(self) -> None:
        """ApparentOhmicResistanceGrowthHypothesis evaluates R0 drift and voltage drop."""
        hyp = ApparentOhmicResistanceGrowthHypothesis()
        items = [
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="pack_voltage_v",
                observed_value=3.4,
                expected_value=3.7,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.4,
                rationale="Terminal IR drop under load",
            ),
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="pack_current_a",
                observed_value=5.0,
                expected_value=5.0,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.3,
                rationale="Active current step",
            ),
            DiagnosticEvidenceItem(
                source_layer="calibration",
                signal_name="identified_r0_ohm",
                observed_value=0.025,
                expected_value=0.020,
                provenance=SignalProvenance.ESTIMATED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.3,
                rationale="RLS R0 shifted by 25%",
            ),
        ]

        result = hyp.evaluate(items, context=OperatingContext.DISCHARGE_CC)
        self.assertEqual(result.category, DiagnosticCategory.ELECTRICAL)
        self.assertAlmostEqual(result.evidence_score, 1.0)
        self.assertEqual(result.confidence_level, "STRONG")

    def test_deterministic_repeated_evaluation(self) -> None:
        """Hypothesis evaluation is strictly deterministic for identical inputs."""
        hyp = ModelFidelityMismatchHypothesis()
        items = [
            DiagnosticEvidenceItem(
                source_layer="validation",
                signal_name="voltage_residual_v",
                observed_value=0.045,
                expected_value=0.010,
                provenance=SignalProvenance.DERIVED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.5,
                rationale="Voltage RMSE exceeds threshold",
            ),
            DiagnosticEvidenceItem(
                source_layer="validation",
                signal_name="model_validation_state",
                observed_value="DEGRADED",
                expected_value="VALIDATED",
                provenance=SignalProvenance.DERIVED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.5,
                rationale="Model validation state is degraded",
            ),
        ]

        res1 = hyp.evaluate(items, context=OperatingContext.DYNAMIC_TRANSIENT)
        res2 = hyp.evaluate(items, context=OperatingContext.DYNAMIC_TRANSIENT)

        self.assertEqual(res1.to_dict(), res2.to_dict())


if __name__ == "__main__":
    unittest.main()
