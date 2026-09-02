"""Observability and Metrics Engine for Events and State Execution.

Collects in-process counters, execution latencies, failure statistics, and diagnostic
audit records with thread safety and zero external logging dependencies.
"""

from collections import deque
from dataclasses import dataclass, field
import threading
import time
from typing import Any, Mapping, Optional

from src.events.base import TwinEvent


class ObservabilityMetrics:
    """Thread-safe in-process metrics aggregator for events, latencies, and execution health."""

    def __init__(self, max_recent_latencies: int = 1000) -> None:
        self._lock = threading.RLock()
        self._max_recent = max_recent_latencies
        self._events_published_total = 0
        self._events_handled_total = 0
        self._handler_failures_total = 0
        self._alerts_emitted_total = 0
        self._events_by_type: dict[str, int] = {}
        self._failures_by_handler: dict[str, int] = {}
        self._recent_latencies_ns: deque[int] = deque(maxlen=max_recent_latencies)
        self._min_latency_ns = float("inf")
        self._max_latency_ns = 0

    def record_published(self, event_type: str) -> None:
        """Records an event publication."""
        with self._lock:
            self._events_published_total += 1
            self._events_by_type[event_type] = self._events_by_type.get(event_type, 0) + 1

    def record_handled(self, event_type: str, duration_ns: int) -> None:
        """Records a successful handler execution and latency."""
        with self._lock:
            self._events_handled_total += 1
            self._recent_latencies_ns.append(duration_ns)
            if duration_ns < self._min_latency_ns:
                self._min_latency_ns = duration_ns
            if duration_ns > self._max_latency_ns:
                self._max_latency_ns = duration_ns

    def record_failure(self, handler_name: str, event_type: str, error: Exception) -> None:
        """Records a handler failure."""
        with self._lock:
            self._handler_failures_total += 1
            self._failures_by_handler[handler_name] = self._failures_by_handler.get(handler_name, 0) + 1

    def record_alert(self, severity: str) -> None:
        """Records an alert event."""
        with self._lock:
            self._alerts_emitted_total += 1

    def get_metrics_summary(self) -> dict[str, Any]:
        """Returns a snapshot of current observability metrics."""
        with self._lock:
            count = len(self._recent_latencies_ns)
            avg_latency_ms = (
                (sum(self._recent_latencies_ns) / count / 1_000_000.0) if count > 0 else 0.0
            )
            min_ms = (self._min_latency_ns / 1_000_000.0) if self._min_latency_ns != float("inf") else 0.0
            max_ms = (self._max_latency_ns / 1_000_000.0)

            return {
                "events_published_total": self._events_published_total,
                "events_handled_total": self._events_handled_total,
                "handler_failures_total": self._handler_failures_total,
                "alerts_emitted_total": self._alerts_emitted_total,
                "events_by_type": dict(self._events_by_type),
                "failures_by_handler": dict(self._failures_by_handler),
                "latency_ms": {
                    "avg": round(avg_latency_ms, 4),
                    "min": round(min_ms, 4),
                    "max": round(max_ms, 4),
                    "sample_count": count,
                },
            }

    def reset(self) -> None:
        """Resets all metrics counters and latencies."""
        with self._lock:
            self._events_published_total = 0
            self._events_handled_total = 0
            self._handler_failures_total = 0
            self._alerts_emitted_total = 0
            self._events_by_type.clear()
            self._failures_by_handler.clear()
            self._recent_latencies_ns.clear()
            self._min_latency_ns = float("inf")
            self._max_latency_ns = 0


class DiagnosticAuditLogger:
    """Lightweight in-memory diagnostic audit observer that records recent events."""

    def __init__(self, max_records: int = 500) -> None:
        self._max_records = max_records
        self._records: deque[dict[str, Any]] = deque(maxlen=max_records)
        self._lock = threading.RLock()

    def handle(self, event: TwinEvent) -> None:
        """Handler callback for EventBus."""
        with self._lock:
            self._records.append({
                "recorded_at_ns": time.time_ns(),
                "event_id": event.event_id,
                "event_type": event.event_type,
                "source_id": event.source_id,
                "timestamp_ns": event.timestamp_ns,
            })

    def get_recent_records(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        """Returns recent audit records."""
        with self._lock:
            items = list(self._records)
            if limit is not None:
                return items[-limit:]
            return items

    def clear(self) -> None:
        """Clears audit records."""
        with self._lock:
            self._records.clear()
