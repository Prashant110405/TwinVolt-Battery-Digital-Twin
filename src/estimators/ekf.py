"""Extended Kalman Filter (EKF) State of Charge (SOC) Estimator.

Implements non-linear state-space recursive estimation for Equivalent Circuit Models
with Joseph-stabilized covariance updates and analytical OCV Jacobian linearizations.
"""

import math
from typing import Any, Mapping, Optional, Sequence

from src.estimators.base import (
    AbstractStateEstimator,
    EstimationInput,
    EstimationOutput,
    EstimationState,
)
from src.estimators.exceptions import (
    EstimatorConvergenceError,
    EstimatorInitializationError,
    InvalidEstimatorInputError,
)
from src.models.base import OCVModel
from src.models.ecm.parameters import GenericECMParameters
from src.models.exceptions import InvalidModelParametersError
from src.models.math import assert_finite, calculate_coulomb_soc_step, clamp
from src.models.parameters.linear_ocv import LinearOCVModel


# ==============================================================================
# Pure Python Matrix Helper Functions for EKF
# ==============================================================================
def _mat_zeros(rows: int, cols: int) -> list[list[float]]:
    return [[0.0 for _ in range(cols)] for _ in range(rows)]


def _mat_eye(n: int) -> list[list[float]]:
    m = _mat_zeros(n, n)
    for i in range(n):
        m[i][i] = 1.0
    return m


