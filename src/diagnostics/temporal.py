"""Temporal persistence and recovery hysteresis tracking for Battery Diagnostics.

Provides deterministic step-based debouncing, onset detection, sustained evidence tracking,
and multi-step recovery hysteresis.
"""

from dataclasses import dataclass
import math
from typing import Any, Optional

from src.diagnostics.config import DiagnosticThresholdConfig


@dataclass(frozen=True)
class TemporalPersistenceState:
    """Immutable snapshot of the temporal persistence state for a single diagnostic hypothesis."""

    hypothesis_id: str
    consecutive_supporting_steps: int = 0
    consecutive_recovery_steps: int = 0
    is_persisted: bool = False
    is_recovered: bool = False
    last_timestamp_ns: Optional[int] = None
    last_evidence_score: float = 0.0
    last_confidence_level: str = "NO_EVIDENCE"

    def __post_init__(self) -> None:
        if not isinstance(self.consecutive_supporting_steps, int) or self.consecutive_supporting_steps < 0:
            raise ValueError(f"consecutive_supporting_steps must be non-negative int, got {self.consecutive_supporting_steps}.")
        if not isinstance(self.consecutive_recovery_steps, int) or self.consecutive_recovery_steps < 0:
            raise ValueError(f"consecutive_recovery_steps must be non-negative int, got {self.consecutive_recovery_steps}.")
        if not (0.0 <= self.last_evidence_score <= 1.0):
            raise ValueError(f"last_evidence_score must be in [0.0, 1.0], got {self.last_evidence_score}.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes temporal persistence state to dictionary."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "consecutive_supporting_steps": self.consecutive_supporting_steps,
            "consecutive_recovery_steps": self.consecutive_recovery_steps,
            "is_persisted": self.is_persisted,
            "is_recovered": self.is_recovered,
            "last_timestamp_ns": self.last_timestamp_ns,
            "last_evidence_score": round(self.last_evidence_score, 4),
            "last_confidence_level": self.last_confidence_level,
        }


class TemporalPersistenceTracker:
    """Tracks persistence, debouncing, and recovery hysteresis for a diagnostic hypothesis."""

    def __init__(
        self,
        hypothesis_id: str,
        config: Optional[DiagnosticThresholdConfig] = None,
    ) -> None:
        if not hypothesis_id or not isinstance(hypothesis_id, str):
            raise ValueError("hypothesis_id must be a non-empty string.")

        self._hypothesis_id = hypothesis_id
        self._config = config or DiagnosticThresholdConfig()

        self._consecutive_supporting_steps: int = 0
        self._consecutive_recovery_steps: int = 0
        self._is_persisted: bool = False
        self._is_recovered: bool = False
        self._last_timestamp_ns: Optional[int] = None
        self._last_evidence_score: float = 0.0
        self._last_confidence_level: str = "NO_EVIDENCE"

    @property
    def hypothesis_id(self) -> str:
        """Attached hypothesis identifier."""
        return self._hypothesis_id

    @property
    def config(self) -> DiagnosticThresholdConfig:
        """Attached threshold configuration."""
        return self._config

    def update(
        self,
        timestamp_ns: int,
        evidence_score: float,
        confidence_level: str,
        is_supporting: bool,
    ) -> TemporalPersistenceState:
        """Updates the temporal persistence state with the results of a new evaluation step.

        Args:
            timestamp_ns: Current telemetry timestamp in nanoseconds.
            evidence_score: Computed evidence score in [0.0, 1.0].
            confidence_level: Classified confidence tier string.
            is_supporting: True if current step satisfies hypothesis activation criteria.

        Returns:
            Immutable TemporalPersistenceState snapshot.
        """
        if not isinstance(timestamp_ns, int) or timestamp_ns < 0:
            raise ValueError(f"timestamp_ns must be a non-negative integer, got {timestamp_ns}.")
        if not isinstance(evidence_score, (int, float)) or math.isnan(evidence_score) or math.isinf(evidence_score):
            raise ValueError(f"evidence_score must be a finite float, got {evidence_score}.")
        if not (0.0 <= evidence_score <= 1.0):
            raise ValueError(f"evidence_score must be in [0.0, 1.0], got {evidence_score}.")

        self._last_timestamp_ns = timestamp_ns
        self._last_evidence_score = float(evidence_score)
        self._last_confidence_level = confidence_level

        if is_supporting:
            self._consecutive_supporting_steps += 1
            self._consecutive_recovery_steps = 0
            self._is_recovered = False

            if self._consecutive_supporting_steps >= self._config.persistence_debounce_steps:
                self._is_persisted = True
        else:
            self._consecutive_supporting_steps = 0

            if self._is_persisted:
                self._consecutive_recovery_steps += 1
                if self._consecutive_recovery_steps >= self._config.recovery_hysteresis_steps:
                    self._is_persisted = False
                    self._is_recovered = True
                    self._consecutive_recovery_steps = 0
            else:
                self._is_recovered = False
                self._consecutive_recovery_steps = 0

        return self.get_state()

    def get_state(self) -> TemporalPersistenceState:
        """Returns the current immutable persistence state."""
        return TemporalPersistenceState(
            hypothesis_id=self._hypothesis_id,
            consecutive_supporting_steps=self._consecutive_supporting_steps,
            consecutive_recovery_steps=self._consecutive_recovery_steps,
            is_persisted=self._is_persisted,
            is_recovered=self._is_recovered,
            last_timestamp_ns=self._last_timestamp_ns,
            last_evidence_score=self._last_evidence_score,
            last_confidence_level=self._last_confidence_level,
        )

    def reset(self) -> None:
        """Resets all internal counters and temporal flags."""
        self._consecutive_supporting_steps = 0
        self._consecutive_recovery_steps = 0
        self._is_persisted = False
        self._is_recovered = False
        self._last_timestamp_ns = None
        self._last_evidence_score = 0.0
        self._last_confidence_level = "NO_EVIDENCE"
