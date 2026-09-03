"""Operating Context Classifier for Battery Diagnostics.

Determines the active physical and electrical regime (REST, CHARGE_CC, DISCHARGE_CC,
DYNAMIC_TRANSIENT, THERMAL_TRANSIENT, DATA_GAPPED) using configured analytical criteria.
"""

from typing import Optional

from src.diagnostics.config import DiagnosticThresholdConfig
from src.diagnostics.types import OperatingContext
from src.telemetry.snapshots import TelemetrySnapshot


class OperatingContextClassifier:
    """Classifies incoming telemetry snapshots into discrete operating regimes."""

    def __init__(self, config: Optional[DiagnosticThresholdConfig] = None) -> None:
        self._config = config or DiagnosticThresholdConfig()
        self._last_timestamp_ns: Optional[int] = None
        self._rest_start_ts_ns: Optional[int] = None
        self._last_temp_c: Optional[float] = None
        self._last_temp_ts_ns: Optional[int] = None
        self._rolling_currents: list[float] = []

    @property
    def config(self) -> DiagnosticThresholdConfig:
        """Attached threshold configuration."""
        return self._config

    def classify(
        self,
        snapshot: TelemetrySnapshot,
        dt_s: Optional[float] = None,
    ) -> OperatingContext:
        """Classifies the operating context of an incoming telemetry snapshot.

        Args:
            snapshot: Incoming TelemetrySnapshot.
            dt_s: Optional step interval in seconds.

        Returns:
            OperatingContext enum indicating the active operating regime.
        """
        curr_ts = snapshot.timestamp_ns

        # 1. Telemetry Continuity & Gap Detection
        if self._last_timestamp_ns is not None:
            if curr_ts < self._last_timestamp_ns:
                # Retrograde timestamp: do not corrupt temporal state
                return OperatingContext.DATA_GAPPED

            step_interval = (curr_ts - self._last_timestamp_ns) / 1.0e9
            if dt_s is not None and dt_s > 0.0:
                step_interval = dt_s

            if step_interval > self._config.data_gap_threshold_s:
                self._rest_start_ts_ns = None
                self._rolling_currents.clear()
                self._last_temp_c = None
                self._last_temp_ts_ns = None
                self._last_timestamp_ns = curr_ts
                return OperatingContext.DATA_GAPPED

        self._last_timestamp_ns = curr_ts

        # 2. Extract Pack Current (Convention: I > 0 discharge, I < 0 charge)
        i_k = snapshot.pack_current_a
        if i_k is None:
            return OperatingContext.REST

        # 3. Rest Evaluation
        abs_i = abs(i_k)
        if abs_i <= self._config.rest_current_threshold_a:
            if self._rest_start_ts_ns is None:
                self._rest_start_ts_ns = curr_ts
            rest_duration = (curr_ts - self._rest_start_ts_ns) / 1.0e9
            if rest_duration >= self._config.rest_min_duration_s:
                self._rolling_currents.clear()
                return OperatingContext.REST
        else:
            self._rest_start_ts_ns = None

        # 4. Thermal Transient Check (if thermal sensor telemetry exists)
        t_obs = (
            snapshot.avg_cell_temperature_c
            if snapshot.avg_cell_temperature_c is not None
            else snapshot.max_cell_temperature_c
        )
        if t_obs is not None:
            if self._last_temp_c is not None and self._last_temp_ts_ns is not None:
                dt_temp = (curr_ts - self._last_temp_ts_ns) / 1.0e9
                if dt_temp > 0.0:
                    temp_rate = abs(t_obs - self._last_temp_c) / dt_temp
                    if temp_rate >= self._config.thermal_rate_threshold_c_per_s:
                        self._last_temp_c = t_obs
                        self._last_temp_ts_ns = curr_ts
                        return OperatingContext.THERMAL_TRANSIENT
            self._last_temp_c = t_obs
            self._last_temp_ts_ns = curr_ts

        # 5. Current Variance (Dynamic vs Constant Current)
        self._rolling_currents.append(i_k)
        if len(self._rolling_currents) > 5:
            self._rolling_currents.pop(0)

        if len(self._rolling_currents) >= 2:
            n = len(self._rolling_currents)
            mean_i = sum(self._rolling_currents) / n
            var_i = sum((x - mean_i) ** 2 for x in self._rolling_currents) / (n - 1)
        else:
            var_i = 0.0

        if var_i >= self._config.cc_current_variance_threshold_a2:
            return OperatingContext.DYNAMIC_TRANSIENT

        # 6. Constant Current Charge vs Discharge
        if i_k >= self._config.rest_current_threshold_a:
            return OperatingContext.DISCHARGE_CC
        elif i_k <= -self._config.rest_current_threshold_a:
            return OperatingContext.CHARGE_CC
        else:
            # Sub-threshold relaxation in progress
            return OperatingContext.REST

    def reset(self) -> None:
        """Resets all internal temporal tracking states."""
        self._last_timestamp_ns = None
        self._rest_start_ts_ns = None
        self._last_temp_c = None
        self._last_temp_ts_ns = None
        self._rolling_currents.clear()
