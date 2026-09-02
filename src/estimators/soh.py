"""State of Health (SOH) and Impedance Degradation Estimator.

Tracks cell capacity loss and DC internal resistance growth across charge/discharge cycles
with health classification mapping to the standard BatteryHealthState domain entity.
"""

from typing import Any, Mapping, Optional

from src.domain.battery.enums import BatteryHealthState
from src.estimators.base import (
    AbstractStateEstimator,
    EstimationInput,
    EstimationOutput,
    EstimationState,
)
from src.models.exceptions import InvalidModelParametersError
from src.models.math import assert_finite, clamp


class SOHEstimator(AbstractStateEstimator):
    r"""State of Health (SOH) Capacity and Internal Resistance Tracker.

    Tracks:
    1. Capacity SOH ($SOH_C$): $\hat{Q}_{usable} = |\int I dt| / \Delta SOC$ during deep cycling.
    2. Resistance SOH ($SOH_R$): $\hat{R}_0 = |\Delta V / \Delta I|$ during high current transients.
    3. Combined SOH: $SOH = \min(SOH_C, SOH_R)$.
    4. Health classification: HEALTHY, AGED, DEGRADED, CRITICAL, END_OF_LIFE.
    """

    def __init__(
        self,
        estimator_id: str,
        nominal_capacity_ah: float,
        baseline_r0_ohm: float = 0.025,
        eol_resistance_multiplier: float = 2.0,
        min_cycle_delta_soc: float = 0.30,
        current_step_threshold_a: float = 1.0,
        capacity_filter_alpha: float = 0.10,
        initial_state: Optional[EstimationState] = None,
    ) -> None:
        assert_finite(nominal_capacity_ah, "nominal_capacity_ah")
        assert_finite(baseline_r0_ohm, "baseline_r0_ohm")
        assert_finite(eol_resistance_multiplier, "eol_resistance_multiplier")
        assert_finite(min_cycle_delta_soc, "min_cycle_delta_soc")

        if nominal_capacity_ah <= 0.0:
            raise InvalidModelParametersError("nominal_capacity_ah must be strictly positive.")
        if baseline_r0_ohm <= 0.0:
            raise InvalidModelParametersError("baseline_r0_ohm must be strictly positive.")
        if eol_resistance_multiplier <= 1.0:
            raise InvalidModelParametersError("eol_resistance_multiplier must be > 1.0.")
        if not (0.0 < min_cycle_delta_soc <= 1.0):
            raise InvalidModelParametersError("min_cycle_delta_soc must be in (0.0, 1.0].")

        self._nominal_capacity_ah = float(nominal_capacity_ah)
        self._r0_fresh_ohm = float(baseline_r0_ohm)
        self._eol_r_multiplier = float(eol_resistance_multiplier)
        self._min_delta_soc = float(min_cycle_delta_soc)
        self._current_step_thresh = float(current_step_threshold_a)
        self._alpha = float(capacity_filter_alpha)

        # Internal tracking variables
        self._soh_c = 1.0
        self._soh_r = 1.0
        self._estimated_r0_ohm = self._r0_fresh_ohm
        self._throughput_ah = 0.0

        # Cycle integration tracking
        self._cycle_active = False
        self._cycle_start_soc = 1.0
        self._cycle_integrated_ah = 0.0
        self._prev_current_a = 0.0
        self._prev_voltage_v = 0.0

        super().__init__(estimator_id=estimator_id, initial_state=initial_state)

    @property
    def nominal_capacity_ah(self) -> float:
        """Nominal charge capacity in Ah."""
        return self._nominal_capacity_ah

    @property
    def soh_capacity_fraction(self) -> float:
        r"""Capacity degradation fraction $SOH_C \in [0.0, 1.0]$."""
        return self._soh_c

    @property
    def soh_resistance_fraction(self) -> float:
        r"""Resistance degradation fraction $SOH_R \in [0.0, 1.0]$."""
        return self._soh_r

    @property
    def estimated_r0_mohm(self) -> float:
        """Estimated DC internal resistance in milliohms."""
        return self._estimated_r0_ohm * 1000.0

    @property
    def total_throughput_ah(self) -> float:
        """Cumulative charge throughput in Ah."""
        return self._throughput_ah

    @property
    def health_state(self) -> BatteryHealthState:
        """Domain health state classification."""
        combined_soh = min(self._soh_c, self._soh_r)
        if combined_soh >= 0.90:
            return BatteryHealthState.HEALTHY
        if combined_soh >= 0.80:
            return BatteryHealthState.AGED
        if combined_soh >= 0.70:
            return BatteryHealthState.DEGRADED
        if combined_soh >= 0.60:
            return BatteryHealthState.CRITICAL
        return BatteryHealthState.END_OF_LIFE

    def _create_initial_state(
        self,
        initial_soc: float,
        initial_soh: float,
        temperature_c: float,
        **kwargs: Any,
    ) -> EstimationState:
        """Initializes internal SOH tracking state."""
        self._soh_c = initial_soh
        self._soh_r = 1.0
        self._estimated_r0_ohm = self._r0_fresh_ohm
        self._throughput_ah = 0.0
        self._cycle_active = False
        self._cycle_start_soc = initial_soc
        self._cycle_integrated_ah = 0.0
        self._prev_current_a = 0.0
        self._prev_voltage_v = 0.0

        return EstimationState(
            soc_fraction=initial_soc,
            soh_fraction=initial_soh,
            temperature_c=temperature_c,
            internal_resistance_mohm=self.estimated_r0_mohm,
            timestamp_ns=kwargs.get("timestamp_ns"),
        )

    def _compute_step(
        self,
        estimation_input: EstimationInput,
        current_state: EstimationState,
    ) -> EstimationOutput:
        """Updates capacity throughput, resistance estimation, and SOH."""
        i_load = estimation_input.current_a
        v_meas = estimation_input.voltage_v
        dt = estimation_input.dt_s
        temp = estimation_input.temperature_c
        current_soc = current_state.soc_fraction

        # 1. Update cumulative throughput
        ah_delta = abs(i_load) * dt / 3600.0
        self._throughput_ah += ah_delta

        # 2. Ohmic Resistance Pulse Tracking: R0 = |delta_V / delta_I|
        delta_i = i_load - self._prev_current_a
        delta_v = v_meas - self._prev_voltage_v
        if abs(delta_i) >= self._current_step_thresh and dt <= 2.0:
            r_measured = abs(delta_v / delta_i)
            # Filter resistance measurement
            if 0.001 <= r_measured <= (self._r0_fresh_ohm * self._eol_r_multiplier * 2.0):
                self._estimated_r0_ohm = (1.0 - self._alpha) * self._estimated_r0_ohm + self._alpha * r_measured
                r_excess = max(0.0, self._estimated_r0_ohm - self._r0_fresh_ohm)
                r_span = self._r0_fresh_ohm * (self._eol_r_multiplier - 1.0)
                self._soh_r = clamp(1.0 - (r_excess / r_span), 0.0, 1.0)

        # 3. Capacity Degradation Cycle Tracking
        if not self._cycle_active:
            if abs(i_load) > 0.1:
                self._cycle_active = True
                self._cycle_start_soc = current_soc
                self._cycle_integrated_ah = 0.0
        else:
            self._cycle_integrated_ah += i_load * dt / 3600.0
            delta_soc = abs(current_soc - self._cycle_start_soc)

            # Cycle finished or rest entered after substantial SOC change
            if abs(i_load) <= 0.05 or (current_soc <= 0.05 or current_soc >= 0.95):
                if delta_soc >= self._min_delta_soc and abs(self._cycle_integrated_ah) > 0.1:
                    q_usable_measured = abs(self._cycle_integrated_ah) / delta_soc
                    soh_c_measured = q_usable_measured / self._nominal_capacity_ah
                    if 0.30 <= soh_c_measured <= 1.20:
                        self._soh_c = clamp(
                            (1.0 - self._alpha) * self._soh_c + self._alpha * soh_c_measured,
                            0.0,
                            1.0,
                        )
                self._cycle_active = False

        self._prev_current_a = i_load
        self._prev_voltage_v = v_meas

        # 4. Combined SOH
        combined_soh = min(self._soh_c, self._soh_r)

        next_state = current_state.with_updates(
            soh_fraction=combined_soh,
            internal_resistance_mohm=self.estimated_r0_mohm,
            temperature_c=temp,
            timestamp_ns=estimation_input.timestamp_ns,
        )

        return EstimationOutput(
            state=next_state,
            diagnostics={
                "soh_capacity": self._soh_c,
                "soh_resistance": self._soh_r,
                "health_state": self.health_state.value,
                "estimated_r0_mohm": self.estimated_r0_mohm,
                "total_throughput_ah": self._throughput_ah,
            },
        )

    def reset(self, initial_state: Optional[EstimationState] = None) -> None:
        """Resets SOH tracker internal state."""
        super().reset(initial_state)
