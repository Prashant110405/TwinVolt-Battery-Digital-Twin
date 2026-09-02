"""Unit tests for ObservabilityMetrics and DiagnosticAuditLogger."""

import unittest

from src.events.base import TwinEvent
from src.events.bus import DigitalTwinEventBus
from src.events.observability import (
    DiagnosticAuditLogger,
    ObservabilityMetrics,
)
from src.events.types import ThermalAlertEvent


class TestObservability(unittest.TestCase):
    """Test suite verifying metric aggregation, duration statistics, and diagnostic audit logging."""

    def setUp(self) -> None:
        self.metrics = ObservabilityMetrics()
        self.bus = DigitalTwinEventBus(metrics=self.metrics)

    def test_metrics_counting_and_latencies(self) -> None:
        """Verify publication counters, handled counters, and latency stats."""
        self.bus.subscribe("test.metric", lambda e: None)

        self.bus.publish(TwinEvent(event_type="test.metric"))
        self.bus.publish(TwinEvent(event_type="test.metric"))

        summary = self.metrics.get_metrics_summary()
        self.assertEqual(summary["events_published_total"], 2)
        self.assertEqual(summary["events_handled_total"], 2)
        self.assertEqual(summary["handler_failures_total"], 0)
        self.assertEqual(summary["events_by_type"]["test.metric"], 2)
        self.assertGreaterEqual(summary["latency_ms"]["avg"], 0.0)

    def test_alert_counter_increments(self) -> None:
        """Publishing ThermalAlertEvent increments alerts_emitted_total."""
        alert = ThermalAlertEvent(system_id="pack_1", temperature_c=70.0, threshold_c=60.0, severity="CRITICAL")
        self.bus.publish(alert)

        summary = self.metrics.get_metrics_summary()
        self.assertEqual(summary["alerts_emitted_total"], 1)

    def test_diagnostic_audit_logger(self) -> None:
        """DiagnosticAuditLogger records recent events in memory buffer."""
        logger = DiagnosticAuditLogger(max_records=10)
        self.bus.subscribe("*", logger.handle)

        self.bus.publish(TwinEvent(event_type="event_1", source_id="source_a"))
        self.bus.publish(TwinEvent(event_type="event_2", source_id="source_b"))

        records = logger.get_recent_records()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["event_type"], "event_1")
        self.assertEqual(records[1]["source_id"], "source_b")

        logger.clear()
        self.assertEqual(len(logger.get_recent_records()), 0)


if __name__ == "__main__":
    unittest.main()
