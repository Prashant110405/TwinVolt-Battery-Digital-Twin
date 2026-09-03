"""Signal Alignment Auditor and Data Quality Verifier.

Audits incoming discrete telemetry steps for timestamp monotonicity, sampling interval validity,
telemetry gaps, and corrupted sensor readings.
"""

from dataclasses import dataclass, field
from typing import Optional

from src.telemetry.enums import TelemetryQuality
from src.telemetry.snapshots import TelemetrySnapshot
from src.validation.types import ValidationConfig


@dataclass(frozen=True)
class SignalAuditResult:
    """Outcome of alignment and data quality verification for a single observation step."""

    is_valid_step: bool
    is_gap: bool
    is_duplicate_timestamp: bool
    is_retrograde_timestamp: bool
    data_quality_flags: tuple[str, ...] = ()
    effective_dt_s: float = 1.0


class SignalAlignmentAuditor:
    """Auditor validating physical signal alignment and telemetry continuity."""

    def __init__(self, config: Optional[ValidationConfig] = None) -> None:
        self._config = config or ValidationConfig()
        self._last_timestamp_ns: Optional[int] = None

    @property
    def config(self) -> ValidationConfig:
        """Attached validation configuration."""
        return self._config

    def audit_step(
        self,
        snapshot: TelemetrySnapshot,
        dt_s: Optional[float] = None,
    ) -> SignalAuditResult:
        """Audits an incoming telemetry snapshot for timing anomalies and signal integrity.

        Args:
            snapshot: Incoming TelemetrySnapshot.
            dt_s: Optional discrete step interval in seconds.

        Returns:
            SignalAuditResult with detailed diagnostics.
        """
        flags: list[str] = []
        is_valid = True
        is_gap = False
        is_dup = False
        is_retro = False

        # 1. Telemetry Quality Check
        if snapshot.quality == TelemetryQuality.INVALID:
            flags.append("INVALID_TELEMETRY_QUALITY")
            is_valid = False

        if snapshot.pack_voltage_v is None:
            flags.append("MISSING_VOLTAGE")
            is_valid = False

        if snapshot.pack_current_a is None:
            flags.append("MISSING_CURRENT")
            is_valid = False

        curr_ts = snapshot.timestamp_ns
        effective_dt = dt_s if (dt_s is not None and dt_s > 0.0) else 1.0

        # 2. Timestamp Monotonicity & Continuity Checks
        if self._last_timestamp_ns is not None:
            if curr_ts == self._last_timestamp_ns:
                flags.append("DUPLICATE_TIMESTAMP")
                is_dup = True
                is_valid = False
            elif curr_ts < self._last_timestamp_ns:
                flags.append("RETROGRADE_TIMESTAMP")
                is_retro = True
                is_valid = False
            else:
                calculated_dt = (curr_ts - self._last_timestamp_ns) / 1.0e9
                if dt_s is None:
                    effective_dt = calculated_dt
                if calculated_dt > self._config.max_dt_s:
                    flags.append("TELEMETRY_GAP")
                    is_gap = True

        self._last_timestamp_ns = curr_ts

        return SignalAuditResult(
            is_valid_step=is_valid,
            is_gap=is_gap,
            is_duplicate_timestamp=is_dup,
            is_retrograde_timestamp=is_retro,
            data_quality_flags=tuple(flags),
            effective_dt_s=effective_dt,
        )

    def reset(self) -> None:
        """Resets timestamp tracking."""
        self._last_timestamp_ns = None
