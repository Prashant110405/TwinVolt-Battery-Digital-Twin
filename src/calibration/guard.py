"""Parameter Bounding, Physical Consistency, and Safety Guard.

Enforces physical boundaries on identified ARX coefficients and recovered Equivalent Circuit
Model (ECM) parameters, ensuring strict thermodynamic plausibility.
"""

from dataclasses import dataclass
import math
from typing import Optional, Tuple

from src.calibration.types import RLSConfig


@dataclass(frozen=True)
class ParameterValidationResult:
    """Outcome of physical parameter validation and recovery."""

    is_r0_valid: bool
    is_secondary_valid: bool
    r0_ohm: float
    r1_ohm: Optional[float] = None
    c1_farad: Optional[float] = None
    tau1_s: Optional[float] = None
    rejection_reason: Optional[str] = None


class ParameterSafetyGuard:
    """Validator and physical parameter recovery guard for 1-RC ECM models."""

    def __init__(self, config: Optional[RLSConfig] = None) -> None:
        self._config = config or RLSConfig()
        self._rejection_count: int = 0

    @property
    def config(self) -> RLSConfig:
        """Attached RLS configuration."""
        return self._config

    @property
    def rejection_count(self) -> int:
        """Cumulative count of rejected parameter updates."""
        return self._rejection_count

    def validate_and_recover(
        self,
        a1: float,
        b0: float,
        b1: float,
        dt_s: float,
    ) -> ParameterValidationResult:
        """Validates discrete ARX coefficients and recovers physical ECM parameters.

        Formulas (Zero-Order Hold):
        - R0 = b0
        - tau1 = -dt / ln(a1)      (valid for 0 < a1 < 1)
        - R1 = (b1 + a1 * b0) / (1 - a1)
        - C1 = tau1 / R1

        Args:
            a1: ARX auto-regressive coefficient (alpha = exp(-dt/tau1)).
            b0: ARX instantaneous current coefficient (R0).
            b1: ARX delayed current coefficient (R1*(1-a1) - a1*R0).
            dt_s: Time step interval in seconds (> 0).

        Returns:
            ParameterValidationResult with recovered physical values.
        """
        # 1. Primary R0 Physical Validation
        r0_val = b0
        if math.isnan(r0_val) or math.isinf(r0_val) or not (self._config.r0_min_ohm <= r0_val <= self._config.r0_max_ohm):
            self._rejection_count += 1
            return ParameterValidationResult(
                is_r0_valid=False,
                is_secondary_valid=False,
                r0_ohm=r0_val,
                rejection_reason=f"R0 value {r0_val} is non-finite or outside [{self._config.r0_min_ohm}, {self._config.r0_max_ohm}] Ohm.",
            )

        # 2. Secondary (R1, C1, tau1) Mathematical & Physical Validation
        if dt_s <= 0.0:
            return ParameterValidationResult(
                is_r0_valid=True,
                is_secondary_valid=False,
                r0_ohm=r0_val,
                rejection_reason="dt_s is non-positive; secondary recovery skipped.",
            )

        # Condition A: 0.0 < a1 < 1.0 (strict requirement for stable decaying exponential)
        if math.isnan(a1) or math.isinf(a1) or not (0.0 < a1 < 1.0) or abs(1.0 - a1) < 1.0e-6:
            return ParameterValidationResult(
                is_r0_valid=True,
                is_secondary_valid=False,
                r0_ohm=r0_val,
                rejection_reason=f"a1={a1:.6f} outside valid interval (0.0, 1.0).",
            )

        # Condition B: b1 + a1 * b0 > 0.0 (ensures R1 > 0)
        numerator_r1 = b1 + (a1 * b0)
        if math.isnan(numerator_r1) or numerator_r1 <= 0.0:
            return ParameterValidationResult(
                is_r0_valid=True,
                is_secondary_valid=False,
                r0_ohm=r0_val,
                rejection_reason=f"Numerator (b1 + a1*b0) = {numerator_r1} is non-positive.",
            )

        # Physical recovery
        try:
            tau1_val = -dt_s / math.log(a1)
            r1_val = numerator_r1 / (1.0 - a1)
            c1_val = tau1_val / r1_val if r1_val > 0.0 else 0.0
        except Exception as exc:
            return ParameterValidationResult(
                is_r0_valid=True,
                is_secondary_valid=False,
                r0_ohm=r0_val,
                rejection_reason=f"Numerical exception during physical recovery: {exc}",
            )

        # Boundary checks on recovered parameters
        if not (self._config.r1_min_ohm <= r1_val <= self._config.r1_max_ohm):
            return ParameterValidationResult(
                is_r0_valid=True,
                is_secondary_valid=False,
                r0_ohm=r0_val,
                rejection_reason=f"R1={r1_val:.6f} Ohm outside [{self._config.r1_min_ohm}, {self._config.r1_max_ohm}].",
            )

        if not (self._config.c1_min_farad <= c1_val <= self._config.c1_max_farad):
            return ParameterValidationResult(
                is_r0_valid=True,
                is_secondary_valid=False,
                r0_ohm=r0_val,
                rejection_reason=f"C1={c1_val:.2f} F outside [{self._config.c1_min_farad}, {self._config.c1_max_farad}].",
            )

        if not (self._config.tau1_min_s <= tau1_val <= self._config.tau1_max_s):
            return ParameterValidationResult(
                is_r0_valid=True,
                is_secondary_valid=False,
                r0_ohm=r0_val,
                rejection_reason=f"tau1={tau1_val:.4f} s outside [{self._config.tau1_min_s}, {self._config.tau1_max_s}].",
            )

        return ParameterValidationResult(
            is_r0_valid=True,
            is_secondary_valid=True,
            r0_ohm=r0_val,
            r1_ohm=r1_val,
            c1_farad=c1_val,
            tau1_s=tau1_val,
            rejection_reason=None,
        )

    def reset(self) -> None:
        """Resets rejection counter."""
        self._rejection_count = 0
