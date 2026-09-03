"""Multi-Dimensional Parameter Validation Evidence Evaluator.

Evaluates Level 5.2 candidate online identified parameter sets without mutating live models,
generating evidence snapshots regarding bounds adherence, numerical confidence, cross-window
stability, and prospective residual improvement.
"""

from typing import Any, Mapping, Optional

from src.calibration.types import IdentifiedParameterSet
from src.validation.types import (
    ParameterEvidenceTier,
    ParameterValidationEvidence,
    ValidationConfig,
)

# Level 5.2 RLS ARX parameter vector definition: theta = [a1, b0, b1]
# Index 0: a1 (AR pole coefficient: alpha = exp(-dt/tau1))
# Index 1: b0 (instantaneous series resistance R0)
# Index 2: b1 (delayed input coefficient: R1*(1-a1) - a1*R0)
ARX_PARAMETER_ORDER: tuple[str, ...] = ("a1", "b0", "b1")
ARX_PARAMETER_INDICES: dict[str, int] = {name: idx for idx, name in enumerate(ARX_PARAMETER_ORDER)}
ARX_PARAMETER_INDICES["r0"] = 1  # b0 is R0 in physical Zero-Order-Hold recovery


def get_parameter_covariance(
    identified_params: Optional[IdentifiedParameterSet],
    parameter_name: str = "r0",
) -> Optional[float]:
    """Resolves estimation variance for a named parameter from IdentifiedParameterSet.

    Maps parameter names to actual Level 5.2 RLS parameter ordering:
    - 'a1': index 0 (P11)
    - 'b0' / 'r0': index 1 (P22)
    - 'b1': index 2 (P33)

    Args:
        identified_params: IdentifiedParameterSet from Level 5.2.
        parameter_name: Parameter key ("r0", "b0", "a1", "b1").

    Returns:
        Variance float or None if unavailable.
    """
    if identified_params is None:
        return None

    param_key = parameter_name.lower()
    # If r0 / b0 is requested, directly use the explicitly resolved r0_covariance field if present
    if param_key in ("r0", "b0") and identified_params.r0_covariance is not None:
        return float(identified_params.r0_covariance)

    idx = ARX_PARAMETER_INDICES.get(param_key)
    if idx is not None and identified_params.coefficient_covariance_diagonal is not None:
        if 0 <= idx < len(identified_params.coefficient_covariance_diagonal):
            return float(identified_params.coefficient_covariance_diagonal[idx])

    return None


