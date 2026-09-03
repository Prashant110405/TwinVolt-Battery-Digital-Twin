"""Unit tests for TemporalPersistenceTracker and recovery hysteresis."""

import unittest

from src.diagnostics.config import DiagnosticThresholdConfig
from src.diagnostics.temporal import (
    TemporalPersistenceState,
    TemporalPersistenceTracker,
)


class TestTemporalPersistenceTracker(unittest.TestCase):
    """Test suite verifying step-based persistence debouncing and recovery hysteresis."""

    def test_persistence_debounce_lifecycle(self) -> None:
        """Hypothesis becomes persisted only after configured consecutive supporting steps."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=5, recovery_hysteresis_steps=10)
        tracker = TemporalPersistenceTracker(hypothesis_id="HYP_TEST", config=cfg)

        # Steps 1 to 4: supporting, but not yet persisted
        for step in range(1, 5):
            state = tracker.update(
                timestamp_ns=step * 1_000_000_000,
                evidence_score=0.8,
                confidence_level="STRONG",
                is_supporting=True,
            )
            self.assertEqual(state.consecutive_supporting_steps, step)
            self.assertFalse(state.is_persisted)
            self.assertFalse(state.is_recovered)

        # Step 5: hits debounce threshold (5 steps) -> is_persisted becomes True
        state_5 = tracker.update(
            timestamp_ns=5 * 1_000_000_000,
            evidence_score=0.85,
            confidence_level="STRONG",
            is_supporting=True,
        )
        self.assertEqual(state_5.consecutive_supporting_steps, 5)
        self.assertTrue(state_5.is_persisted)
        self.assertFalse(state_5.is_recovered)

    def test_transient_interruption_resets_supporting_counter(self) -> None:
        """A transient drop in evidence before debounce threshold resets the supporting counter."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=5)
        tracker = TemporalPersistenceTracker(hypothesis_id="HYP_TEST", config=cfg)

        # 3 supporting steps
        for step in range(1, 4):
            tracker.update(step * 1_000_000_000, 0.8, "STRONG", is_supporting=True)

        # 1 non-supporting step (interruption)
        state_drop = tracker.update(4 * 1_000_000_000, 0.1, "NO_EVIDENCE", is_supporting=False)
        self.assertEqual(state_drop.consecutive_supporting_steps, 0)
        self.assertFalse(state_drop.is_persisted)

    def test_recovery_hysteresis_lifecycle(self) -> None:
        """Persisted hypothesis requires full recovery hysteresis steps before clearing."""
        cfg = DiagnosticThresholdConfig(persistence_debounce_steps=3, recovery_hysteresis_steps=5)
        tracker = TemporalPersistenceTracker(hypothesis_id="HYP_TEST", config=cfg)

        # Persist hypothesis (3 steps)
        for step in range(1, 4):
            tracker.update(step * 1_000_000_000, 0.8, "STRONG", is_supporting=True)
        self.assertTrue(tracker.get_state().is_persisted)

        # Non-supporting steps 1 to 4: hypothesis remains persisted (suppressing alert flapping)
        for rec_step in range(1, 5):
            ts = (4 + rec_step) * 1_000_000_000
            state = tracker.update(ts, 0.0, "NO_EVIDENCE", is_supporting=False)
            self.assertTrue(state.is_persisted)
            self.assertFalse(state.is_recovered)
            self.assertEqual(state.consecutive_recovery_steps, rec_step)

        # Step 5: hits recovery threshold (5 steps) -> clears persisted state
        state_recovered = tracker.update(10 * 1_000_000_000, 0.0, "NO_EVIDENCE", is_supporting=False)
        self.assertFalse(state_recovered.is_persisted)
        self.assertTrue(state_recovered.is_recovered)

    def test_reset_clears_all_temporal_state(self) -> None:
        """Reset clears internal counters, flags, and score records."""
        tracker = TemporalPersistenceTracker(hypothesis_id="HYP_TEST")
        tracker.update(1000, 0.9, "STRONG", is_supporting=True)

        tracker.reset()
        state = tracker.get_state()
        self.assertEqual(state.consecutive_supporting_steps, 0)
        self.assertEqual(state.consecutive_recovery_steps, 0)
        self.assertFalse(state.is_persisted)
        self.assertFalse(state.is_recovered)
        self.assertIsNone(state.last_timestamp_ns)

    def test_invalid_input_validation(self) -> None:
        """Invalid hypothesis_id, negative timestamps, or invalid scores raise ValueError."""
        with self.assertRaises(ValueError):
            TemporalPersistenceTracker(hypothesis_id="")

        tracker = TemporalPersistenceTracker(hypothesis_id="HYP_TEST")
        with self.assertRaises(ValueError):
            tracker.update(timestamp_ns=-1, evidence_score=0.5, confidence_level="MODERATE", is_supporting=True)

        with self.assertRaises(ValueError):
            tracker.update(timestamp_ns=1000, evidence_score=1.5, confidence_level="STRONG", is_supporting=True)


if __name__ == "__main__":
    unittest.main()
