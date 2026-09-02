"""In-Process Publish-Subscribe EventBus Implementation.

Provides deterministic, priority-ordered, fault-isolated in-process event dispatching
with wildcard topic routing and integrated observability metrics.
"""

from dataclasses import dataclass
import fnmatch
import threading
import time
from typing import Callable, Optional
import uuid

from src.events.base import AbstractEventBus, EventHandler, TwinEvent
from src.events.exceptions import InvalidEventError, SubscriptionError
from src.events.observability import ObservabilityMetrics


@dataclass(frozen=True)
class SubscriptionEntry:
    """Internal container for a registered event subscription."""

    subscription_id: str
    event_type_pattern: str
    handler: EventHandler
    priority: int
    registration_sequence: int

    def matches(self, event_type: str) -> bool:
        """Checks if event_type matches the subscription pattern."""
        if self.event_type_pattern == "*" or self.event_type_pattern == event_type:
            return True
        return fnmatch.fnmatch(event_type, self.event_type_pattern)


class DigitalTwinEventBus(AbstractEventBus):
    """Thread-safe, priority-ordered in-process EventBus with error isolation and metrics."""

    def __init__(self, metrics: Optional[ObservabilityMetrics] = None) -> None:
        self._subscriptions: dict[str, SubscriptionEntry] = {}
        self._sorted_entries: list[SubscriptionEntry] = []
        self._registration_counter = 0
        self._lock = threading.RLock()
        self._metrics = metrics or ObservabilityMetrics()

    @property
    def metrics(self) -> ObservabilityMetrics:
        """Attached observability metrics collector."""
        return self._metrics

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        priority: int = 100,
    ) -> str:
        """Subscribes a handler callback with priority ordering."""
        if not callable(handler):
            raise SubscriptionError("handler must be a callable.")
        if not event_type or not event_type.strip():
            raise SubscriptionError("event_type pattern cannot be empty.")

        with self._lock:
            self._registration_counter += 1
            sub_id = f"sub_{uuid.uuid4().hex[:12]}_{self._registration_counter}"
            entry = SubscriptionEntry(
                subscription_id=sub_id,
                event_type_pattern=event_type.strip(),
                handler=handler,
                priority=priority,
                registration_sequence=self._registration_counter,
            )
            self._subscriptions[sub_id] = entry
            self._rebuild_sorted_entries()
            return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Removes a subscription by ID."""
        with self._lock:
            if subscription_id in self._subscriptions:
                del self._subscriptions[subscription_id]
                self._rebuild_sorted_entries()
                return True
            return False

    def clear_subscribers(self) -> None:
        """Removes all registered subscribers."""
        with self._lock:
            self._subscriptions.clear()
            self._sorted_entries.clear()

    def subscribers_count(self, event_type: Optional[str] = None) -> int:
        """Returns the number of active subscriptions."""
        with self._lock:
            if event_type is None:
                return len(self._subscriptions)
            return sum(1 for entry in self._sorted_entries if entry.matches(event_type))

    def publish(self, event: TwinEvent) -> int:
        """Publishes an event to matching subscribers in priority order with error isolation.

        Returns:
            The number of handlers invoked.
        """
        if not isinstance(event, TwinEvent):
            raise InvalidEventError(f"Expected TwinEvent, got {type(event).__name__}.")

        self._metrics.record_published(event.event_type)

        # Check for alert events
        if hasattr(event, "severity"):
            self._metrics.record_alert(getattr(event, "severity", "WARNING"))

        with self._lock:
            matching_entries = [entry for entry in self._sorted_entries if entry.matches(event.event_type)]

        invoked_count = 0
        for entry in matching_entries:
            handler_name = getattr(entry.handler, "__name__", str(entry.handler))
            t_start_ns = time.perf_counter_ns()
            try:
                entry.handler(event)
                duration_ns = time.perf_counter_ns() - t_start_ns
                self._metrics.record_handled(event.event_type, duration_ns)
                invoked_count += 1
            except Exception as exc:
                # Fault isolation: record failure without terminating dispatch loop
                self._metrics.record_failure(handler_name, event.event_type, exc)
                invoked_count += 1

        return invoked_count

    def _rebuild_sorted_entries(self) -> None:
        """Sorts entries by priority (ascending) and registration order (ascending)."""
        self._sorted_entries = sorted(
            self._subscriptions.values(),
            key=lambda e: (e.priority, e.registration_sequence),
        )
