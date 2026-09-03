"""Excitation and Observability Gating for Online Parameter Identification.

Evaluates incoming telemetry to ensure sufficient current magnitude, persistent dynamic excitation,
and valid operating regimes before permitting RLS parameter updates.
"""

from collections import deque
from dataclasses import dataclass
from typing import Optional

from src.calibration.types import RLSConfig
from src.telemetry.enums import TelemetryQuality
from src.telemetry.snapshots import TelemetrySnapshot


@dataclass(frozen=True)
class ExcitationGatingResult:
    """Outcome of excitation and observability evaluation for a single observation step."""

    is_valid_step: bool
    can_update_r0: bool
    can_update_secondary: bool
    is_telemetry_gap: bool
    gating_status: str
    current_variance: float
    reason: Optional[str] = None


class ExcitationDetector:
    """Windowed observability and persistent excitation detector."""

    def __init__(self, config: Optional[RLSConfig] = None) -> None:
        self._config = config or RLSConfig()
        self._current_window: deque[float] = deque(maxlen=self._config.excitation_window_size)
        self._last_current_a: Optional[float] = None
        self._last_timestamp_ns: Optional[int] = None

    @property
    def config(self) -> RLSConfig:
        """Attached RLS configuration."""
        return self._config

    def evaluate(
        self,
        snapshot: TelemetrySnapshot,
        soc_estimate: float,
        voltage_residual_v: Optional[float] = None,
        dt_s: Optional[float] = None,
    ) -> ExcitationGatingResult:
        """Evaluates whether the incoming snapshot satisfies excitation and observability criteria.

        Args:
            snapshot: Incoming TelemetrySnapshot.
            soc_estimate: Current State of Charge estimate in [0.0, 1.0].
            voltage_residual_v: Instantaneous terminal voltage residual (V_meas - V_sim).
            dt_s: Effective time step interval in seconds.

        Returns:
            ExcitationGatingResult with granular capability flags.
        """
        # 1. Telemetry Quality Check
        if snapshot.quality == TelemetryQuality.INVALID:
            return ExcitationGatingResult(
                is_valid_step=False,
                can_update_r0=False,
                can_update_secondary=False,
                is_telemetry_gap=False,
                gating_status="SENSOR_INVALID",
                current_variance=0.0,
                reason="Telemetry snapshot is flagged INVALID.",
            )

        curr_t_ns = snapshot.timestamp_ns
        step_dt = dt_s

        # 2. Timestamp Monotonicity & Telemetry Gap Check
        is_gap = False
        if self._last_timestamp_ns is not None:
            if curr_t_ns <= self._last_timestamp_ns:
                # Duplicate or retrograde timestamp -> skip step completely
                return ExcitationGatingResult(
                    is_valid_step=False,
                    can_update_r0=False,
                    can_update_secondary=False,
                    is_telemetry_gap=False,
                    gating_status="NON_MONOTONIC_TIMESTAMP",
                    current_variance=0.0,
                    reason=f"Timestamp {curr_t_ns} <= previous {self._last_timestamp_ns}.",
                )

            calculated_dt = (curr_t_ns - self._last_timestamp_ns) / 1.0e9
            if step_dt is None:
                step_dt = calculated_dt

            if calculated_dt > self._config.max_dt_s:
                is_gap = True
                self._current_window.clear()
                self._last_current_a = None

        self._last_timestamp_ns = curr_t_ns

        if is_gap:
            return ExcitationGatingResult(
                is_valid_step=False,
                can_update_r0=False,
                can_update_secondary=False,
                is_telemetry_gap=True,
                gating_status="TELEMETRY_GAP",
                current_variance=0.0,
                reason=f"Telemetry gap exceeding {self._config.max_dt_s}s detected.",
            )

        current_a = snapshot.pack_current_a
        if current_a is None:
            return ExcitationGatingResult(
                is_valid_step=False,
                can_update_r0=False,
                can_update_secondary=False,
                is_telemetry_gap=False,
                gating_status="MISSING_CURRENT",
                current_variance=0.0,
                reason="Pack current measurement is missing.",
            )

        # 3. Update Current History & Variance
        self._current_window.append(current_a)
        step_change = abs(current_a - self._last_current_a) if self._last_current_a is not None else 0.0
        self._last_current_a = current_a

        n = len(self._current_window)
        mean_i = sum(self._current_window) / n
        current_variance = sum((x - mean_i) ** 2 for x in self._current_window) / n if n > 1 else 0.0

        # 4. SOC Regime Gating (Avoid steep OCV cliff regions)
        if not (self._config.min_soc <= soc_estimate <= self._config.max_soc):
            return ExcitationGatingResult(
                is_valid_step=True,
                can_update_r0=False,
                can_update_secondary=False,
                is_telemetry_gap=False,
                gating_status="SOC_CLIFF_REGIME",
                current_variance=current_variance,
                reason=f"SOC {soc_estimate:.3f} outside stable range [{self._config.min_soc}, {self._config.max_soc}].",
            )

        # 5. Voltage Residual Outlier Gating
        if voltage_residual_v is not None and abs(voltage_residual_v) > self._config.max_voltage_residual_v:
            return ExcitationGatingResult(
                is_valid_step=True,
                can_update_r0=False,
                can_update_secondary=False,
                is_telemetry_gap=False,
                gating_status="VOLTAGE_RESIDUAL_OUTLIER",
                current_variance=current_variance,
                reason=f"Voltage residual {abs(voltage_residual_v):.3f}V exceeds limit {self._config.max_voltage_residual_v}V.",
            )

        # 6. Current Magnitude Gating for R0
        abs_i = abs(current_a)
        if abs_i < self._config.min_current_a:
            return ExcitationGatingResult(
                is_valid_step=True,
                can_update_r0=False,
                can_update_secondary=False,
                is_telemetry_gap=False,
                gating_status="INSUFFICIENT_CURRENT",
                current_variance=current_variance,
                reason=f"Current magnitude {abs_i:.3f}A below threshold {self._config.min_current_a}A.",
            )

        # Primary R0 can be observed under current load
        can_r0 = True

        # Secondary (R1, C1) requires persistent dynamic excitation
        has_dynamic_excitation = (
            (current_variance >= self._config.min_current_variance)
            or (step_change >= self._config.min_current_step_a)
        ) and (n >= 3)

        gating_status = "ACTIVE" if has_dynamic_excitation else "PRIMARY_ONLY_R0"

        return ExcitationGatingResult(
            is_valid_step=True,
            can_update_r0=can_r0,
            can_update_secondary=has_dynamic_excitation,
            is_telemetry_gap=False,
            gating_status=gating_status,
            current_variance=current_variance,
            reason=None if has_dynamic_excitation else "Low current variance; secondary R1/C1 gated.",
        )

    def reset(self) -> None:
        """Resets excitation history window and timestamp tracking."""
        self._current_window.clear()
        self._last_current_a = None
        self._last_timestamp_ns = None
