"""Diagnostic Lifecycle State Machine and Transition Management.

Drives deterministic state transitions across NORMAL, ANOMALY_DETECTED, SUSPECTED,
DIAGNOSED, DIAGNOSED_CRITICAL, RECOVERED, INSUFFICIENT_EVIDENCE, and DATA_QUALITY_FAILED.
"""

from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from src.diagnostics.types import (
    DiagnosticCategory,
    FaultLifecycleState,
)


@dataclass(frozen=True)
class LifecycleTransition:
    """Immutable record of a state transition in the diagnostic lifecycle."""

    from_state: FaultLifecycleState
    to_state: FaultLifecycleState
    reason: str
    timestamp_ns: int

    def to_dict(self) -> dict[str, Any]:
        """Serializes transition record to dictionary."""
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "reason": self.reason,
            "timestamp_ns": self.timestamp_ns,
        }


class DiagnosticLifecycleTracker:
    """Manages the operational lifecycle state machine for battery diagnostics."""

    def __init__(self, max_history_size: int = 50) -> None:
        if max_history_size < 1:
            raise ValueError(f"max_history_size must be >= 1, got {max_history_size}.")

        self._current_state: FaultLifecycleState = FaultLifecycleState.NORMAL
        self._transitions: deque[LifecycleTransition] = deque(maxlen=max_history_size)
        self._last_transition_reason: str = "INITIALIZED"

    @property
    def current_state(self) -> FaultLifecycleState:
        """Active diagnostic lifecycle state."""
        return self._current_state

    @property
    def last_transition_reason(self) -> str:
        """Reason for the most recent state transition."""
        return self._last_transition_reason

    @property
    def transitions(self) -> tuple[LifecycleTransition, ...]:
        """Recent transition history."""
        return tuple(self._transitions)

    def transition_to(
        self,
        new_state: FaultLifecycleState,
        reason: str,
        timestamp_ns: int,
    ) -> FaultLifecycleState:
        """Transitions to a new lifecycle state and records the event if state changed.

        Args:
            new_state: Target FaultLifecycleState.
            reason: Human-readable rationale for the transition.
            timestamp_ns: Current telemetry timestamp in nanoseconds.

        Returns:
            The resulting FaultLifecycleState.
        """
        if not isinstance(new_state, FaultLifecycleState):
            raise TypeError(f"Expected FaultLifecycleState, got {type(new_state).__name__}.")
        if not isinstance(timestamp_ns, int) or timestamp_ns < 0:
            raise ValueError(f"timestamp_ns must be a non-negative integer, got {timestamp_ns}.")

        if new_state != self._current_state:
            record = LifecycleTransition(
                from_state=self._current_state,
                to_state=new_state,
                reason=reason,
                timestamp_ns=timestamp_ns,
            )
            self._transitions.append(record)
            self._current_state = new_state
            self._last_transition_reason = reason
        else:
            self._last_transition_reason = reason

        return self._current_state

    def reset(self) -> None:
        """Resets the lifecycle tracker to the clean initial NORMAL state."""
        self._current_state = FaultLifecycleState.NORMAL
        self._transitions.clear()
        self._last_transition_reason = "RESET"
