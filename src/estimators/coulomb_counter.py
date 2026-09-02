"""Coulomb Counting Battery State of Charge (SOC) Estimator.

Implements ampere-hour integration with current sensor variance tracking,
quiescent rest detection, and automatic Open-Circuit Voltage (OCV) recalibration.
"""

import math
from typing import Any, Mapping, Optional

from src.estimators.base import (
    AbstractStateEstimator,
    EstimationInput,
    EstimationOutput,
    EstimationState,
)
from src.estimators.exceptions import EstimatorInitializationError
from src.models.base import OCVModel
from src.models.exceptions import InvalidModelParametersError
from src.models.math import assert_finite, calculate_coulomb_soc_step, clamp


def _find_soc_from_ocv(
    ocv_model: OCVModel,
    target_ocv_v: float,
    temperature_c: float = 25.0,
    tol: float = 1e-5,
    max_iter: int = 40,
) -> float:
    """Finds SOC fraction in [0.0, 1.0] corresponding to target_ocv_v via bounded bisection."""
    v0 = ocv_model.get_ocv(0.0, temperature_c)
    v1 = ocv_model.get_ocv(1.0, temperature_c)

    if target_ocv_v <= v0:
        return 0.0
    if target_ocv_v >= v1:
        return 1.0

    low = 0.0
    high = 1.0
    for _ in range(max_iter):
        mid = 0.5 * (low + high)
        v_mid = ocv_model.get_ocv(mid, temperature_c)
        if abs(v_mid - target_ocv_v) <= tol:
            return mid
        if v_mid < target_ocv_v:
            low = mid
        else:
            high = mid

    return 0.5 * (low + high)


