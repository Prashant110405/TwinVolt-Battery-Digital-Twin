"""Unit tests for OperatingContextClassifier across physical operating regimes."""

import unittest

from src.diagnostics.config import DiagnosticThresholdConfig
from src.diagnostics.context import OperatingContextClassifier
from src.diagnostics.types import OperatingContext
from src.telemetry.snapshots import TelemetrySnapshot


class TestOperatingContextClassifier(unittest.TestCase):
    """Test suite verifying operating context classification and temporal regime handling."""

    def test_rest_classification_after_duration_satisfied(self) -> None:
        """Quiescent current below rest threshold sustained for >= 10s is classified as REST."""
        classifier = OperatingContextClassifier(config=DiagnosticThresholdConfig(rest_min_duration_s=10.0))

        # Feed 12 continuous 1-second steps (0 to 11s)
        ctx = OperatingContext.CHARGE_CC
        for i in range(12):
            snap = TelemetrySnapshot(
                system_id="twin_01",
                snapshot_id=f"snap_{i}",
                timestamp_ns=i * 1_000_000_000,
                pack_current_a=0.02,
                pack_voltage_v=3.8,
            )
            ctx = classifier.classify(snap)

        self.assertEqual(ctx, OperatingContext.REST)

    def test_constant_current_discharge_classification(self) -> None:
        """Positive constant current (I > 0) with low variance is classified as DISCHARGE_CC."""
        classifier = OperatingContextClassifier()
        for i in range(5):
            snap = TelemetrySnapshot(
                system_id="twin_01",
                snapshot_id=f"snap_{i}",
                timestamp_ns=i * 1_000_000_000,
                pack_current_a=4.0,  # 4A constant discharge
                pack_voltage_v=3.7,
            )
            ctx = classifier.classify(snap)

        self.assertEqual(ctx, OperatingContext.DISCHARGE_CC)

    def test_constant_current_charge_classification(self) -> None:
        """Negative constant current (I < 0) with low variance is classified as CHARGE_CC."""
        classifier = OperatingContextClassifier()
        for i in range(5):
            snap = TelemetrySnapshot(
                system_id="twin_01",
                snapshot_id=f"snap_{i}",
                timestamp_ns=i * 1_000_000_000,
                pack_current_a=-3.0,  # -3A constant charge
                pack_voltage_v=3.9,
            )
            ctx = classifier.classify(snap)

        self.assertEqual(ctx, OperatingContext.CHARGE_CC)

    def test_dynamic_transient_classification(self) -> None:
        """High current variance across steps is classified as DYNAMIC_TRANSIENT."""
        classifier = OperatingContextClassifier()
        currents = [5.0, -3.0, 4.0, -2.0, 6.0]
        ctx = OperatingContext.REST

        for i, curr in enumerate(currents):
            snap = TelemetrySnapshot(
                system_id="twin_01",
                snapshot_id=f"snap_{i}",
                timestamp_ns=i * 1_000_000_000,
                pack_current_a=curr,
                pack_voltage_v=3.7,
            )
            ctx = classifier.classify(snap)

        self.assertEqual(ctx, OperatingContext.DYNAMIC_TRANSIENT)

    def test_data_gapped_classification(self) -> None:
        """Step interval exceeding data_gap_threshold_s is classified as DATA_GAPPED."""
        classifier = OperatingContextClassifier(config=DiagnosticThresholdConfig(data_gap_threshold_s=5.0))
        s0 = TelemetrySnapshot(system_id="t1", snapshot_id="s0", timestamp_ns=0, pack_current_a=2.0)
        s1 = TelemetrySnapshot(system_id="t1", snapshot_id="s1", timestamp_ns=20 * 1_000_000_000, pack_current_a=2.0)

        classifier.classify(s0)
        ctx = classifier.classify(s1)
        self.assertEqual(ctx, OperatingContext.DATA_GAPPED)

    def test_thermal_transient_classification(self) -> None:
        """High cell temperature rate of change (|dT/dt| >= threshold) triggers THERMAL_TRANSIENT."""
        classifier = OperatingContextClassifier(
            config=DiagnosticThresholdConfig(thermal_rate_threshold_c_per_s=0.05)
        )
        s0 = TelemetrySnapshot(
            system_id="t1",
            snapshot_id="s0",
            timestamp_ns=0,
            pack_current_a=1.0,
            avg_cell_temperature_c=25.0,
        )
        # 1 second later, temperature jumped from 25.0 to 25.2°C (rate = 0.20°C/s >= 0.05°C/s)
        s1 = TelemetrySnapshot(
            system_id="t1",
            snapshot_id="s1",
            timestamp_ns=1_000_000_000,
            pack_current_a=1.0,
            avg_cell_temperature_c=25.2,
        )

        classifier.classify(s0)
        ctx = classifier.classify(s1)
        self.assertEqual(ctx, OperatingContext.THERMAL_TRANSIENT)

    def test_reset_clears_classifier_state(self) -> None:
        """Reset clears internal timestamps and rolling current buffers."""
        classifier = OperatingContextClassifier()
        s0 = TelemetrySnapshot(system_id="t1", snapshot_id="s0", timestamp_ns=1000, pack_current_a=5.0)
        classifier.classify(s0)

        classifier.reset()
        self.assertIsNone(classifier._last_timestamp_ns)
        self.assertIsNone(classifier._rest_start_ts_ns)
        self.assertEqual(len(classifier._rolling_currents), 0)


if __name__ == "__main__":
    unittest.main()
