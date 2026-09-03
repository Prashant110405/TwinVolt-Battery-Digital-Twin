"""Unit tests for DiagnosticEngine orchestration, hypothesis ranking, and critical advisory gating."""

import unittest

from src.diagnostics.config import DiagnosticThresholdConfig
from src.diagnostics.engine import DiagnosticEngine
from src.diagnostics.types import (
    DiagnosticCategory,
    DiagnosticEvidenceItem,
    DiagnosticSeverity,
    EvidenceEvaluationStatus,
    FaultLifecycleState,
    OperatingContext,
)
from src.telemetry.snapshots import TelemetrySnapshot
from src.validation.types import ModelValidationReport, ModelValidationState, SignalProvenance


class TestDiagnosticEngine(unittest.TestCase):
    """Test suite verifying diagnostic orchestration, persistence, ranking, and critical advisory evaluation."""

    def test_normal_telemetry_produces_normal_lifecycle(self) -> None:
        """Nominal resting telemetry with zero anomalies produces NORMAL assessment."""
        engine = DiagnosticEngine(system_id="twin_01")
        snap = TelemetrySnapshot(
            system_id="twin_01",
            snapshot_id="snap_01",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=3.8,
            pack_current_a=0.01,
        )

        report = engine.step(snap, evidence_items=())
        self.assertEqual(report.lifecycle_state, FaultLifecycleState.NORMAL)
        self.assertEqual(report.severity, DiagnosticSeverity.INFORMATIONAL)
        self.assertIsNone(report.primary_hypothesis)
        self.assertEqual(report.operating_context, OperatingContext.REST)

    def test_anomaly_to_diagnosed_lifecycle_progression(self) -> None:
        """Sustained supporting evidence progresses from ANOMALY_DETECTED to SUSPECTED to DIAGNOSED."""
        cfg = DiagnosticThresholdConfig(
            persistence_debounce_steps=3,
            recovery_hysteresis_steps=5,
            diagnosis_evidence_score_threshold=0.50,
        )
        engine = DiagnosticEngine(system_id="twin_01", config=cfg)

        evidence = [
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="pack_voltage_v",
                observed_value=3.4,
                expected_value=3.7,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.3,
                rationale="IR drop",
            ),
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="pack_current_a",
                observed_value=5.0,
                expected_value=5.0,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.2,
                rationale="Discharge load",
            ),
            DiagnosticEvidenceItem(
                source_layer="calibration",
                signal_name="identified_r0_ohm",
                observed_value=0.025,
                expected_value=0.020,
                provenance=SignalProvenance.ESTIMATED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.1,
                rationale="RLS R0 shift",
            ),
        ]

        # Step 1: Anomaly detected (persistence count = 1 < 3)
        s1 = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.4, pack_current_a=5.0)
        r1 = engine.step(s1, evidence_items=evidence)
        self.assertEqual(r1.lifecycle_state, FaultLifecycleState.ANOMALY_DETECTED)
        self.assertEqual(r1.severity, DiagnosticSeverity.INFORMATIONAL)

        # Step 2: Still anomaly detected (persistence count = 2 < 3)
        s2 = TelemetrySnapshot(system_id="t1", snapshot_id="s2", timestamp_ns=2_000_000_000, pack_voltage_v=3.4, pack_current_a=5.0)
        r2 = engine.step(s2, evidence_items=evidence)
        self.assertEqual(r2.lifecycle_state, FaultLifecycleState.ANOMALY_DETECTED)

        # Step 3: Hits debounce threshold (3 steps) with score = 0.60 -> transitions to DIAGNOSED
        s3 = TelemetrySnapshot(system_id="t1", snapshot_id="s3", timestamp_ns=3_000_000_000, pack_voltage_v=3.4, pack_current_a=5.0)
        r3 = engine.step(s3, evidence_items=evidence)
        self.assertEqual(r3.lifecycle_state, FaultLifecycleState.DIAGNOSED)
        self.assertEqual(r3.severity, DiagnosticSeverity.WARNING)
        self.assertIsNotNone(r3.primary_hypothesis)
        self.assertEqual(r3.primary_hypothesis.hypothesis_id, "HYP_APPARENT_OHMIC_GROWTH")

    def test_critical_advisory_all_seven_conditions(self) -> None:
        """DIAGNOSED_CRITICAL is reached when all 7 critical advisory criteria are satisfied."""
        cfg = DiagnosticThresholdConfig(
            persistence_debounce_steps=2,
            critical_evidence_score_threshold=0.75,
            critical_min_corroborating_channels=2,
        )
        engine = DiagnosticEngine(system_id="twin_01", config=cfg)

        evidence = [
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="avg_cell_temperature_c",
                observed_value=45.0,
                expected_value=25.0,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.5,
                rationale="Elevated cell temp",
            ),
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="pack_current_a",
                observed_value=2.0,
                expected_value=2.0,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.5,
                rationale="Active current",
            ),
        ]

        from src.validation.types import ValidationWindowReport
        window_report = ValidationWindowReport(
            window_id="w1",
            system_id="twin_01",
            start_timestamp_ns=0,
            end_timestamp_ns=2_000_000_000,
            duration_s=2.0,
            sample_count=50,
            state=ModelValidationState.VALIDATED,
        )
        val_report = ModelValidationReport(
            system_id="twin_01",
            timestamp_ns=2_000_000_000,
            active_window=window_report,
        )

        # Step 1
        s1 = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_current_a=2.0, avg_cell_temperature_c=45.0)
        engine.step(s1, evidence_items=evidence, model_validation_report=val_report)

        # Step 2: Hits debounce threshold with score = 1.0 >= 0.75, 2 channels, no contraindications
        s2 = TelemetrySnapshot(system_id="t1", snapshot_id="s2", timestamp_ns=2_000_000_000, pack_current_a=2.0, avg_cell_temperature_c=45.0)
        r2 = engine.step(s2, evidence_items=evidence, model_validation_report=val_report)

        self.assertEqual(r2.lifecycle_state, FaultLifecycleState.DIAGNOSED_CRITICAL)
        self.assertEqual(r2.severity, DiagnosticSeverity.CRITICAL)
        self.assertTrue(r2.diagnostics["is_critical_eligible"])
        self.assertIn("CRITICAL ADVISORY NOTICE", r2.explanation_narrative)

    def test_critical_ineligibility_with_contraindication(self) -> None:
        """Active contraindication prevents DIAGNOSED_CRITICAL transition."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=1)
        engine = DiagnosticEngine(system_id="twin_01", config=cfg)

        evidence = [
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="avg_cell_temperature_c",
                observed_value=45.0,
                expected_value=25.0,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.6,
                rationale="Elevated temp",
            ),
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="pack_current_a",
                observed_value=2.0,
                expected_value=2.0,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.4,
                rationale="Active load",
            ),
            DiagnosticEvidenceItem(
                source_layer="validation",
                signal_name="thermal_residual_c",
                observed_value=0.1,
                expected_value=0.1,
                provenance=SignalProvenance.DERIVED,
                status=EvidenceEvaluationStatus.CONTRAINDICATING,
                weight=0.2,
                rationale="Thermal residual is minimal",
            ),
        ]

        s1 = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_current_a=2.0, avg_cell_temperature_c=45.0)
        report = engine.step(s1, evidence_items=evidence)

        # Blocked from CRITICAL due to active contraindication
        self.assertNotEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED_CRITICAL)
        self.assertFalse(report.diagnostics["is_critical_eligible"])
        self.assertIn("Active contraindicating evidence present", report.diagnostics["critical_ineligibility_reasons"])

    def test_data_gap_transitions_to_data_quality_failed(self) -> None:
        """Telemetry gap > 5s transitions engine to DATA_QUALITY_FAILED without physical fault diagnosis."""
        engine = DiagnosticEngine(system_id="twin_01", config=DiagnosticThresholdConfig(data_gap_threshold_s=5.0))

        s0 = TelemetrySnapshot(system_id="t1", snapshot_id="s0", timestamp_ns=0, pack_current_a=1.0)
        engine.step(s0)

        # 20 second gap
        s1 = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=20 * 1_000_000_000, pack_current_a=1.0)
        report = engine.step(s1)

        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DATA_QUALITY_FAILED)
        self.assertEqual(report.severity, DiagnosticSeverity.UNKNOWN)
        self.assertIsNone(report.primary_hypothesis)

    def test_reset_clears_all_engine_state(self) -> None:
        """Reset clears all hypothesis persistence trackers, lifecycle state, and cached assessments."""
        engine = DiagnosticEngine(system_id="twin_01")
        s0 = TelemetrySnapshot(system_id="t1", snapshot_id="s0", timestamp_ns=1000, pack_current_a=5.0)
        engine.step(s0)

        engine.reset()
        self.assertIsNone(engine.latest_assessment)
        self.assertEqual(engine.lifecycle_tracker.current_state, FaultLifecycleState.NORMAL)
        self.assertEqual(len(engine.lifecycle_tracker.transitions), 0)


if __name__ == "__main__":
    unittest.main()
