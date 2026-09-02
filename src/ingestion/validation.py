"""Ingestion Validation, Filtering, and Rate Limiting.

Provides quality filtering, timestamp monotonicity checking, clock drift validation,
and per-system rate limiting for ingested telemetry streams.
"""

from collections import deque
from dataclasses import dataclass, field
import threading
import time
from typing import Mapping, Optional

from src.ingestion.exceptions import (
    IngestionValidationError,
    RateLimitExceededError,
    TimestampMonotonicityError,
)
from src.telemetry.snapshots import TelemetrySnapshot


@dataclass(frozen=True)
class IngestionFilterConfig:
    """Configuration options for telemetry ingestion filtering."""

    strict_monotonic_timestamps: bool = True
    max_clock_drift_future_s: float = 300.0  # 5 minutes in future max
    max_clock_drift_past_s: Optional[float] = None  # None = allow any past/historical timestamps
    max_samples_per_second: float = 1000.0  # Max frequency per system
    min_interval_ns: int = 0  # Minimum nanoseconds between consecutive packets (0 = no min)
    allow_out_of_order_within_ns: int = 0  # Reordering tolerance (0 = strict)


class RateLimiter:
    """Thread-safe sliding-window rate limiter per battery system."""

    def __init__(self, max_samples_per_second: float = 1000.0, window_seconds: float = 1.0) -> None:
        self._max_samples = max_samples_per_second
        self._window_ns = int(window_seconds * 1_000_000_000)
        self._history: dict[str, deque[int]] = {}
        self._lock = threading.Lock()

    def check_and_record(self, system_id: str, timestamp_ns: Optional[int] = None) -> None:
        """Checks if a new packet exceeds the rate limit. Records the timestamp if accepted.

        Raises:
            RateLimitExceededError: If the arrival rate exceeds max_samples_per_second.
        """
        t_now = timestamp_ns if timestamp_ns is not None else time.time_ns()

        with self._lock:
            if system_id not in self._history:
                self._history[system_id] = deque()

            queue = self._history[system_id]
            cutoff = t_now - self._window_ns

            # Evict timestamps older than the sliding window
            while queue and queue[0] < cutoff:
                queue.popleft()

            if len(queue) >= self._max_samples:
                raise RateLimitExceededError(
                    f"System '{system_id}' exceeded rate limit of {self._max_samples} samples/sec.",
                    source_id=system_id,
                    details={"current_window_count": len(queue), "window_ns": self._window_ns},
                )

            queue.append(t_now)

    def reset(self, system_id: Optional[str] = None) -> None:
        """Resets the rate limiter history for a given system or all systems."""
        with self._lock:
            if system_id is not None:
                self._history.pop(system_id, None)
            else:
                self._history.clear()


class TimestampValidator:
    """Tracks and validates timestamp continuity and monotonicity per battery system."""

    def __init__(self, config: IngestionFilterConfig) -> None:
        self._config = config
        self._last_timestamps: dict[str, int] = {}
        self._lock = threading.Lock()

    def validate(self, system_id: str, timestamp_ns: int, received_at_ns: Optional[int] = None) -> None:
        """Validates timestamp monotonicity and clock drift.

        Raises:
            TimestampMonotonicityError: If timestamp arrives out-of-order when strict monotonicity is enabled.
            IngestionValidationError: If timestamp exhibits excessive clock drift.
        """
        t_recv = received_at_ns if received_at_ns is not None else time.time_ns()

        # Check clock drift only for epoch timestamps (>= 2020)
        min_epoch_ns = 1_577_836_800_000_000_000  # 2020-01-01
        if timestamp_ns >= min_epoch_ns:
            # Check future drift
            max_future_ns = int(self._config.max_clock_drift_future_s * 1_000_000_000)
            if timestamp_ns > t_recv + max_future_ns:
                drift_s = (timestamp_ns - t_recv) / 1_000_000_000.0
                raise IngestionValidationError(
                    f"Timestamp for '{system_id}' is in the future by {drift_s:.1f}s (max allowed: {self._config.max_clock_drift_future_s}s).",
                    source_id=system_id,
                    details={"timestamp_ns": timestamp_ns, "received_at_ns": t_recv, "drift_s": drift_s},
                )

            # Check past drift if configured
            if self._config.max_clock_drift_past_s is not None:
                max_past_ns = int(self._config.max_clock_drift_past_s * 1_000_000_000)
                if timestamp_ns < t_recv - max_past_ns:
                    drift_s = (t_recv - timestamp_ns) / 1_000_000_000.0
                    raise IngestionValidationError(
                        f"Timestamp for '{system_id}' is too far in the past by {drift_s:.1f}s.",
                        source_id=system_id,
                        details={"timestamp_ns": timestamp_ns, "received_at_ns": t_recv, "drift_s": drift_s},
                    )

        with self._lock:
            last_t = self._last_timestamps.get(system_id)
            if last_t is not None:
                # Monotonicity check
                if timestamp_ns <= last_t:
                    delta_ns = last_t - timestamp_ns
                    if self._config.strict_monotonic_timestamps:
                        if delta_ns > self._config.allow_out_of_order_within_ns:
                            raise TimestampMonotonicityError(
                                f"Non-monotonic timestamp received for '{system_id}': "
                                f"timestamp_ns={timestamp_ns} <= last_timestamp_ns={last_t} (backward delta: {delta_ns} ns).",
                                source_id=system_id,
                                details={"current_ns": timestamp_ns, "last_ns": last_t, "delta_ns": delta_ns},
                            )

                # Minimum interval check
                if self._config.min_interval_ns > 0 and (timestamp_ns - last_t) < self._config.min_interval_ns:
                    raise IngestionValidationError(
                        f"Packet interval {(timestamp_ns - last_t)} ns is below min_interval_ns {self._config.min_interval_ns}.",
                        source_id=system_id,
                    )

            self._last_timestamps[system_id] = max(last_t or 0, timestamp_ns)

    def reset(self, system_id: Optional[str] = None) -> None:
        """Resets the timestamp tracker."""
        with self._lock:
            if system_id is not None:
                self._last_timestamps.pop(system_id, None)
            else:
                self._history.clear() if hasattr(self, "_history") else self._last_timestamps.clear()
