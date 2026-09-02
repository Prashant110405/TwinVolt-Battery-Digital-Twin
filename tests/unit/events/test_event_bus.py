"""Unit tests for DigitalTwinEventBus."""

import threading
import unittest

from src.events.base import EventBus, TwinEvent
from src.events.bus import DigitalTwinEventBus
from src.events.exceptions import InvalidEventError, SubscriptionError


class TestDigitalTwinEventBus(unittest.TestCase):
    """Test suite verifying EventBus publish-subscribe routing, wildcards, priority, and fault isolation."""

    def setUp(self) -> None:
        self.bus = DigitalTwinEventBus()

    def test_protocol_compliance(self) -> None:
        """Verify bus implements EventBus protocol."""
        self.assertIsInstance(self.bus, EventBus)

    def test_publish_and_subscribe_single(self) -> None:
        """Single subscriber receives published event."""
        received = []

        def handler(event: TwinEvent) -> None:
            received.append(event)

        sub_id = self.bus.subscribe("telemetry.received", handler)
        self.assertTrue(sub_id.startswith("sub_"))
        self.assertEqual(self.bus.subscribers_count("telemetry.received"), 1)

        evt = TwinEvent(event_type="telemetry.received", payload={"v": 48.0})
        invoked = self.bus.publish(evt)

        self.assertEqual(invoked, 1)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["v"], 48.0)

    def test_wildcard_matching(self) -> None:
        """Wildcard '*' and prefix patterns match correctly."""
        all_events = []
        alerts_only = []

        self.bus.subscribe("*", lambda e: all_events.append(e))
        self.bus.subscribe("alert.*", lambda e: alerts_only.append(e))

        evt_tel = TwinEvent(event_type="telemetry.received")
        evt_alert = TwinEvent(event_type="alert.thermal")

        self.bus.publish(evt_tel)
        self.bus.publish(evt_alert)

        self.assertEqual(len(all_events), 2)
        self.assertEqual(len(alerts_only), 1)
        self.assertEqual(alerts_only[0].event_type, "alert.thermal")

    def test_priority_based_execution_order(self) -> None:
        """Subscribers execute in ascending priority order (lower number first)."""
        execution_order = []

        self.bus.subscribe("test.order", lambda e: execution_order.append("priority_200"), priority=200)
        self.bus.subscribe("test.order", lambda e: execution_order.append("priority_10"), priority=10)
        self.bus.subscribe("test.order", lambda e: execution_order.append("priority_50"), priority=50)

        self.bus.publish(TwinEvent(event_type="test.order"))
        self.assertEqual(execution_order, ["priority_10", "priority_50", "priority_200"])

    def test_unsubscribe(self) -> None:
        """Unsubscribed handler is not invoked."""
        received = []
        sub_id = self.bus.subscribe("test.unsub", lambda e: received.append(e))

        self.bus.publish(TwinEvent(event_type="test.unsub"))
        self.assertEqual(len(received), 1)

        unsub_ok = self.bus.unsubscribe(sub_id)
        self.assertTrue(unsub_ok)
        self.assertEqual(self.bus.subscribers_count("test.unsub"), 0)

        self.bus.publish(TwinEvent(event_type="test.unsub"))
        self.assertEqual(len(received), 1)  # No new invocation

    def test_fault_isolation_on_handler_exception(self) -> None:
        """Failing handler does not block remaining subscribers."""
        invocations = []

        def broken_handler(event: TwinEvent) -> None:
            invocations.append("broken")
            raise RuntimeError("Handler failed deliberately!")

        def healthy_handler(event: TwinEvent) -> None:
            invocations.append("healthy")

        self.bus.subscribe("test.fault", broken_handler, priority=10)
        self.bus.subscribe("test.fault", healthy_handler, priority=20)

        # Publish should not raise RuntimeError
        invoked_count = self.bus.publish(TwinEvent(event_type="test.fault"))

        self.assertEqual(invoked_count, 2)
        self.assertEqual(invocations, ["broken", "healthy"])
        self.assertEqual(self.bus.metrics.get_metrics_summary()["handler_failures_total"], 1)

    def test_invalid_subscription_raises(self) -> None:
        """Non-callable handler raises SubscriptionError."""
        with self.assertRaises(SubscriptionError):
            self.bus.subscribe("test.err", "not_a_callable")  # type: ignore

    def test_concurrent_publishing_thread_safety(self) -> None:
        """Multiple threads publishing concurrently execute safely without deadlocks or race conditions."""
        count = []
        lock = threading.Lock()

        def counter_handler(event: TwinEvent) -> None:
            with lock:
                count.append(1)

        self.bus.subscribe("concurrent.event", counter_handler)

        threads = []
        for _ in range(10):
            t = threading.Thread(
                target=lambda: [self.bus.publish(TwinEvent(event_type="concurrent.event")) for _ in range(20)]
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(count), 200)


if __name__ == "__main__":
    unittest.main()
