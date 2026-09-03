"""Unit tests for DiagnosticLifecycleTracker and state transitions."""

import unittest

from src.diagnostics.lifecycle import (
    DiagnosticLifecycleTracker,
    LifecycleTransition,
)
from src.diagnostics.types import FaultLifecycleState


class TestDiagnosticLifecycleTracker(unittest.TestCase):
    """Test suite verifying lifecycle state machine transitions, history bounds, and reset."""

    def test_initial_state_is_normal(self) -> None:
        """Lifecycle tracker initializes cleanly in NORMAL state with empty transition history."""
        tracker = DiagnosticLifecycleTracker()
        self.assertEqual(tracker.current_state, FaultLifecycleState.NORMAL)
        self.assertEqual(len(tracker.transitions), 0)
        self.assertEqual(tracker.last_transition_reason, "INITIALIZED")

    def test_state_transitions_record_history(self) -> None:
        """State transitions correctly update current state and append immutable history records."""
        tracker = DiagnosticLifecycleTracker()

        s1 = tracker.transition_to(
            new_state=FaultLifecycleState.ANOMALY_DETECTED,
            reason="Voltage residual anomaly observed",
            timestamp_ns=1_000_000_000,
        )
        self.assertEqual(s1, FaultLifecycleState.ANOMALY_DETECTED)
        self.assertEqual(len(tracker.transitions), 1)

        t1 = tracker.transitions[0]
        self.assertEqual(t1.from_state, FaultLifecycleState.NORMAL)
        self.assertEqual(t1.to_state, FaultLifecycleState.ANOMALY_DETECTED)
        self.assertEqual(t1.reason, "Voltage residual anomaly observed")
        self.assertEqual(t1.timestamp_ns, 1_000_000_000)

        s2 = tracker.transition_to(
            new_state=FaultLifecycleState.SUSPECTED,
            reason="Persistence debounce reached",
            timestamp_ns=2_000_000_000,
        )
        self.assertEqual(s2, FaultLifecycleState.SUSPECTED)
        self.assertEqual(len(tracker.transitions), 2)

    def test_no_duplicate_transition_record_for_identical_state(self) -> None:
        """Transitioning to the same active state updates reason without appending duplicate history record."""
        tracker = DiagnosticLifecycleTracker()
        tracker.transition_to(FaultLifecycleState.SUSPECTED, "Reason A", 1000)
        self.assertEqual(len(tracker.transitions), 1)

        tracker.transition_to(FaultLifecycleState.SUSPECTED, "Reason B", 2000)
        self.assertEqual(len(tracker.transitions), 1)
        self.assertEqual(tracker.last_transition_reason, "Reason B")

    def test_history_boundedness(self) -> None:
        """Transition history is strictly bounded by max_history_size."""
        tracker = DiagnosticLifecycleTracker(max_history_size=5)
        for i in range(10):
            state = FaultLifecycleState.ANOMALY_DETECTED if i % 2 == 0 else FaultLifecycleState.SUSPECTED
            tracker.transition_to(state, f"Step {i}", i * 1000)

        self.assertEqual(len(tracker.transitions), 5)

    def test_reset_clears_history_and_restores_normal(self) -> None:
        """Reset clears all history records and restores the NORMAL state."""
        tracker = DiagnosticLifecycleTracker()
        tracker.transition_to(FaultLifecycleState.DIAGNOSED_CRITICAL, "Critical anomaly", 1000)

        tracker.reset()
        self.assertEqual(tracker.current_state, FaultLifecycleState.NORMAL)
        self.assertEqual(len(tracker.transitions), 0)
        self.assertEqual(tracker.last_transition_reason, "RESET")

    def test_invalid_input_validation(self) -> None:
        """Invalid state types or negative timestamps raise ValueError or TypeError."""
        tracker = DiagnosticLifecycleTracker()
        with self.assertRaises(TypeError):
            tracker.transition_to("NOT_A_STATE", "Invalid", 1000)  # type: ignore

        with self.assertRaises(ValueError):
            tracker.transition_to(FaultLifecycleState.NORMAL, "Invalid ts", -100)


if __name__ == "__main__":
    unittest.main()
