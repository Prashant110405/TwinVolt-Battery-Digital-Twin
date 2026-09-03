"""Recursive Least Squares (RLS) Parameter Identification Engine.

Implements Zero-Order-Hold discrete-time ARX parameter identification with genuine
Bierman U-D Covariance Factorization (Bierman-Thornton), windowed persistent excitation
gating, and physical parameter recovery for battery digital twins.
"""

from dataclasses import dataclass
import math
from typing import Any, Optional, Tuple

from src.calibration.gating import ExcitationDetector, ExcitationGatingResult
from src.calibration.guard import ParameterSafetyGuard, ParameterValidationResult
from src.calibration.types import IdentifiedParameterSet, ParameterStateClassification, RLSConfig
from src.telemetry.snapshots import TelemetrySnapshot


class UDCovarianceFactorizer:
    """Bierman U-D Covariance Factorization (P = U * D * U^T) for 3-parameter RLS.

    Maintains covariance strictly in factored form where U is unit upper triangular
    and D is a diagonal matrix of strictly positive variance factors.
    """

    def __init__(self, dim: int = 3, initial_variance: float = 100.0) -> None:
        self.dim = dim
        # D elements [d1, d2, d3]
        self.d = [max(1.0e-6, float(initial_variance)) for _ in range(dim)]
        # U upper triangular elements: u_12, u_13, u_23
        # Matrix U = [[1.0, u12, u13], [0.0, 1.0, u23], [0.0, 0.0, 1.0]]
        self.u12 = 0.0
        self.u13 = 0.0
        self.u23 = 0.0

    def get_covariance_matrix(self) -> list[list[float]]:
        """Reconstructs the full 3x3 covariance matrix P = U * D * U^T."""
        d1, d2, d3 = self.d[0], self.d[1], self.d[2]
        u12, u13, u23 = self.u12, self.u13, self.u23

        p11 = d1 + (u12 ** 2) * d2 + (u13 ** 2) * d3
        p12 = u12 * d2 + u13 * u23 * d3
        p13 = u13 * d3
        p22 = d2 + (u23 ** 2) * d3
        p23 = u23 * d3
        p33 = d3

        return [
            [p11, p12, p13],
            [p12, p22, p23],
            [p13, p23, p33],
        ]

    def get_diagonal_elements(self) -> tuple[float, float, float]:
        """Returns the main diagonal variance elements (P11, P22, P33)."""
        d1, d2, d3 = self.d[0], self.d[1], self.d[2]
        u12, u13, u23 = self.u12, self.u13, self.u23

        p11 = d1 + (u12 ** 2) * d2 + (u13 ** 2) * d3
        p22 = d2 + (u23 ** 2) * d3
        p33 = d3
        return (p11, p22, p33)

    def get_trace(self) -> float:
        """Returns Tr(P) = P11 + P22 + P33."""
        p11, p22, p33 = self.get_diagonal_elements()
        return p11 + p22 + p33

    def inflate(self, factor: float) -> None:
        """Inflates covariance factors by a scalar multiplier (e.g. after telemetry gap)."""
        if factor > 0.0:
            self.d = [di * factor for di in self.d]

    def apply_trace_bounds(self, min_trace: float, max_trace: float) -> None:
        """Clamps covariance trace within [min_trace, max_trace] to prevent windup or sleep."""
        tr = self.get_trace()
        if tr > max_trace and tr > 0.0:
            scale = max_trace / tr
            self.d = [di * scale for di in self.d]
        elif tr < min_trace and tr > 0.0:
            scale = min_trace / tr
            self.d = [di * scale for di in self.d]

    def update(
        self,
        phi: list[float],
        lam: float,
    ) -> Tuple[list[float], float]:
        """Executes Bierman measurement update for U-D factors and computes Kalman gain K.

        Args:
            phi: Regressor vector [phi_1, phi_2, phi_3].
            lam: Exponential forgetting factor lambda in [0.98, 1.0].

        Returns:
            Tuple of (Kalman gain vector K, denominator alpha_M).
        """
        # 1. f = U^T * phi
        f1 = phi[0]
        f2 = self.u12 * phi[0] + phi[1]
        f3 = self.u13 * phi[0] + self.u23 * phi[1] + phi[2]
        f = [f1, f2, f3]

        # 2. g = D * f
        g1 = self.d[0] * f1
        g2 = self.d[1] * f2
        g3 = self.d[2] * f3
        g = [g1, g2, g3]

        # 3. Bierman recursive update for j = 1, 2, 3
        # Initialize
        alpha_prev = max(1.0e-12, lam)
        k_bar = [0.0, 0.0, 0.0]
        new_d = [0.0, 0.0, 0.0]
        new_u12 = self.u12
        new_u13 = self.u13
        new_u23 = self.u23

        # --- Step j = 1 ---
        alpha_1 = alpha_prev + f[0] * g[0]
        beta_1 = alpha_prev
        new_d[0] = (self.d[0] * beta_1) / (lam * alpha_1)
        k_bar[0] = g[0]
        alpha_prev = alpha_1

        # --- Step j = 2 ---
        alpha_2 = alpha_prev + f[1] * g[1]
        beta_2 = alpha_prev
        new_d[1] = (self.d[1] * beta_2) / (lam * alpha_2)
        v2 = g[1]
        new_u12 = self.u12 - (f[1] / beta_2) * k_bar[0]
        k_bar[0] = k_bar[0] + v2 * self.u12
        k_bar[1] = v2
        alpha_prev = alpha_2

        # --- Step j = 3 ---
        alpha_3 = alpha_prev + f[2] * g[2]
        beta_3 = alpha_prev
        new_d[2] = (self.d[2] * beta_3) / (lam * alpha_3)
        v3 = g[2]
        new_u13 = self.u13 - (f[2] / beta_3) * k_bar[0]
        new_u23 = self.u23 - (f[2] / beta_3) * k_bar[1]
        k_bar[0] = k_bar[0] + v3 * self.u13
        k_bar[1] = v3 * self.u23 + k_bar[1]
        k_bar[2] = v3

        # Update internal factors
        self.d = [max(1.0e-10, di) for di in new_d]
        self.u12 = new_u12
        self.u13 = new_u13
        self.u23 = new_u23

        # Compute gain K = k_bar / alpha_3
        k_gain = [k_bar[0] / alpha_3, k_bar[1] / alpha_3, k_bar[2] / alpha_3]
        return k_gain, alpha_3

    def reset(self, initial_variance: float = 100.0) -> None:
        """Resets factorizer to initial isotropic diagonal covariance."""
        self.d = [max(1.0e-6, float(initial_variance)) for _ in range(self.dim)]
        self.u12 = 0.0
        self.u13 = 0.0
        self.u23 = 0.0