class ParameterValidationEvaluator:
    """Evaluates empirical evidence strength for online identified battery model parameters."""

    def __init__(self, config: Optional[ValidationConfig] = None) -> None:
        self._config = config or ValidationConfig()
        self._prev_r0_ohm: Optional[float] = None
        self._stable_window_count: int = 0

    @property
    def config(self) -> ValidationConfig:
        """Attached validation configuration."""
        return self._config

    def evaluate(
        self,
        timestamp_ns: int,
        system_id: str,
        identified_params: Optional[IdentifiedParameterSet],
        nominal_rmse_v: Optional[float] = None,
        prospective_rmse_v: Optional[float] = None,
        sample_count: int = 0,
    ) -> ParameterValidationEvidence:
        """Evaluates empirical validation evidence for candidate identified parameters.

        Args:
            timestamp_ns: Current evaluation timestamp in nanoseconds.
            system_id: Battery system identifier.
            identified_params: Candidate IdentifiedParameterSet from Level 5.2 observer.
            nominal_rmse_v: Terminal voltage RMSE obtained with configured nominal parameters.
            prospective_rmse_v: Terminal voltage RMSE obtained with candidate parameters.
            sample_count: Number of observation samples evaluated in window.

        Returns:
            Immutable ParameterValidationEvidence instance.
        """
        if identified_params is None:
            return ParameterValidationEvidence(
                timestamp_ns=timestamp_ns,
                system_id=system_id,
                tier=ParameterEvidenceTier.EVIDENCE_REJECTED,
                bounds_satisfied=False,
                excitation_sufficient=False,
                covariance_acceptable=False,
                evaluated_sample_count=0,
                diagnostics={"reason": "No online identified parameters available."},
            )

        r0 = identified_params.r0_ohm
        r1 = identified_params.r1_ohm
        c1 = identified_params.c1_farad
        tau1 = identified_params.tau1_s
        gating = identified_params.gating_status

        # 1. Bounds Satisfaction (following Level 5.2 ParameterSafetyGuard contracts)
        # Primary R0 bounds: [0.0001, 1.0] Ohm
        bounds_ok = (0.0001 <= r0 <= 1.0)

        # Secondary parameter bounds (if present)
        if r1 is not None and not (0.0001 <= r1 <= 1.0):
            bounds_ok = False
        if c1 is not None and not (10.0 <= c1 <= 50000.0):
            bounds_ok = False
        if tau1 is not None and not (0.1 <= tau1 <= 300.0):
            bounds_ok = False

        # 2. Excitation Gating Status
        excitation_ok = gating in ("ACTIVE", "PRIMARY_ONLY_R0")

        # 3. Covariance / Statistical Variance Check via explicit parameter-to-index mapping
        r0_cov = get_parameter_covariance(identified_params, "r0")
        cov_ok = (r0_cov is not None and r0_cov <= self._config.max_parameter_r0_covariance)

        # 4. Cross-Window Stability / Drift Analysis
        drift_fraction: Optional[float] = None
        is_stable = False
        if self._prev_r0_ohm is not None and self._prev_r0_ohm > 0.0:
            drift_fraction = abs(r0 - self._prev_r0_ohm) / self._prev_r0_ohm
            if drift_fraction <= self._config.max_acceptable_drift_fraction:
                is_stable = True
                self._stable_window_count += 1
            else:
                self._stable_window_count = 0
        else:
            is_stable = True  # First window baseline

        self._prev_r0_ohm = r0

        # 5. Prospective Residual Reduction
        delta_rmse: Optional[float] = None
        residual_improved = False
        if nominal_rmse_v is not None and prospective_rmse_v is not None:
            delta_rmse = nominal_rmse_v - prospective_rmse_v
            residual_improved = (delta_rmse > 0.0)

        # 6. Classify Evidence Tier
        if not bounds_ok:
            tier = ParameterEvidenceTier.EVIDENCE_REJECTED
            reason = "Physical parameter bounds violated."
        elif not excitation_ok:
            tier = ParameterEvidenceTier.EVIDENCE_WEAK
            reason = f"Gating status {gating} indicates insufficient excitation."
        elif not is_stable:
            tier = ParameterEvidenceTier.EVIDENCE_WEAK
            drift_pct = (drift_fraction or 0.0) * 100.0
            reason = f"Parameter drift ({drift_pct:.1f}%) exceeded acceptable limit."
        elif residual_improved and is_stable and cov_ok:
            tier = ParameterEvidenceTier.EVIDENCE_STRONG
            reason = f"Candidate parameters reduced voltage RMSE by {delta_rmse:.4f}V with stable drift."
        elif bounds_ok and cov_ok:
            tier = ParameterEvidenceTier.EVIDENCE_MODERATE
            reason = "Valid bounds and covariance; prospective residual neutral or dynamic branches unexcited."
        else:
            tier = ParameterEvidenceTier.EVIDENCE_WEAK
            reason = "High estimation variance or parameter drift detected across windows."

        return ParameterValidationEvidence(
            timestamp_ns=timestamp_ns,
            system_id=system_id,
            tier=tier,
            bounds_satisfied=bounds_ok,
            excitation_sufficient=excitation_ok,
            covariance_acceptable=cov_ok,
            cross_window_drift_fraction=drift_fraction,
            prospective_rmse_v=prospective_rmse_v,
            nominal_rmse_v=nominal_rmse_v,
            delta_rmse_v=delta_rmse,
            evaluated_sample_count=sample_count,
            diagnostics={
                "evidence_reason": reason,
                "stable_window_count": self._stable_window_count,
                "identified_gating_status": gating,
                "resolved_r0_covariance": r0_cov,
            },
        )

    def reset(self) -> None:
        """Resets parameter evaluator history."""
        self._prev_r0_ohm = None
        self._stable_window_count = 0
