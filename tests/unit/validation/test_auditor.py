"""Unit tests for SignalAlignmentAuditor and telemetry continuity checks."""

import unittest

from src.telemetry.enums import TelemetryQuality
from src.telemetry.snapshots import TelemetrySnapshot
from src.validation.auditor import SignalAlignmentAuditor
from src.validation.types import ValidationConfig


class TestSignalAlignmentAuditor(unittest.TestCase):
    """Test suite verifying timestamp monotonicity, gap detection, and sensor quality auditing."""

    def test_monotonic_timestamps_valid_step(self) -> None:
        """Sequential strictly increasing timestamps produce valid audit results."""
        auditor = SignalAlignmentAuditor()
        for i in range(5):
            snap = TelemetrySnapshot(
                system_id="twin_01",
                snapshot_id=f"snap_{i}",
                timestamp_ns=(i + 1) * 1_000_000_000,
                pack_current_a=2.0,
                pack_voltage_v=3.8,
            )
            audit = auditor.audit_step(snap)
            self.assertTrue(audit.is_valid_step)
            self.assertFalse(audit.is_gap)
            self.assertFalse(audit.is_duplicate_timestamp)
            self.assertFalse(audit.is_retrograde_timestamp)
            self.assertEqual(len(audit.data_quality_flags), 0)

    def test_duplicate_timestamp_rejection(self) -> None:
        """Identical timestamp to previous step is rejected as DUPLICATE_TIMESTAMP."""
        auditor = SignalAlignmentAuditor()
        s0 = TelemetrySnapshot(system_id="t1", snapshot_id="s0", timestamp_ns=1000, pack_current_a=1.0, pack_voltage_v=3.6)
        s1 = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=1000, pack_current_a=1.0, pack_voltage_v=3.6)

        auditor.audit_step(s0)
        res = auditor.audit_step(s1)

        self.assertFalse(res.is_valid_step)
        self.assertTrue(res.is_duplicate_timestamp)
        self.assertIn("DUPLICATE_TIMESTAMP", res.data_quality_flags)

    def test_retrograde_timestamp_rejection(self) -> None:
        """Backward timestamp is rejected as RETROGRADE_TIMESTAMP."""
        auditor = SignalAlignmentAuditor()
        s0 = TelemetrySnapshot(system_id="t1", snapshot_id="s0", timestamp_ns=5000, pack_current_a=1.0, pack_voltage_v=3.6)
        s1 = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=2000, pack_current_a=1.0, pack_voltage_v=3.6)

        auditor.audit_step(s0)
        res = auditor.audit_step(s1)

        self.assertFalse(res.is_valid_step)
        self.assertTrue(res.is_retrograde_timestamp)
        self.assertIn("RETROGRADE_TIMESTAMP", res.data_quality_flags)

    def test_telemetry_gap_detection(self) -> None:
        """Step interval exceeding max_dt_s triggers gap detection."""
        auditor = SignalAlignmentAuditor(config=ValidationConfig(max_dt_s=5.0))
        s0 = TelemetrySnapshot(system_id="t1", snapshot_id="s0", timestamp_ns=0, pack_current_a=1.0, pack_voltage_v=3.6)
        s1 = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=10 * 1_000_000_000, pack_current_a=1.0, pack_voltage_v=3.6)

        auditor.audit_step(s0)
        res = auditor.audit_step(s1)

        self.assertTrue(res.is_gap)
        self.assertIn("TELEMETRY_GAP", res.data_quality_flags)

    def test_missing_voltage_or_current(self) -> None:
        """Missing essential electrical signals marks step as invalid with diagnostic flags."""
        auditor = SignalAlignmentAuditor()
        s_no_v = TelemetrySnapshot(system_id="t1", snapshot_id="s0", timestamp_ns=1000, pack_current_a=1.0, pack_voltage_v=None)
        res_v = auditor.audit_step(s_no_v)
        self.assertFalse(res_v.is_valid_step)
        self.assertIn("MISSING_VOLTAGE", res_v.data_quality_flags)

        auditor.reset()
        s_no_i = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=2000, pack_current_a=None, pack_voltage_v=3.6)
        res_i = auditor.audit_step(s_no_i)
        self.assertFalse(res_i.is_valid_step)
        self.assertIn("MISSING_CURRENT", res_i.data_quality_flags)

    def test_invalid_telemetry_quality(self) -> None:
        """Snapshot flagged as INVALID quality marks audit step as invalid."""
        auditor = SignalAlignmentAuditor()
        s_bad = TelemetrySnapshot(
            system_id="t1",
            snapshot_id="s0",
            timestamp_ns=1000,
            pack_current_a=1.0,
            pack_voltage_v=3.6,
            quality=TelemetryQuality.INVALID,
        )
        res = auditor.audit_step(s_bad)
        self.assertFalse(res.is_valid_step)
        self.assertIn("INVALID_TELEMETRY_QUALITY", res.data_quality_flags)


if __name__ == "__main__":
    unittest.main()