def _mat_mult(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    rows_a, cols_a = len(a), len(a[0])
    rows_b, cols_b = len(b), len(b[0])
    res = _mat_zeros(rows_a, cols_b)
    for i in range(rows_a):
        for j in range(cols_b):
            s = 0.0
            for k in range(cols_a):
                s += a[i][k] * b[k][j]
            res[i][j] = s
    return res


def _mat_transpose(a: list[list[float]]) -> list[list[float]]:
    rows, cols = len(a), len(a[0])
    res = _mat_zeros(cols, rows)
    for i in range(rows):
        for j in range(cols):
            res[j][i] = a[i][j]
    return res


def _mat_add(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    rows, cols = len(a), len(a[0])
    res = _mat_zeros(rows, cols)
    for i in range(rows):
        for j in range(cols):
            res[i][j] = a[i][j] + b[i][j]
    return res


class ExtendedKalmanFilter(AbstractStateEstimator):
    """Non-Linear Extended Kalman Filter (EKF) for Battery State of Charge (SOC).

    State Space Representation:
        x[k] = [ SOC, V_RC,1, V_RC,2, ..., V_RC,N ]^T

    Prediction:
        x[k|k-1] = A * x[k-1|k-1] + B * I[k]
        P[k|k-1] = A * P[k-1|k-1] * A^T + Q

    Measurement:
        V_pred = V_oc(SOC, T) - I[k] * R_0 - sum(V_RC,i)
        C = [ dOCV/dSOC, -1, -1, ..., -1 ]
        innovation = V_meas - V_pred
        S = C * P[k|k-1] * C^T + R_v
        K = P[k|k-1] * C^T / S
        x[k|k] = x[k|k-1] + K * innovation
        P[k|k] = (I - K*C) * P[k|k-1] * (I - K*C)^T + K * R_v * K^T  (Joseph Form)
    """

    def __init__(
        self,
        estimator_id: str,
        parameters: GenericECMParameters,
        ocv_model: Optional[OCVModel] = None,
        process_noise_soc: float = 1e-7,
        process_noise_rc: float = 1e-6,
        measurement_noise_voltage_v2: float = 1e-4,
        initial_covariance_soc: float = 0.04,
        initial_covariance_rc: float = 1e-4,
        initial_state: Optional[EstimationState] = None,
    ) -> None:
        if not isinstance(parameters, GenericECMParameters):
            raise InvalidModelParametersError(
                f"parameters must be GenericECMParameters, got {type(parameters).__name__}."
            )
        self._params = parameters
        self._ocv_model = ocv_model or LinearOCVModel(
            v_min_v=parameters.nominal_voltage_v * 0.8,
            v_max_v=parameters.nominal_voltage_v * 1.14,
        )

        assert_finite(process_noise_soc, "process_noise_soc")
        assert_finite(process_noise_rc, "process_noise_rc")
        assert_finite(measurement_noise_voltage_v2, "measurement_noise_voltage_v2")
        assert_finite(initial_covariance_soc, "initial_covariance_soc")
        assert_finite(initial_covariance_rc, "initial_covariance_rc")

        if process_noise_soc < 0.0 or process_noise_rc < 0.0:
            raise InvalidModelParametersError("Process noise must be non-negative.")
        if measurement_noise_voltage_v2 <= 0.0:
            raise InvalidModelParametersError("Measurement noise variance must be strictly positive.")
        if initial_covariance_soc < 0.0 or initial_covariance_rc < 0.0:
            raise InvalidModelParametersError("Initial covariance must be non-negative.")

        self._dim = 1 + self._params.branch_count
        self._q_soc = float(process_noise_soc)
        self._q_rc = float(process_noise_rc)
        self._r_v = float(measurement_noise_voltage_v2)
        self._p_init_soc = float(initial_covariance_soc)
        self._p_init_rc = float(initial_covariance_rc)

        # Internal state vector and covariance matrix
        self._x: list[float] = [1.0] + [0.0 for _ in range(self._params.branch_count)]
        self._P: list[list[float]] = _mat_eye(self._dim)

        super().__init__(estimator_id=estimator_id, initial_state=initial_state)

    @property
    def parameters(self) -> GenericECMParameters:
        """Configured ECM physical parameters."""
        return self._params

    @property
    def ocv_model(self) -> OCVModel:
        """Configured Open-Circuit Voltage relationship provider."""
        return self._ocv_model

    @property
    def state_dimension(self) -> int:
        """Dimension of the state vector (1 + N RC branches)."""
        return self._dim

    @property
    def covariance_matrix(self) -> list[list[float]]:
        """Current state error covariance matrix P."""
        return [row[:] for row in self._P]

    def _create_initial_state(
        self,
        initial_soc: float,
        initial_soh: float,
        temperature_c: float,
        **kwargs: Any,
    ) -> EstimationState:
        """Initializes internal state vector x and covariance P."""
        self._x = [initial_soc] + [0.0 for _ in range(self._params.branch_count)]
        
        P = _mat_zeros(self._dim, self._dim)
        P[0][0] = kwargs.get("initial_covariance_soc", self._p_init_soc)
        for i in range(1, self._dim):
            P[i][i] = kwargs.get("initial_covariance_rc", self._p_init_rc)
        self._P = P

        return EstimationState(
            soc_fraction=initial_soc,
            soh_fraction=initial_soh,
            soc_variance=P[0][0],
            temperature_c=temperature_c,
            internal_resistance_mohm=self._params.total_dc_resistance_mohm,
            polarization_voltages_v=tuple(self._x[1:]),
            timestamp_ns=kwargs.get("timestamp_ns"),
        )

    def _compute_step(
        self,
        estimation_input: EstimationInput,
        current_state: EstimationState,
    ) -> EstimationOutput:
        """Executes full discrete EKF Predict and Correct steps."""
        i_load = estimation_input.current_a
        v_meas = estimation_input.voltage_v
        dt = estimation_input.dt_s
        temp = estimation_input.temperature_c
        q_cap = self._params.nominal_capacity_ah * current_state.soh_fraction * 3600.0

        # ======================================================================
        # 1. TIME UPDATE (PREDICTION)
        # ======================================================================
        # Construct Transition Matrix A and Input Vector B
        A = _mat_eye(self._dim)
        B: list[float] = [0.0] * self._dim

        # SOC prediction
        eta = self._params.coulombic_efficiency if i_load < 0 else 1.0
        B[0] = -(eta * dt) / q_cap

        # RC branch predictions
        for idx, branch in enumerate(self._params.rc_branches):
            state_idx = 1 + idx
            r_i = branch.resistance_r_ohm
            tau_i = branch.time_constant_tau_s
            decay = math.exp(-dt / tau_i) if tau_i > 0 else 0.0
            A[state_idx][state_idx] = decay
            B[state_idx] = r_i * (1.0 - decay)

        # State Predict: x_pred = A * x + B * I
        x_pred: list[float] = [0.0] * self._dim
        for i in range(self._dim):
            row_sum = sum(A[i][j] * self._x[j] for j in range(self._dim))
            x_pred[i] = row_sum + B[i] * i_load

        # Clamp predicted SOC
        x_pred[0] = clamp(x_pred[0], 0.0, 1.0)

        # Process Noise Matrix Q
        Q = _mat_zeros(self._dim, self._dim)
        Q[0][0] = self._q_soc * dt
        for i in range(1, self._dim):
            Q[i][i] = self._q_rc * dt

        # Covariance Predict: P_pred = A * P * A^T + Q
        A_P = _mat_mult(A, self._P)
        A_T = _mat_transpose(A)
        P_pred = _mat_add(_mat_mult(A_P, A_T), Q)

        # ======================================================================
        # 2. MEASUREMENT UPDATE (CORRECTION)
        # ======================================================================
        soc_pred = x_pred[0]
        v_oc = self._ocv_model.get_ocv(soc_pred, temp)
        v_r0 = i_load * self._params.series_resistance_r0_ohm
        v_rc_sum = sum(x_pred[1:])
        v_pred = v_oc - v_r0 - v_rc_sum

        # Measurement Jacobian C = [ dOCV/dSOC, -1, ..., -1 ]
        docv_dsoc = self._ocv_model.get_docv_dsoc(soc_pred, temp)
        assert_finite(docv_dsoc, "docv_dsoc")

        C = _mat_zeros(1, self._dim)
        C[0][0] = docv_dsoc
        for i in range(1, self._dim):
            C[0][i] = -1.0

        # Innovation: y_tilde = V_meas - V_pred
        innov = v_meas - v_pred
        assert_finite(innov, "voltage_innovation")

        # Innovation Covariance S = C * P_pred * C^T + R_v (scalar)
        C_T = _mat_transpose(C)
        P_C_T = _mat_mult(P_pred, C_T)
        C_P_C_T = _mat_mult(C, P_C_T)
        s_scalar = C_P_C_T[0][0] + self._r_v

        if s_scalar <= 0.0 or math.isnan(s_scalar) or math.isinf(s_scalar):
            raise EstimatorConvergenceError(
                f"EKF innovation covariance S became non-positive or non-finite: {s_scalar}.",
                estimator_id=self._estimator_id,
            )

        # Kalman Gain: K = P_pred * C^T / S (dimension: [dim x 1])
        K: list[list[float]] = _mat_zeros(self._dim, 1)
        for i in range(self._dim):
            K[i][0] = P_C_T[i][0] / s_scalar

        # State Update: x_post = x_pred + K * innov
        x_post: list[float] = [0.0] * self._dim
        for i in range(self._dim):
            x_post[i] = x_pred[i] + K[i][0] * innov

        # Strict SOC physical boundary clamping
        x_post[0] = clamp(x_post[0], 0.0, 1.0)
        self._x = x_post

        # Joseph-Stabilized Covariance Update:
        # P_post = (I - K*C) * P_pred * (I - K*C)^T + K * R_v * K^T
        I_mat = _mat_eye(self._dim)
        K_C = _mat_mult(K, C)
        I_minus_KC = _mat_zeros(self._dim, self._dim)
        for i in range(self._dim):
            for j in range(self._dim):
                I_minus_KC[i][j] = I_mat[i][j] - K_C[i][j]

        I_minus_KC_T = _mat_transpose(I_minus_KC)
        P_part1 = _mat_mult(_mat_mult(I_minus_KC, P_pred), I_minus_KC_T)

        K_T = _mat_transpose(K)
        K_R_KT = _mat_mult(K, K_T)
        P_part2 = _mat_zeros(self._dim, self._dim)
        for i in range(self._dim):
            for j in range(self._dim):
                P_part2[i][j] = K_R_KT[i][j] * self._r_v

        P_post = _mat_add(P_part1, P_part2)

        # Enforce exact symmetry: P = 0.5 * (P + P^T)
        for i in range(self._dim):
            for j in range(self._dim):
                sym_val = 0.5 * (P_post[i][j] + P_post[j][i])
                P_post[i][j] = sym_val

        # Verify positive variance
        if P_post[0][0] <= 0.0 or math.isnan(P_post[0][0]):
            raise EstimatorConvergenceError(
                f"EKF SOC variance non-positive: {P_post[0][0]}.",
                estimator_id=self._estimator_id,
            )

        self._P = P_post

        # 3. Construct Output
        next_state = current_state.with_updates(
            soc_fraction=self._x[0],
            soc_variance=self._P[0][0],
            temperature_c=temp,
            polarization_voltages_v=tuple(self._x[1:]),
            timestamp_ns=estimation_input.timestamp_ns,
        )

        return EstimationOutput(
            state=next_state,
            predicted_voltage_v=v_pred,
            innovation_v=innov,
            innovation_variance_v2=s_scalar,
            derivatives={"d_soc_dt": (self._x[0] - current_state.soc_fraction) / dt if dt > 0 else 0.0},
            diagnostics={
                "kalman_gain_soc": K[0][0],
                "docv_dsoc": docv_dsoc,
                "v_predicted": v_pred,
            },
        )

    def reset(self, initial_state: Optional[EstimationState] = None) -> None:
        """Resets EKF state vector and covariance matrix."""
        super().reset(initial_state)
