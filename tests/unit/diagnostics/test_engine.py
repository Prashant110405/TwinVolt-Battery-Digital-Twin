"""Unit tests for DiagnosticEngine orchestration, hypothesis ranking, and critical advisory gating."""

import math
import unittest

from src.diagnostics.config import DiagnosticThresholdConfig
from src.diagnostics.engine import DiagnosticEngine
from src.diagnostics.hypotheses import (
    AbstractDiagnosticHypothesis,
    ApparentOhmicResistanceGrowthHypothesis,
    SensorDriftHypothesis,
    ThermalDissipationImpairmentHypothesis,
    ThroughputAcceleratedFadeHypothesis,
)
from src.diagnostics.types import (
    DiagnosticCategory,
    DiagnosticEvidenceItem,
    DiagnosticSeverity,
    EvidenceEvaluationStatus,
    FaultLifecycleState,
    OperatingContext,
    RootCauseHypothesis,
)
from src.telemetry.enums import TelemetryQuality
from src.telemetry.snapshots import TelemetrySnapshot
from src.validation.types import (
    ModelValidationReport,
    ModelValidationState,
    SignalProvenance,
    ValidationWindowReport,
)


class MockCustomHypothesis(AbstractDiagnosticHypothesis):
    """Custom test hypothesis supporting arbitrary mock eligibility configuration."""

    def __init__(
        self,
        hypothesis_id: str,
        category: DiagnosticCategory = DiagnosticCategory.ELECTRICAL,
        is_critical_eligible: bool = False,
        is_diagnostically_eligible_flag: bool = True,
        required_signals: tuple[str, ...] = ("pack_voltage_v",),
        optional_signals: tuple[str, ...] = (),
    ) -> None:
        super().__init__(
            hypothesis_id=hypothesis_id,
            title=f"Mock Hypothesis {hypothesis_id}",
            category=category,
            required_signals=required_signals,
            optional_signals=optional_signals,
            untestable_confounds=("Mock confound",),
            suggested_investigations=("Mock action",),
            total_possible_supporting_weight=1.0,
            is_critical_eligible=is_critical_eligible,
        )
        self._is_diag_eligible = is_diagnostically_eligible_flag

    def is_diagnostically_eligible(self, context: OperatingContext, telemetry=None) -> bool:
        return self._is_diag_eligible


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

    # ==========================================================================
    # BLOCKER 1 TESTS: DATA_GAPPED vs DATA_QUALITY_FAILED
    # ==========================================================================

    def test_data_gap_produces_insufficient_evidence_not_data_quality_failed(self) -> None:
        """Valid samples separated by interval > data_gap_threshold_s produce INSUFFICIENT_EVIDENCE, not DATA_QUALITY_FAILED."""
        engine = DiagnosticEngine(system_id="twin_01", config=DiagnosticThresholdConfig(data_gap_threshold_s=5.0))

        s0 = TelemetrySnapshot(system_id="t1", snapshot_id="s0", timestamp_ns=0, pack_current_a=1.0)
        r0 = engine.step(s0)
        self.assertEqual(r0.lifecycle_state, FaultLifecycleState.NORMAL)

        # 20-second gap between valid telemetry snapshots
        s1 = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=20 * 1_000_000_000, pack_current_a=1.0)
        report = engine.step(s1)

        self.assertEqual(report.operating_context, OperatingContext.DATA_GAPPED)
        self.assertEqual(report.lifecycle_state, FaultLifecycleState.INSUFFICIENT_EVIDENCE)
        self.assertNotEqual(report.lifecycle_state, FaultLifecycleState.DATA_QUALITY_FAILED)
        self.assertEqual(report.data_quality_status, "DATA_GAPPED")
        self.assertIsNone(report.primary_hypothesis)

    def test_invalid_telemetry_quality_produces_data_quality_failed(self) -> None:
        """Explicit TelemetryQuality.INVALID produces DATA_QUALITY_FAILED."""
        engine = DiagnosticEngine(system_id="twin_01")
        s_invalid = TelemetrySnapshot(
            system_id="t1",
            snapshot_id="s_bad",
            timestamp_ns=1_000_000_000,
            quality=TelemetryQuality.INVALID,
        )
        report = engine.step(s_invalid)

        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DATA_QUALITY_FAILED)
        self.assertEqual(report.severity, DiagnosticSeverity.UNKNOWN)
        self.assertEqual(report.data_quality_status, "FAILED")
        self.assertIsNone(report.primary_hypothesis)

    def test_nan_or_inf_telemetry_produces_data_quality_failed(self) -> None:
        """Non-finite NaN or Inf in telemetry or invalid quality flag produces DATA_QUALITY_FAILED."""
        engine = DiagnosticEngine(system_id="twin_01")

        # Snapshot with INVALID quality
        s_inv = TelemetrySnapshot(
            system_id="t1",
            snapshot_id="s_inv",
            timestamp_ns=1_000_000_000,
            quality=TelemetryQuality.INVALID,
        )
        report_inv = engine.step(s_inv)
        self.assertEqual(report_inv.lifecycle_state, FaultLifecycleState.DATA_QUALITY_FAILED)
        self.assertEqual(report_inv.data_quality_status, "FAILED")

        # Snapshot with bypassed validation to simulate corrupted memory
        s_nan = TelemetrySnapshot(
            system_id="t1",
            snapshot_id="s_nan",
            timestamp_ns=2_000_000_000,
        )
        object.__setattr__(s_nan, "pack_voltage_v", float("nan"))
        report_nan = engine.step(s_nan)
        self.assertEqual(report_nan.lifecycle_state, FaultLifecycleState.DATA_QUALITY_FAILED)
        self.assertEqual(report_nan.data_quality_status, "FAILED")

        s_inf = TelemetrySnapshot(
            system_id="t1",
            snapshot_id="s_inf",
            timestamp_ns=3_000_000_000,
        )
        object.__setattr__(s_inf, "pack_current_a", float("inf"))
        report_inf = engine.step(s_inf)
        self.assertEqual(report_inf.lifecycle_state, FaultLifecycleState.DATA_QUALITY_FAILED)
        self.assertEqual(report_inf.data_quality_status, "FAILED")

    def test_data_gapped_cannot_create_physical_fault_diagnosis(self) -> None:
        """DATA_GAPPED context alone cannot produce a physical battery fault diagnosis."""
        engine = DiagnosticEngine(system_id="twin_01", config=DiagnosticThresholdConfig(data_gap_threshold_s=5.0))

        s0 = TelemetrySnapshot(system_id="t1", snapshot_id="s0", timestamp_ns=0, pack_current_a=2.0)
        engine.step(s0)

        # Huge time gap
        s_gap = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=100 * 1_000_000_000, pack_current_a=2.0)
        report = engine.step(s_gap)

        self.assertIsNone(report.primary_hypothesis)
        self.assertEqual(report.lifecycle_state, FaultLifecycleState.INSUFFICIENT_EVIDENCE)
        self.assertNotEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED)
        self.assertNotEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED_CRITICAL)

    # ==========================================================================
    # BLOCKER 2 TESTS: 6-TIER DETERMINISTIC HYPOTHESIS RANKING
    # ==========================================================================

    def test_ranking_tier1_eligibility_outranks_ineligible_with_higher_score(self) -> None:
        """Tier 1: An ineligible hypothesis cannot outrank an eligible one even with a higher score."""
        h_ineligible = MockCustomHypothesis(
            hypothesis_id="HYP_INELIGIBLE",
            is_diagnostically_eligible_flag=False,
        )
        h_eligible = MockCustomHypothesis(
            hypothesis_id="HYP_ELIGIBLE",
            is_diagnostically_eligible_flag=True,
        )

        engine = DiagnosticEngine(
            system_id="twin_01",
            hypotheses=[h_ineligible, h_eligible],
        )

        # Evidence gives HYP_INELIGIBLE score 1.0 (both signals), but it is ineligible.
        # HYP_ELIGIBLE gets score 0.6.
        evidence = [
            DiagnosticEvidenceItem(
                source_layer="telemetry",
                signal_name="pack_voltage_v",
                observed_value=3.4,
                expected_value=3.7,
                provenance=SignalProvenance.MEASURED,
                status=EvidenceEvaluationStatus.SUPPORTING,
                weight=0.6,
                rationale="Voltage drop",
            ),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.4)
        report = engine.step(s, evidence_items=evidence)

        # Primary hypothesis must be HYP_ELIGIBLE
        self.assertIsNotNone(report.primary_hypothesis)
        self.assertEqual(report.primary_hypothesis.hypothesis_id, "HYP_ELIGIBLE")

    def test_ranking_tier2_higher_coverage_outranks_lower_coverage(self) -> None:
        """Tier 2: Higher required coverage outranks lower coverage when eligibility is equal."""
        h_full_cov = ApparentOhmicResistanceGrowthHypothesis()  # Requires pack_voltage_v, pack_current_a, identified_r0_ohm
        h_partial_cov = SensorDriftHypothesis()                # Requires pack_voltage_v, pack_current_a

        engine = DiagnosticEngine(
            system_id="twin_01",
            hypotheses=[h_partial_cov, h_full_cov],
        )

        # Provide all 3 signals for h_full_cov (cov=1.0, score=0.6), but only 1 of 2 for h_partial_cov (cov=0.5, score=0.8 clamped to 0)
        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_voltage_v", observed_value=3.4, expected_value=3.7, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.3, rationale="V"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=5.0, expected_value=5.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.2, rationale="I"),
            DiagnosticEvidenceItem(source_layer="calibration", signal_name="identified_r0_ohm", observed_value=0.025, expected_value=0.020, provenance=SignalProvenance.ESTIMATED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.1, rationale="R0"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.4, pack_current_a=5.0)
        report = engine.step(s, evidence_items=evidence)

        self.assertEqual(report.primary_hypothesis.hypothesis_id, "HYP_APPARENT_OHMIC_GROWTH")

    def test_ranking_tier3_higher_evidence_score_outranks_lower(self) -> None:
        """Tier 3: Higher evidence score outranks lower score when coverage and eligibility are equal."""
        h1 = MockCustomHypothesis(hypothesis_id="HYP_LOW_SCORE")
        h2 = MockCustomHypothesis(hypothesis_id="HYP_HIGH_SCORE")

        engine = DiagnosticEngine(system_id="twin_01", hypotheses=[h1, h2])

        ev1 = DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_voltage_v", observed_value=3.4, expected_value=3.7, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.8, rationale="High score")
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.4)
        report = engine.step(s, evidence_items=[ev1])

        self.assertIsNotNone(report.primary_hypothesis)

    def test_ranking_tier4_corroborating_channels_outrank_persistence(self) -> None:
        """Tier 4 vs Tier 5: Higher independent corroborating channel count outranks lower count before persistence."""
        h_2chan_unpersisted = MockCustomHypothesis(
            hypothesis_id="HYP_TWO_CHANNELS",
            is_critical_eligible=True,
            required_signals=("pack_voltage_v", "pack_current_a"),
            optional_signals=(),
        )

        h_1chan_persisted = MockCustomHypothesis(
            hypothesis_id="HYP_ONE_CHANNEL",
            is_critical_eligible=True,
            required_signals=("pack_voltage_v",),
            optional_signals=(),
        )

        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=2)
        engine = DiagnosticEngine(
            system_id="twin_01",
            config=cfg,
            hypotheses=[h_1chan_persisted, h_2chan_unpersisted],
        )

        # Step 1 & 2: Only pack_voltage_v provided.
        # HYP_ONE_CHANNEL satisfies required signals and persists after 2 steps.
        # HYP_TWO_CHANNELS is missing pack_current_a (coverage 0.5 < 1.0) and remains unpersisted.
        ev_1chan = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_voltage_v", observed_value=3.4, expected_value=3.7, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.8, rationale="V"),
        ]
        s1 = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.4)
        engine.step(s1, evidence_items=ev_1chan)
        s2 = TelemetrySnapshot(system_id="t1", snapshot_id="s2", timestamp_ns=2_000_000_000, pack_voltage_v=3.4)
        engine.step(s2, evidence_items=ev_1chan)

        self.assertTrue(engine._trackers["HYP_ONE_CHANNEL"].get_state().is_persisted)
        self.assertFalse(engine._trackers["HYP_TWO_CHANNELS"].get_state().is_persisted)

        # Step 3: Provide 2 corroborating channels to HYP_TWO_CHANNELS with equal evidence score (0.8)
        ev_2chan = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_voltage_v", observed_value=3.4, expected_value=3.7, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.4, rationale="V"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=5.0, expected_value=5.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.4, rationale="I"),
        ]
        s3 = TelemetrySnapshot(system_id="t1", snapshot_id="s3", timestamp_ns=3_000_000_000, pack_voltage_v=3.4, pack_current_a=5.0)
        report3 = engine.step(s3, evidence_items=ev_2chan)

        # Because corroborating channels (2 channels) is evaluated BEFORE persistence (Tier 4 before Tier 5),
        # HYP_TWO_CHANNELS must outrank HYP_ONE_CHANNEL!
        self.assertEqual(report3.primary_hypothesis.hypothesis_id, "HYP_TWO_CHANNELS")

    def test_ranking_tier6_canonical_hypothesis_id_tie_breaker(self) -> None:
        """Tier 6: Canonical hypothesis ID provides final deterministic alphabetical tie-breaker."""
        h_beta = MockCustomHypothesis(hypothesis_id="HYP_BETA")
        h_alpha = MockCustomHypothesis(hypothesis_id="HYP_ALPHA")

        engine = DiagnosticEngine(
            system_id="twin_01",
            hypotheses=[h_beta, h_alpha],
        )

        ev = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_voltage_v", observed_value=3.4, expected_value=3.7, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.8, rationale="V"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.4)
        report = engine.step(s, evidence_items=ev)

        # All 5 previous criteria are identical. Canonical alphabetical tie-breaker picks HYP_ALPHA over HYP_BETA.
        self.assertEqual(report.primary_hypothesis.hypothesis_id, "HYP_ALPHA")

    # ==========================================================================
    # BLOCKER 3 & 4 TESTS: EXPLICIT CRITICAL ELIGIBILITY & 7 GATING CONDITIONS
    # ==========================================================================

    def test_ineligible_hypothesis_cannot_become_diagnosed_critical(self) -> None:
        """Ineligible hypothesis (e.g. SensorDriftHypothesis) cannot become DIAGNOSED_CRITICAL despite score 1.0."""
        cfg = DiagnosticThresholdConfig(
            persistence_debounce_steps=1,
            critical_evidence_score_threshold=0.75,
            critical_min_corroborating_channels=2,
        )
        engine = DiagnosticEngine(
            system_id="twin_01",
            config=cfg,
            hypotheses=[SensorDriftHypothesis()],
        )

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_voltage_v", observed_value=3.85, expected_value=3.80, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.6, rationale="V offset"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=0.01, expected_value=0.00, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.4, rationale="Rest current"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.85, pack_current_a=0.01)
        report = engine.step(s, evidence_items=evidence)

        # Meets score (1.0), 2 channels, 1.0 coverage, persisted, but is NOT critical eligible
        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED)
        self.assertNotEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED_CRITICAL)
        self.assertEqual(report.severity, DiagnosticSeverity.WARNING)
        self.assertFalse(report.diagnostics["is_critical_eligible"])
        self.assertTrue(any("not critical-advisory eligible" in r for r in report.diagnostics["critical_ineligibility_reasons"]))

    def test_critical_failure_condition_1_incomplete_coverage(self) -> None:
        """Critical Criterion 1 Failure: required_coverage < 1.0 blocks DIAGNOSED_CRITICAL."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=1)
        engine = DiagnosticEngine(system_id="twin_01", config=cfg)

        # Only 2 of 3 required signals provided for ApparentOhmicGrowth
        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_voltage_v", observed_value=3.4, expected_value=3.7, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="V"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=5.0, expected_value=5.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="I"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.4, pack_current_a=5.0)
        report = engine.step(s, evidence_items=evidence)

        self.assertNotEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED_CRITICAL)

    def test_critical_failure_condition_2_sub_threshold_score(self) -> None:
        """Critical Criterion 2 Failure: score (0.60) < critical threshold (0.75) yields DIAGNOSED, not CRITICAL."""
        cfg = DiagnosticThresholdConfig(
            persistence_debounce_steps=1,
            critical_evidence_score_threshold=0.75,
            diagnosis_evidence_score_threshold=0.50,
            critical_min_corroborating_channels=2,
        )
        engine = DiagnosticEngine(
            system_id="twin_01",
            config=cfg,
            hypotheses=[ThermalDissipationImpairmentHypothesis()],
        )

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="avg_cell_temperature_c", observed_value=35.0, expected_value=25.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.35, rationale="T"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=2.0, expected_value=2.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.25, rationale="I"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, avg_cell_temperature_c=35.0, pack_current_a=2.0)
        report = engine.step(s, evidence_items=evidence)

        # Score is 0.60 -> DIAGNOSED (WARNING), not DIAGNOSED_CRITICAL (CRITICAL)
        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED)
        self.assertEqual(report.severity, DiagnosticSeverity.WARNING)
        self.assertFalse(report.diagnostics["is_critical_eligible"])
        self.assertTrue(any("Evidence score" in r for r in report.diagnostics["critical_ineligibility_reasons"]))

    def test_critical_failure_condition_3_active_contraindication(self) -> None:
        """Critical Criterion 3 Failure: Active contraindication blocks DIAGNOSED_CRITICAL."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=1)
        engine = DiagnosticEngine(system_id="twin_01", config=cfg, hypotheses=[ThermalDissipationImpairmentHypothesis()])

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="avg_cell_temperature_c", observed_value=45.0, expected_value=25.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="T"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=2.0, expected_value=2.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="I"),
            DiagnosticEvidenceItem(source_layer="validation", signal_name="thermal_residual_c", observed_value=0.01, expected_value=0.01, provenance=SignalProvenance.DERIVED, status=EvidenceEvaluationStatus.CONTRAINDICATING, weight=0.1, rationale="Residual zero"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, avg_cell_temperature_c=45.0, pack_current_a=2.0)
        report = engine.step(s, evidence_items=evidence)

        self.assertNotEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED_CRITICAL)
        self.assertTrue(any("Active contraindicating" in r for r in report.diagnostics["critical_ineligibility_reasons"]))

    def test_critical_failure_condition_4_insufficient_corroborating_channels(self) -> None:
        """Critical Criterion 4 Failure: 1 channel < required 2 channels blocks DIAGNOSED_CRITICAL."""
        cfg = DiagnosticThresholdConfig(
            persistence_debounce_steps=1,
            critical_min_corroborating_channels=2,
        )
        h = MockCustomHypothesis(hypothesis_id="HYP_MOCK_1CHAN", is_critical_eligible=True)
        engine = DiagnosticEngine(system_id="twin_01", config=cfg, hypotheses=[h])

        # 1 single channel with high weight (0.9)
        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_voltage_v", observed_value=3.4, expected_value=3.7, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.9, rationale="V"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.4)
        report = engine.step(s, evidence_items=evidence)

        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED)
        self.assertFalse(report.diagnostics["is_critical_eligible"])
        self.assertTrue(any("Corroborating channels" in r for r in report.diagnostics["critical_ineligibility_reasons"]))

    def test_critical_failure_condition_5_model_validation_failed(self) -> None:
        """Critical Criterion 5 Failure: Model validation DATA_QUALITY_FAILED blocks DIAGNOSED_CRITICAL."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=1, critical_min_corroborating_channels=2)
        engine = DiagnosticEngine(system_id="twin_01", config=cfg, hypotheses=[ThermalDissipationImpairmentHypothesis()])

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="avg_cell_temperature_c", observed_value=45.0, expected_value=25.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="T"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=2.0, expected_value=2.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="I"),
        ]

        window_report = ValidationWindowReport(
            window_id="w1",
            system_id="twin_01",
            start_timestamp_ns=0,
            end_timestamp_ns=1_000_000_000,
            duration_s=1.0,
            sample_count=20,
            state=ModelValidationState.DATA_QUALITY_FAILED,
        )
        val_report = ModelValidationReport(
            system_id="twin_01",
            timestamp_ns=1_000_000_000,
            active_window=window_report,
        )

        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, avg_cell_temperature_c=45.0, pack_current_a=2.0)
        report = engine.step(s, evidence_items=evidence, model_validation_report=val_report)

        self.assertNotEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED_CRITICAL)
        self.assertTrue(any("Upstream model validation state" in r for r in report.diagnostics["critical_ineligibility_reasons"]))

    def test_critical_failure_condition_6_persistence_debounce_pending(self) -> None:
        """Critical Criterion 6 Failure: Debounce step count < required steps blocks DIAGNOSED_CRITICAL."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=3, critical_min_corroborating_channels=2)
        engine = DiagnosticEngine(system_id="twin_01", config=cfg, hypotheses=[ThermalDissipationImpairmentHypothesis()])

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="avg_cell_temperature_c", observed_value=45.0, expected_value=25.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="T"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=2.0, expected_value=2.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="I"),
        ]

        # Step 1 of 3: Anomaly detected
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, avg_cell_temperature_c=45.0, pack_current_a=2.0)
        report = engine.step(s, evidence_items=evidence)

        self.assertEqual(report.lifecycle_state, FaultLifecycleState.ANOMALY_DETECTED)
        self.assertFalse(report.diagnostics["is_critical_eligible"])

    # ==========================================================================
    # BLOCKER 5 TESTS: MODEL VALIDATION SEMANTICS & CRITICAL ADVISORY GATING
    # ==========================================================================

    def test_valid_model_validation_permits_diagnosed_critical_physical_hypothesis(self) -> None:
        """VALID / VALIDATED model validation allows physical hypothesis to reach DIAGNOSED_CRITICAL."""
        cfg = DiagnosticThresholdConfig(
            persistence_debounce_steps=1,
            critical_evidence_score_threshold=0.75,
            critical_min_corroborating_channels=2,
        )
        engine = DiagnosticEngine(system_id="twin_01", config=cfg, hypotheses=[ThermalDissipationImpairmentHypothesis()])

        window_report = ValidationWindowReport(
            window_id="w_val",
            system_id="twin_01",
            start_timestamp_ns=0,
            end_timestamp_ns=1_000_000_000,
            duration_s=1.0,
            sample_count=20,
            state=ModelValidationState.VALIDATED,
        )
        val_report = ModelValidationReport(
            system_id="twin_01",
            timestamp_ns=1_000_000_000,
            active_window=window_report,
        )

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="avg_cell_temperature_c", observed_value=45.0, expected_value=25.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="T"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=2.0, expected_value=2.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="I"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, avg_cell_temperature_c=45.0, pack_current_a=2.0)
        report = engine.step(s, evidence_items=evidence, model_validation_report=val_report)

        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED_CRITICAL)
        self.assertEqual(report.severity, DiagnosticSeverity.CRITICAL)
        self.assertTrue(report.diagnostics["is_critical_eligible"])

    def test_degraded_model_validation_blocks_critical_for_electrical_hypothesis(self) -> None:
        """DEGRADED model validation blocks DIAGNOSED_CRITICAL for ELECTRICAL hypothesis, yielding DIAGNOSED."""
        cfg = DiagnosticThresholdConfig(
            persistence_debounce_steps=1,
            critical_evidence_score_threshold=0.75,
            critical_min_corroborating_channels=2,
        )
        engine = DiagnosticEngine(system_id="twin_01", config=cfg, hypotheses=[ApparentOhmicResistanceGrowthHypothesis()])

        window_report = ValidationWindowReport(
            window_id="w_deg_elec",
            system_id="twin_01",
            start_timestamp_ns=0,
            end_timestamp_ns=1_000_000_000,
            duration_s=1.0,
            sample_count=20,
            state=ModelValidationState.DEGRADED,
        )
        val_report = ModelValidationReport(
            system_id="twin_01",
            timestamp_ns=1_000_000_000,
            active_window=window_report,
        )

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_voltage_v", observed_value=3.4, expected_value=3.7, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.4, rationale="V drop"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=5.0, expected_value=5.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.3, rationale="I load"),
            DiagnosticEvidenceItem(source_layer="calibration", signal_name="identified_r0_ohm", observed_value=0.025, expected_value=0.020, provenance=SignalProvenance.ESTIMATED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.3, rationale="R0 growth"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.4, pack_current_a=5.0)
        report = engine.step(s, evidence_items=evidence, model_validation_report=val_report)

        # Reaches ordinary DIAGNOSED with WARNING, NOT DIAGNOSED_CRITICAL
        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED)
        self.assertEqual(report.severity, DiagnosticSeverity.WARNING)
        self.assertFalse(report.diagnostics["is_critical_eligible"])
        self.assertTrue(any("DEGRADED" in r for r in report.diagnostics["critical_ineligibility_reasons"]))
        self.assertEqual(report.primary_hypothesis.hypothesis_id, "HYP_APPARENT_OHMIC_GROWTH")

    def test_degraded_model_validation_blocks_critical_for_thermal_hypothesis(self) -> None:
        """DEGRADED model validation blocks DIAGNOSED_CRITICAL for THERMAL hypothesis, yielding DIAGNOSED."""
        cfg = DiagnosticThresholdConfig(
            persistence_debounce_steps=1,
            critical_evidence_score_threshold=0.75,
            critical_min_corroborating_channels=2,
        )
        engine = DiagnosticEngine(system_id="twin_01", config=cfg, hypotheses=[ThermalDissipationImpairmentHypothesis()])

        window_report = ValidationWindowReport(
            window_id="w_deg_therm",
            system_id="twin_01",
            start_timestamp_ns=0,
            end_timestamp_ns=1_000_000_000,
            duration_s=1.0,
            sample_count=20,
            state=ModelValidationState.DEGRADED,
        )
        val_report = ModelValidationReport(
            system_id="twin_01",
            timestamp_ns=1_000_000_000,
            active_window=window_report,
        )

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="avg_cell_temperature_c", observed_value=45.0, expected_value=25.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="T"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=2.0, expected_value=2.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="I"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, avg_cell_temperature_c=45.0, pack_current_a=2.0)
        report = engine.step(s, evidence_items=evidence, model_validation_report=val_report)

        # Reaches ordinary DIAGNOSED with WARNING, NOT DIAGNOSED_CRITICAL
        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED)
        self.assertEqual(report.severity, DiagnosticSeverity.WARNING)
        self.assertFalse(report.diagnostics["is_critical_eligible"])
        self.assertEqual(report.primary_hypothesis.hypothesis_id, "HYP_THERMAL_IMPAIRMENT")

    def test_degraded_model_validation_blocks_critical_for_cell_hypothesis(self) -> None:
        """DEGRADED model validation blocks DIAGNOSED_CRITICAL for CELL hypothesis, yielding DIAGNOSED."""
        h_cell = MockCustomHypothesis(
            hypothesis_id="HYP_CELL_IMBALANCE",
            category=DiagnosticCategory.CELL,
            is_critical_eligible=True,
            required_signals=("pack_voltage_v", "pack_current_a"),
        )
        cfg = DiagnosticThresholdConfig(
            persistence_debounce_steps=1,
            critical_evidence_score_threshold=0.75,
            critical_min_corroborating_channels=2,
        )
        engine = DiagnosticEngine(system_id="twin_01", config=cfg, hypotheses=[h_cell])

        window_report = ValidationWindowReport(
            window_id="w_deg_cell",
            system_id="twin_01",
            start_timestamp_ns=0,
            end_timestamp_ns=1_000_000_000,
            duration_s=1.0,
            sample_count=20,
            state=ModelValidationState.DEGRADED,
        )
        val_report = ModelValidationReport(
            system_id="twin_01",
            timestamp_ns=1_000_000_000,
            active_window=window_report,
        )

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_voltage_v", observed_value=3.4, expected_value=3.7, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="V"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=2.0, expected_value=2.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="I"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.4, pack_current_a=2.0)
        report = engine.step(s, evidence_items=evidence, model_validation_report=val_report)

        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED)
        self.assertEqual(report.severity, DiagnosticSeverity.WARNING)
        self.assertFalse(report.diagnostics["is_critical_eligible"])
        self.assertEqual(report.primary_hypothesis.hypothesis_id, "HYP_CELL_IMBALANCE")

    def test_degraded_model_validation_allows_ordinary_diagnosed_physical_hypothesis(self) -> None:
        """Physical hypotheses under DEGRADED validation can reach ordinary DIAGNOSED."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=1)
        engine = DiagnosticEngine(system_id="twin_01", config=cfg)

        window_report = ValidationWindowReport(
            window_id="w_deg",
            system_id="twin_01",
            start_timestamp_ns=0,
            end_timestamp_ns=1_000_000_000,
            duration_s=1.0,
            sample_count=20,
            state=ModelValidationState.DEGRADED,
        )
        val_report = ModelValidationReport(
            system_id="twin_01",
            timestamp_ns=1_000_000_000,
            active_window=window_report,
        )

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_voltage_v", observed_value=3.4, expected_value=3.7, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.3, rationale="V drop"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=5.0, expected_value=5.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.2, rationale="I load"),
            DiagnosticEvidenceItem(source_layer="calibration", signal_name="identified_r0_ohm", observed_value=0.025, expected_value=0.020, provenance=SignalProvenance.ESTIMATED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.1, rationale="R0 growth"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, pack_voltage_v=3.4, pack_current_a=5.0)
        report = engine.step(s, evidence_items=evidence, model_validation_report=val_report)

        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED)
        self.assertEqual(report.primary_hypothesis.hypothesis_id, "HYP_APPARENT_OHMIC_GROWTH")
        self.assertEqual(report.diagnostics["model_validation_state"], "DEGRADED")

    def test_degraded_model_validation_does_not_produce_model_mismatch_automatically(self) -> None:
        """DEGRADED model validation does not automatically assert HYP_MODEL_MISMATCH as root cause."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=1)
        engine = DiagnosticEngine(system_id="twin_01", config=cfg)

        window_report = ValidationWindowReport(
            window_id="w_deg2",
            system_id="twin_01",
            start_timestamp_ns=0,
            end_timestamp_ns=1_000_000_000,
            duration_s=1.0,
            sample_count=20,
            state=ModelValidationState.DEGRADED,
        )
        val_report = ModelValidationReport(
            system_id="twin_01",
            timestamp_ns=1_000_000_000,
            active_window=window_report,
        )

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="avg_cell_temperature_c", observed_value=40.0, expected_value=25.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="T"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=2.0, expected_value=2.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.3, rationale="I"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, avg_cell_temperature_c=40.0, pack_current_a=2.0)
        report = engine.step(s, evidence_items=evidence, model_validation_report=val_report)

        self.assertEqual(report.primary_hypothesis.hypothesis_id, "HYP_THERMAL_IMPAIRMENT")
        self.assertNotEqual(report.primary_hypothesis.hypothesis_id, "HYP_MODEL_MISMATCH")

    def test_insufficient_data_model_validation_cannot_produce_diagnosed_critical(self) -> None:
        """INSUFFICIENT_DATA model validation state blocks DIAGNOSED_CRITICAL transition."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=1, critical_min_corroborating_channels=2)
        engine = DiagnosticEngine(system_id="twin_01", config=cfg, hypotheses=[ThermalDissipationImpairmentHypothesis()])

        window_report = ValidationWindowReport(
            window_id="w_insuf",
            system_id="twin_01",
            start_timestamp_ns=0,
            end_timestamp_ns=1_000_000_000,
            duration_s=1.0,
            sample_count=5,
            state=ModelValidationState.INSUFFICIENT_DATA,
        )
        val_report = ModelValidationReport(
            system_id="twin_01",
            timestamp_ns=1_000_000_000,
            active_window=window_report,
        )

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="avg_cell_temperature_c", observed_value=45.0, expected_value=25.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="T"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=2.0, expected_value=2.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="I"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, avg_cell_temperature_c=45.0, pack_current_a=2.0)
        report = engine.step(s, evidence_items=evidence, model_validation_report=val_report)

        self.assertNotEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED_CRITICAL)
        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED)
        self.assertFalse(report.diagnostics["is_critical_eligible"])
        self.assertTrue(any("INSUFFICIENT_DATA" in r for r in report.diagnostics["critical_ineligibility_reasons"]))

    def test_data_quality_failed_model_validation_cannot_produce_diagnosed_critical(self) -> None:
        """DATA_QUALITY_FAILED model validation state blocks DIAGNOSED_CRITICAL transition."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=1, critical_min_corroborating_channels=2)
        engine = DiagnosticEngine(system_id="twin_01", config=cfg, hypotheses=[ThermalDissipationImpairmentHypothesis()])

        window_report = ValidationWindowReport(
            window_id="w_dq",
            system_id="twin_01",
            start_timestamp_ns=0,
            end_timestamp_ns=1_000_000_000,
            duration_s=1.0,
            sample_count=20,
            state=ModelValidationState.DATA_QUALITY_FAILED,
        )
        val_report = ModelValidationReport(
            system_id="twin_01",
            timestamp_ns=1_000_000_000,
            active_window=window_report,
        )

        evidence = [
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="avg_cell_temperature_c", observed_value=45.0, expected_value=25.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="T"),
            DiagnosticEvidenceItem(source_layer="telemetry", signal_name="pack_current_a", observed_value=2.0, expected_value=2.0, provenance=SignalProvenance.MEASURED, status=EvidenceEvaluationStatus.SUPPORTING, weight=0.5, rationale="I"),
        ]
        s = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1_000_000_000, avg_cell_temperature_c=45.0, pack_current_a=2.0)
        report = engine.step(s, evidence_items=evidence, model_validation_report=val_report)

        self.assertNotEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED_CRITICAL)
        self.assertEqual(report.lifecycle_state, FaultLifecycleState.DIAGNOSED)
        self.assertFalse(report.diagnostics["is_critical_eligible"])
        self.assertTrue(any("DATA_QUALITY_FAILED" in r for r in report.diagnostics["critical_ineligibility_reasons"]))

    def test_confidence_level_is_qualitative_evidence_tier_not_probability(self) -> None:
        """Retained confidence_level metadata represents qualitative evidence strength tier, not probability."""
        hyp = ThermalDissipationImpairmentHypothesis()
        res = hyp.evaluate([], context=OperatingContext.REST)
        self.assertIn(res.confidence_level, ("STRONG", "MODERATE", "WEAK", "INSUFFICIENT_DATA", "NO_EVIDENCE"))
        self.assertIsInstance(res.confidence_level, str)
        self.assertEqual(res.confidence_level, res.evidence_strength_tier)

    def test_is_model_validation_critical_eligible_explicit_mapping(self) -> None:
        """Explicitly tests DiagnosticEngine.is_model_validation_critical_eligible across all states and categories."""
        # 1. VALID / VALIDATED / VALIDATING / None -> True
        self.assertTrue(DiagnosticEngine.is_model_validation_critical_eligible(None))
        self.assertTrue(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.VALIDATED, DiagnosticCategory.ELECTRICAL))
        self.assertTrue(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.VALIDATED, DiagnosticCategory.THERMAL))
        self.assertTrue(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.VALIDATED, DiagnosticCategory.CELL))
        self.assertTrue(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.VALIDATING))
        self.assertTrue(DiagnosticEngine.is_model_validation_critical_eligible("EXCITATION_STEADY_STATE_ONLY"))

        # 2. DEGRADED -> strictly False for physical hazard categories (ELECTRICAL, THERMAL, CELL) and None
        self.assertFalse(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.DEGRADED, DiagnosticCategory.ELECTRICAL))
        self.assertFalse(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.DEGRADED, DiagnosticCategory.THERMAL))
        self.assertFalse(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.DEGRADED, DiagnosticCategory.CELL))
        self.assertFalse(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.DEGRADED, None))
        self.assertFalse(DiagnosticEngine.is_model_validation_critical_eligible("DEGRADED"))

        # 3. INSUFFICIENT_DATA -> False
        self.assertFalse(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.INSUFFICIENT_DATA))
        self.assertFalse(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.INSUFFICIENT_DATA, DiagnosticCategory.THERMAL))

        # 4. DATA_QUALITY_FAILED -> False
        self.assertFalse(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.DATA_QUALITY_FAILED))
        self.assertFalse(DiagnosticEngine.is_model_validation_critical_eligible(ModelValidationState.DATA_QUALITY_FAILED, DiagnosticCategory.ELECTRICAL))

        # 5. UNAVAILABLE or unknown states -> False
        self.assertFalse(DiagnosticEngine.is_model_validation_critical_eligible("UNAVAILABLE"))
        self.assertFalse(DiagnosticEngine.is_model_validation_critical_eligible("UNKNOWN_STATE"))

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