class RLSParameterIdentifier:
    """Online 1-RC ARX Recursive Least Squares Parameter Identification Engine."""

    def __init__(
        self,
        system_id: str,
        nominal_r0_ohm: float = 0.025,
        nominal_r1_ohm: Optional[float] = 0.015,
        nominal_c1_farad: Optional[float] = 1000.0,
        config: Optional[RLSConfig] = None,
    ) -> None:
        self._system_id = system_id
        self._config = config or RLSConfig()
        self._nominal_r0 = float(nominal_r0_ohm)
        self._nominal_r1 = float(nominal_r1_ohm) if nominal_r1_ohm is not None else None
        self._nominal_c1 = float(nominal_c1_farad) if nominal_c1_farad is not None else None

        # Components
        self._ud = UDCovarianceFactorizer(
            dim=3,
            initial_variance=self._config.initial_covariance_diagonal,
        )
        self._gating = ExcitationDetector(config=self._config)
        self._guard = ParameterSafetyGuard(config=self._config)

        # Initial Parameter Vector theta = [a1, b0, b1]
        dt_ref = 1.0
        tau_ref = (self._nominal_r1 * self._nominal_c1) if (self._nominal_r1 and self._nominal_c1) else 15.0
        a1_init = math.exp(-dt_ref / tau_ref)
        b0_init = self._nominal_r0
        r1_init = self._nominal_r1 if self._nominal_r1 else 0.015
        b1_init = r1_init * (1.0 - a1_init) - (a1_init * b0_init)

        self._theta = [a1_init, b0_init, b1_init]
        self._prev_y: Optional[float] = None
        self._prev_i: Optional[float] = None
        self._sample_count: int = 0
        self._latest_parameter_set: Optional[IdentifiedParameterSet] = None

    @property
    def system_id(self) -> str:
        """System identifier."""
        return self._system_id

    @property
    def config(self) -> RLSConfig:
        """Attached RLS configuration."""
        return self._config

    @property
    def latest_parameters(self) -> Optional[IdentifiedParameterSet]:
        """Most recent identified parameter snapshot."""
        return self._latest_parameter_set

    def update(
        self,
        snapshot: TelemetrySnapshot,
        sync_output: Any,
        dt_s: Optional[float] = None,
    ) -> IdentifiedParameterSet:
        """Executes a single recursive parameter identification step.

        Args:
            snapshot: Incoming TelemetrySnapshot.
            sync_output: Result from TwinSynchronizer step containing model outputs and residuals.
            dt_s: Effective discrete step interval in seconds.

        Returns:
            Updated immutable IdentifiedParameterSet.
        """
        effective_dt = dt_s if (dt_s is not None and dt_s > 0.0) else 1.0

        # Extract SOC estimate and voltage residual
        soc_est = 0.5
        v_res = None
        v_oc = None
        v_term = snapshot.pack_voltage_v

        if hasattr(sync_output, "model_output") and sync_output.model_output is not None:
            soc_est = sync_output.model_output.state.soc_fraction
            v_oc = sync_output.model_output.open_circuit_voltage_v
        if hasattr(sync_output, "residuals") and sync_output.residuals:
            v_res = sync_output.residuals.get("voltage_residual_v")

        # 1. Gating & Observability Evaluation
        gating_res = self._gating.evaluate(
            snapshot=snapshot,
            soc_estimate=soc_est,
            voltage_residual_v=v_res,
            dt_s=effective_dt,
        )

        # Handle Telemetry Gap
        if gating_res.is_telemetry_gap:
            self._ud.inflate(self._config.gap_covariance_inflation_factor)
            self._prev_y = None
            self._prev_i = None

        # If observation is not a valid step or missing current/voltage
        current_a = snapshot.pack_current_a
        if (
            not gating_res.is_valid_step
            or current_a is None
            or v_term is None
            or v_oc is None
        ):
            return self._build_snapshot(
                timestamp_ns=snapshot.timestamp_ns,
                gating_status=gating_res.gating_status,
                rejection_reason=gating_res.reason,
            )

        # Instantaneous overpotential observation: y[k] = Voc[k] - Vterm[k]
        y_k = v_oc - v_term

        # Check if we have delayed regressor components (y[k-1], I[k-1])
        if self._prev_y is None or self._prev_i is None:
            self._prev_y = y_k
            self._prev_i = current_a
            return self._build_snapshot(
                timestamp_ns=snapshot.timestamp_ns,
                gating_status="INITIALIZING_REGRESSORS",
                rejection_reason="First valid sample; initial regressor buffer populated.",
            )

        # Construct Regressor phi[k] = [y[k-1], I[k], I[k-1]]
        phi_k = [self._prev_y, current_a, self._prev_i]

        # 2. Check if update is gated due to insufficient excitation or operating regime
        if not gating_res.can_update_r0:
            self._prev_y = y_k
            self._prev_i = current_a
            return self._build_snapshot(
                timestamp_ns=snapshot.timestamp_ns,
                gating_status=gating_res.gating_status,
                rejection_reason=gating_res.reason,
            )

        # 3. Execute Bierman U-D Covariance RLS Update
        try:
            # Innovation e[k] = y[k] - phi^T * theta[k-1]
            y_pred = phi_k[0] * self._theta[0] + phi_k[1] * self._theta[1] + phi_k[2] * self._theta[2]
            e_k = y_k - y_pred

            # Innovation gating
            if abs(e_k) > self._config.max_voltage_residual_v:
                self._prev_y = y_k
                self._prev_i = current_a
                return self._build_snapshot(
                    timestamp_ns=snapshot.timestamp_ns,
                    gating_status="INNOVATION_OUTLIER",
                    rejection_reason=f"Innovation error {abs(e_k):.4f}V exceeded threshold.",
                )

            # U-D Measurement Update
            k_gain, _ = self._ud.update(phi=phi_k, lam=self._config.forgetting_factor_lambda)

            # Candidate Parameter Vector Update
            candidate_theta = [
                self._theta[0] + k_gain[0] * e_k,
                self._theta[1] + k_gain[1] * e_k,
                self._theta[2] + k_gain[2] * e_k,
            ]

            # Enforce trace bounds
            self._ud.apply_trace_bounds(
                min_trace=self._config.min_covariance_trace,
                max_trace=self._config.max_covariance_trace,
            )

            # 4. Parameter Safety Guard & Physical Recovery
            val_result = self._guard.validate_and_recover(
                a1=candidate_theta[0],
                b0=candidate_theta[1],
                b1=candidate_theta[2],
                dt_s=effective_dt,
            )

            if val_result.is_r0_valid:
                # Accept RLS update
                self._theta = candidate_theta
                self._sample_count += 1
                gating_status = "ACTIVE" if (gating_res.can_update_secondary and val_result.is_secondary_valid) else "PRIMARY_ONLY_R0"
            else:
                gating_status = "UPDATE_REJECTED"

            self._prev_y = y_k
            self._prev_i = current_a

            return self._build_snapshot(
                timestamp_ns=snapshot.timestamp_ns,
                gating_status=gating_status,
                rejection_reason=val_result.rejection_reason,
                val_result=val_result if val_result.is_r0_valid else None,
            )

        except Exception as exc:
            self._prev_y = y_k
            self._prev_i = current_a
            return self._build_snapshot(
                timestamp_ns=snapshot.timestamp_ns,
                gating_status="NUMERICAL_ERROR",
                rejection_reason=str(exc),
            )

    def _build_snapshot(
        self,
        timestamp_ns: int,
        gating_status: str,
        rejection_reason: Optional[str] = None,
        val_result: Optional[ParameterValidationResult] = None,
    ) -> IdentifiedParameterSet:
        """Constructs an immutable IdentifiedParameterSet snapshot."""
        diag = self._ud.get_diagonal_elements()
        # R0 is the 2nd parameter (index 1), corresponding to P22
        r0_cov = diag[1]

        r0_val = self._theta[1]
        r1_val = None
        c1_val = None
        tau1_val = None

        if val_result is not None:
            r0_val = val_result.r0_ohm
            if val_result.is_secondary_valid:
                r1_val = val_result.r1_ohm
                c1_val = val_result.c1_farad
                tau1_val = val_result.tau1_s
        else:
            # Fallback recovery check on current stable theta
            fallback_val = self._guard.validate_and_recover(
                a1=self._theta[0],
                b0=self._theta[1],
                b1=self._theta[2],
                dt_s=1.0,
            )
            if fallback_val.is_r0_valid:
                r0_val = fallback_val.r0_ohm
                if fallback_val.is_secondary_valid:
                    r1_val = fallback_val.r1_ohm
                    c1_val = fallback_val.c1_farad
                    tau1_val = fallback_val.tau1_s

        metadata: dict[str, Any] = {
            "theta_arx": [round(th, 6) for th in self._theta],
            "rejections": self._guard.rejection_count,
        }
        if rejection_reason is not None:
            metadata["diagnostic_reason"] = rejection_reason

        param_set = IdentifiedParameterSet(
            timestamp_ns=timestamp_ns,
            system_id=self._system_id,
            r0_ohm=r0_val,
            r1_ohm=r1_val,
            c1_farad=c1_val,
            tau1_s=tau1_val,
            r0_covariance=r0_cov,
            coefficient_covariance_diagonal=diag,
            sample_count=self._sample_count,
            classification=ParameterStateClassification.ONLINE_IDENTIFIED,
            gating_status=gating_status,
            metadata=metadata,
        )

        self._latest_parameter_set = param_set
        return param_set

    def reset(self) -> None:
        """Resets RLS estimator state, covariance, and history buffers."""
        self._ud.reset(initial_variance=self._config.initial_covariance_diagonal)
        self._gating.reset()
        self._guard.reset()
        self._prev_y = None
        self._prev_i = None
        self._sample_count = 0
        self._latest_parameter_set = None
