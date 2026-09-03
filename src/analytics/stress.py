"""Battery Stress Accumulation and Throughput Integration.

Integrates real-time current, voltage, and time steps to track cumulative Ampere-hour
throughput, Watt-hour energy throughput, and Equivalent Full Cycles (EFC).
"""

from typing import Optional
from src.analytics.types import StressAccumulatorState
from src.telemetry.enums import TelemetryQuality
from src.telemetry.snapshots import TelemetrySnapshot


class StressAccumulator:
    """Deterministic throughput and stress accumulator for battery digital twins.

    Sign Convention:
    - Current I > 0: Discharge (current flowing out of the battery).
    - Current I < 0: Charge (current flowing into the battery).
    - Current I = 0: Idle.
    """

    def __init__(
        self,
        nominal_capacity_ah: float,
        max_integration_interval_s: float = 60.0,
    ) -> None:
        """Initializes the stress accumulator.

        Args:
            nominal_capacity_ah: Nominal pack/cell capacity in Ampere-hours (> 0).
            max_integration_interval_s: Maximum allowable integration time step in seconds.
        """
        self._nominal_capacity_ah = max(0.0, float(nominal_capacity_ah))
        self._max_dt_s = max(0.001, float(max_integration_interval_s))

        self._total_throughput_ah: float = 0.0
        self._charge_throughput_ah: float = 0.0
        self._discharge_throughput_ah: float = 0.0
        self._energy_throughput_wh: float = 0.0
        self._total_elapsed_time_s: float = 0.0
        self._sample_count: int = 0
        self._last_timestamp_ns: Optional[int] = None

    @property
    def nominal_capacity_ah(self) -> float:
        """Configured nominal capacity in Ampere-hours."""
        return self._nominal_capacity_ah

    def set_nominal_capacity(self, capacity_ah: float) -> None:
        """Updates the nominal capacity used for EFC scaling."""
        if capacity_ah > 0.0:
            self._nominal_capacity_ah = float(capacity_ah)

    def update(
        self,
        snapshot: TelemetrySnapshot,
        dt_s: Optional[float] = None,
    ) -> StressAccumulatorState:
        """Updates cumulative stress metrics from an incoming telemetry observation.

        Args:
            snapshot: Canonical TelemetrySnapshot.
            dt_s: Optional explicit step duration in seconds. If None, derived from timestamps.

        Returns:
            Updated immutable StressAccumulatorState.
        """
        # Skip rejected / invalid telemetry
        if snapshot.quality == TelemetryQuality.INVALID:
            return self.get_state()

        curr_t_ns = snapshot.timestamp_ns
        step_dt = 0.0

        if dt_s is not None and dt_s > 0.0:
            step_dt = min(dt_s, self._max_dt_s)
        elif self._last_timestamp_ns is not None:
            if curr_t_ns > self._last_timestamp_ns:
                raw_dt = (curr_t_ns - self._last_timestamp_ns) / 1e9
                step_dt = min(raw_dt, self._max_dt_s)
            else:
                # Duplicate or non-monotonic timestamp -> ignore integration for this step
                return self.get_state()

        # Update tracking timestamp
        self._last_timestamp_ns = curr_t_ns
        self._sample_count += 1

        if step_dt <= 0.0:
            return self.get_state()

        self._total_elapsed_time_s += step_dt

        # Current and voltage extraction
        current_a = snapshot.pack_current_a
        voltage_v = snapshot.pack_voltage_v

        if current_a is not None:
            abs_i = abs(current_a)
            delta_ah = (abs_i * step_dt) / 3600.0

            self._total_throughput_ah += delta_ah

            if current_a < 0.0:
                # Negative current = Charging
                self._charge_throughput_ah += delta_ah
            elif current_a > 0.0:
                # Positive current = Discharging
                self._discharge_throughput_ah += delta_ah

            # Energy throughput (Wh = V * |I| * dt / 3600)
            if voltage_v is not None and voltage_v > 0.0:
                delta_wh = (voltage_v * abs_i * step_dt) / 3600.0
                self._energy_throughput_wh += delta_wh

        return self.get_state()

    def get_state(self) -> StressAccumulatorState:
        """Returns the current immutable StressAccumulatorState."""
        efc = 0.0
        if self._nominal_capacity_ah > 0.0:
            # EFC = Total Absolute Throughput / (2 * Nominal Capacity)
            efc = self._total_throughput_ah / (2.0 * self._nominal_capacity_ah)

        return StressAccumulatorState(
            total_throughput_ah=self._total_throughput_ah,
            charge_throughput_ah=self._charge_throughput_ah,
            discharge_throughput_ah=self._discharge_throughput_ah,
            energy_throughput_wh=self._energy_throughput_wh,
            equivalent_full_cycles=efc,
            total_elapsed_time_s=self._total_elapsed_time_s,
            sample_count=self._sample_count,
            last_timestamp_ns=self._last_timestamp_ns,
        )

    def reset(self) -> None:
        """Resets all cumulative counters to zero."""
        self._total_throughput_ah = 0.0
        self._charge_throughput_ah = 0.0
        self._discharge_throughput_ah = 0.0
        self._energy_throughput_wh = 0.0
        self._total_elapsed_time_s = 0.0
        self._sample_count = 0
        self._last_timestamp_ns = None