class CoulombCounter(AbstractStateEstimator):
    r"""Enhanced Coulomb Counting State of Charge (SOC) Estimator.

    Integrates current measurements:
        SOC[k+1] = SOC[k] - (I[k] * dt * eta) / (Q_nom * 3600)
    with:
    - Current sensor error variance growth: $\sigma^2_{SOC}[k+1] = \sigma^2_{SOC}[k] + \sigma_I^2 (\Delta t / 3600 Q_{nom})^2$
    - Rest period detection ($|I| \le I_{rest}$ for duration $\ge t_{rest}$)
    - Automatic resting OCV recalibration via configured OCVModel.
    """

    def __init__(
        self,
        estimator_id: str,
        nominal_capacity_ah: float,
        coulombic_efficiency: float = 1.0,
        current_sensor_noise_std_a: float = 0.02,
        rest_current_threshold_a: float = 0.02,
        rest_time_threshold_s: float = 1800.0,
        ocv_recalibration_soc_variance: float = 0.0004,
        ocv_model: Optional[OCVModel] = None,
        initial_state: Optional[EstimationState] = None,
    ) -> None:
        assert_finite(nominal_capacity_ah, "nominal_capacity_ah")
        assert_finite(coulombic_efficiency, "coulombic_efficiency")
        assert_finite(current_sensor_noise_std_a, "current_sensor_noise_std_a")
        assert_finite(rest_current_threshold_a, "rest_current_threshold_a")
        assert_finite(rest_time_threshold_s, "rest_time_threshold_s")

        if nominal_capacity_ah <= 0.0:
            raise InvalidModelParametersError("nominal_capacity_ah must be strictly positive.")
        if not (0.0 < coulombic_efficiency <= 1.0):
            raise InvalidModelParametersError("coulombic_efficiency must be in (0.0, 1.0].")
        if current_sensor_noise_std_a < 0.0:
            raise InvalidModelParametersError("current_sensor_noise_std_a cannot be negative.")
        if rest_current_threshold_a < 0.0:
            raise InvalidModelParametersError("rest_current_threshold_a cannot be negative.")
        if rest_time_threshold_s <= 0.0:
            raise InvalidModelParametersError("rest_time_threshold_s must be strictly positive.")

        self._nominal_capacity_ah = float(nominal_capacity_ah)
        self._coulombic_efficiency = float(coulombic_efficiency)
        self._current_noise_std = float(current_sensor_noise_std_a)
        self._rest_current_thresh = float(rest_current_threshold_a)
        self._rest_time_thresh = float(rest_time_threshold_s)
        self._ocv_recal_var = float(ocv_recalibration_soc_variance)
        self._ocv_model = ocv_model
        self._rest_duration_s = 0.0
        self._total_recalibrations = 0

        super().__init__(estimator_id=estimator_id, initial_state=initial_state)

    @property
    def nominal_capacity_ah(self) -> float:
        """Configured nominal cell charge capacity in Ah."""
        return self._nominal_capacity_ah

    @property
    def coulombic_efficiency(self) -> float:
        """Charging coulombic efficiency."""
        return self._coulombic_efficiency

    @property
    def ocv_model(self) -> Optional[OCVModel]:
        """Configured OCV model for resting recalibration."""
        return self._ocv_model

    @property
    def rest_duration_s(self) -> float:
        """Current continuous duration at resting current in seconds."""
        return self._rest_duration_s

    @property
    def total_recalibrations(self) -> int:
        """Total number of resting OCV recalibrations executed."""
        return self._total_recalibrations

    def _create_initial_state(
        self,
        initial_soc: float,
        initial_soh: float,
        temperature_c: float,
        **kwargs: Any,
    ) -> EstimationState:
        """Initializes internal CoulombCounter state."""
        self._rest_duration_s = 0.0
        init_var = kwargs.get("initial_soc_variance", 0.0001)
        return EstimationState(
            soc_fraction=initial_soc,
            soh_fraction=initial_soh,
            soc_variance=init_var,
            temperature_c=temperature_c,
            timestamp_ns=kwargs.get("timestamp_ns"),
        )

    def _compute_step(
        self,
        estimation_input: EstimationInput,
        current_state: EstimationState,
    ) -> EstimationOutput:
        """Performs discrete Coulomb counting integration, variance growth, and rest calibration."""
        i_load = estimation_input.current_a
        v_meas = estimation_input.voltage_v
        dt = estimation_input.dt_s
        temp = estimation_input.temperature_c

        # 1. State of Charge Update
        d_soc = calculate_coulomb_soc_step(
            current_a=i_load,
            dt_s=dt,
            nominal_capacity_ah=self._nominal_capacity_ah * current_state.soh_fraction,
            coulombic_efficiency=self._coulombic_efficiency,
        )
        soc_raw = current_state.soc_fraction + d_soc
        soc_next = clamp(soc_raw, 0.0, 1.0)

        # 2. Estimation Variance Growth: Var(SOC) += (sigma_I * dt / (Q * 3600))^2
        dt_scaled = dt / (self._nominal_capacity_ah * current_state.soh_fraction * 3600.0)
        variance_growth = (self._current_noise_std * dt_scaled) ** 2
        var_next = current_state.soc_variance + variance_growth

        # 3. Rest Detection and Resting OCV Recalibration
        recalibration_applied = False
        if abs(i_load) <= self._rest_current_thresh:
            self._rest_duration_s += dt
            if self._rest_duration_s >= self._rest_time_thresh and self._ocv_model is not None:
                # Recalibrate SOC based on resting terminal voltage
                soc_ocv = _find_soc_from_ocv(self._ocv_model, v_meas, temp)
                soc_next = soc_ocv
                var_next = self._ocv_recal_var
                recalibration_applied = True
                self._total_recalibrations += 1
                # Reset timer so we don't recalibrate every single step unless continuous
                self._rest_duration_s = 0.0
        else:
            self._rest_duration_s = 0.0

        # Predicted voltage from OCV if model is available
        pred_voltage = self._ocv_model.get_ocv(soc_next, temp) if self._ocv_model else None
        innov = (v_meas - pred_voltage) if pred_voltage is not None else None

        # 4. Construct Updated EstimationState
        next_state = current_state.with_updates(
            soc_fraction=soc_next,
            soc_variance=var_next,
            temperature_c=temp,
            timestamp_ns=estimation_input.timestamp_ns,
        )

        return EstimationOutput(
            state=next_state,
            predicted_voltage_v=pred_voltage,
            innovation_v=innov,
            derivatives={"d_soc_dt": d_soc / dt if dt > 0 else 0.0},
            diagnostics={
                "rest_duration_s": self._rest_duration_s,
                "recalibration_applied": recalibration_applied,
                "total_recalibrations": self._total_recalibrations,
            },
        )

    def reset(self, initial_state: Optional[EstimationState] = None) -> None:
        """Resets Coulomb counter state and resting timers."""
        self._rest_duration_s = 0.0
        self._total_recalibrations = 0
        super().reset(initial_state)
