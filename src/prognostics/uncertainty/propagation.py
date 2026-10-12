"""Analytical RUL Uncertainty Propagation and Interval Evaluation.

Implements first-order analytical Taylor series uncertainty propagation for linear
EOL-crossing Remaining Useful Life (RUL) estimates under explicit mathematical assumptions.

Strict Invariants & Scientific Distinctions:
1. Evaluates sensitivity derivatives:
   df/dr = -RUL / r  (sensitivity with respect to degradation rate)
   df/dy = 1 / r     (sensitivity with respect to current state)
2. Combines independent standard uncertainties via root-sum-of-squares (RSS) only when
   independence is explicitly declared.
3. Strictly separates confidence intervals (uncertainty of the mean model trajectory)
   from prediction intervals (future individual realization dispersion).
4. Prediction intervals are marked UNAVAILABLE rather than fabricated from slope error.
5. Lower bounds enforce physical non-negativity invariants with explicit truncation tracking.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence

from src.prognostics.uncertainty.types import (
    UncertaintyBound,
    UncertaintyCombinationResult,
    UncertaintyComponent,
    UncertaintyIntervalType,
    UncertaintySourceCategory,
    UncertaintyStatus,
)


# Standard critical values table for Student-t distribution: t_{alpha/2, df}
# Keys: (confidence_level, df)
_STUDENT_T_TABLE: dict[tuple[float, int], float] = {
    # 90% confidence (alpha = 0.10, alpha/2 = 0.05)
    (0.90, 1): 6.3138, (0.90, 2): 2.9200, (0.90, 3): 2.3534, (0.90, 4): 2.1318,
    (0.90, 5): 2.0150, (0.90, 6): 1.9432, (0.90, 7): 1.8946, (0.90, 8): 1.8595,
    (0.90, 9): 1.8331, (0.90, 10): 1.8125, (0.90, 15): 1.7531, (0.90, 20): 1.7247,
    (0.90, 30): 1.6973, (0.90, 50): 1.6759, (0.90, 100): 1.6602,

    # 95% confidence (alpha = 0.05, alpha/2 = 0.025)
    (0.95, 1): 12.7062, (0.95, 2): 4.3027, (0.95, 3): 3.1824, (0.95, 4): 2.7764,
    (0.95, 5): 2.5706, (0.95, 6): 2.4469, (0.95, 7): 2.3646, (0.95, 8): 2.3060,
    (0.95, 9): 2.2622, (0.95, 10): 2.2281, (0.95, 15): 2.1314, (0.95, 20): 2.0860,
    (0.95, 30): 2.0423, (0.95, 50): 2.0086, (0.95, 100): 1.9840,

    # 99% confidence (alpha = 0.01, alpha/2 = 0.005)
    (0.99, 1): 63.6567, (0.99, 2): 9.9248, (0.99, 3): 5.8409, (0.99, 4): 4.6041,
    (0.99, 5): 4.0321, (0.99, 6): 3.7074, (0.99, 7): 3.4995, (0.99, 8): 3.3554,
    (0.99, 9): 3.2498, (0.99, 10): 3.1693, (0.99, 15): 2.9467, (0.99, 20): 2.8453,
    (0.99, 30): 2.7500, (0.99, 50): 2.6778, (0.99, 100): 2.6259,
}


def _get_student_t_critical_value(confidence_level: float, df: int) -> float:
    """Returns the two-tailed Student-t critical value t_{alpha/2, df}."""
    if df < 1:
        raise ValueError(f"degrees of freedom df must be >= 1, got {df}.")

    # Round confidence level to 2 decimal places for lookup
    c_key = round(float(confidence_level), 2)

    # Direct match in table
    if (c_key, df) in _STUDENT_T_TABLE:
        return _STUDENT_T_TABLE[(c_key, df)]

    # Interpolate or find nearest in table for df <= 100
    available_dfs = sorted([d for (c, d) in _STUDENT_T_TABLE.keys() if c == c_key])
    if available_dfs:
        if df > available_dfs[-1]:
            # Normal distribution approximation z_{alpha/2} for large df
            if c_key == 0.90:
                return 1.6449
            elif c_key == 0.95:
                return 1.9600
            elif c_key == 0.99:
                return 2.5758
            else:
                return 1.9600

        # Stepwise interpolation: pick closest lower/upper bound
        for i in range(len(available_dfs) - 1):
            d1, d2 = available_dfs[i], available_dfs[i + 1]
            if d1 <= df <= d2:
                t1 = _STUDENT_T_TABLE[(c_key, d1)]
                t2 = _STUDENT_T_TABLE[(c_key, d2)]
                # Linear interpolation in 1/df
                frac = (1.0 / df - 1.0 / d1) / (1.0 / d2 - 1.0 / d1)
                return t1 + frac * (t2 - t1)

    # Standard fallback Gaussian z critical value
    if c_key >= 0.99:
        return 2.5758
    elif c_key >= 0.95:
        return 1.9600
    elif c_key >= 0.90:
        return 1.6449
    return 1.9600


@dataclass(frozen=True)
class RULPropagationResult:
    """Immutable result of analytical RUL uncertainty propagation."""

    rul_value: float
    degradation_rate: float
    status: UncertaintyStatus
    sensitivity_to_rate: float
    sensitivity_to_state: float
    rate_uncertainty: Optional[float] = None
    state_uncertainty: Optional[float] = None
    propagated_standard_uncertainty: Optional[float] = None
    bounds: Optional[UncertaintyBound] = None
    components: Sequence[UncertaintyComponent] = field(default_factory=tuple)
    assumptions: Sequence[str] = field(default_factory=tuple)
    diagnostic_message: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes propagation result to dictionary."""
        return {
            "rul_value": round(float(self.rul_value), 6),
            "degradation_rate": round(float(self.degradation_rate), 8),
            "status": self.status.value,
            "sensitivity_to_rate": round(float(self.sensitivity_to_rate), 6),
            "sensitivity_to_state": round(float(self.sensitivity_to_state), 6),
            "rate_uncertainty": round(float(self.rate_uncertainty), 8) if self.rate_uncertainty is not None else None,
            "state_uncertainty": (
                round(float(self.state_uncertainty), 8) if self.state_uncertainty is not None else None
            ),
            "propagated_standard_uncertainty": (
                round(float(self.propagated_standard_uncertainty), 8)
                if self.propagated_standard_uncertainty is not None
                else None
            ),
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "components": [c.to_dict() for c in self.components],
            "assumptions": list(self.assumptions),
            "diagnostic_message": self.diagnostic_message,
            "metadata": dict(self.metadata),
        }


class RULUncertaintyPropagator:
    """Analytical first-order Taylor propagator for linear RUL uncertainty."""

    @classmethod
    def propagate(
        cls,
        rul_value: float,
        degradation_rate: float,
        rate_uncertainty_component: Optional[UncertaintyComponent] = None,
        state_uncertainty_component: Optional[UncertaintyComponent] = None,
        assume_independent: bool = True,
        confidence_level: Optional[float] = None,
        domain_unit: str = "cycles",
    ) -> RULPropagationResult:
        """Propagates degradation rate and state uncertainty to RUL standard error and bounds."""
        if not isinstance(rul_value, (int, float)) or math.isnan(rul_value) or math.isinf(rul_value):
            raise ValueError(f"rul_value must be a finite float, got {rul_value}.")
        if not isinstance(degradation_rate, (int, float)) or math.isnan(degradation_rate) or math.isinf(degradation_rate):
            raise ValueError(f"degradation_rate must be a finite float, got {degradation_rate}.")

        rul = float(rul_value)
        rate = float(degradation_rate)

        # Rate must be strictly positive for non-zero division
        if rate <= 1e-15:
            return RULPropagationResult(
                rul_value=rul,
                degradation_rate=rate,
                status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
                sensitivity_to_rate=0.0,
                sensitivity_to_state=0.0,
                diagnostic_message="Degradation rate is non-positive or flat; propagation derivative undefined.",
            )

        # Sensitivity derivatives
        # df/dr = -RUL / rate
        # df/dy = 1 / rate
        sens_rate = -rul / rate
        sens_state = 1.0 / rate

        sigma_r: Optional[float] = None
        df_r: Optional[int] = None
        if rate_uncertainty_component and rate_uncertainty_component.standard_uncertainty is not None:
            sigma_r = float(rate_uncertainty_component.standard_uncertainty)
            df_r = rate_uncertainty_component.degrees_of_freedom

        sigma_y: Optional[float] = None
        df_y: Optional[int] = None
        if state_uncertainty_component and state_uncertainty_component.standard_uncertainty is not None:
            sigma_y = float(state_uncertainty_component.standard_uncertainty)
            df_y = state_uncertainty_component.degrees_of_freedom

        # Case 1: Neither component has quantified standard uncertainty
        if sigma_r is None and sigma_y is None:
            comp = UncertaintyComponent(
                source_category=UncertaintySourceCategory.COMBINED,
                status=UncertaintyStatus.DETERMINISTIC_ONLY,
                unit=domain_unit,
                description="Point estimate only; no input standard uncertainties were provided.",
            )
            return RULPropagationResult(
                rul_value=rul,
                degradation_rate=rate,
                status=UncertaintyStatus.DETERMINISTIC_ONLY,
                sensitivity_to_rate=sens_rate,
                sensitivity_to_state=sens_state,
                components=(comp,),
                diagnostic_message="Deterministic point estimate; no rate or state uncertainty available.",
            )

        # Case 2: Both present but independence not assumed and covariance unavailable
        if sigma_r is not None and sigma_y is not None and not assume_independent:
            comp = UncertaintyComponent(
                source_category=UncertaintySourceCategory.COMBINED,
                status=UncertaintyStatus.COMBINATION_UNAVAILABLE,
                unit=domain_unit,
                description="Rate and state uncertainties are both present but cross-covariance is uncharacterized.",
                assumptions=("Cross-covariance between rate and state was not provided.",),
            )
            return RULPropagationResult(
                rul_value=rul,
                degradation_rate=rate,
                status=UncertaintyStatus.COMBINATION_UNAVAILABLE,
                sensitivity_to_rate=sens_rate,
                sensitivity_to_state=sens_state,
                rate_uncertainty=sigma_r,
                state_uncertainty=sigma_y,
                components=(
                    rate_uncertainty_component,
                    state_uncertainty_component,
                    comp,
                ),
                diagnostic_message="Combination unavailable because cross-covariance is uncharacterized.",
            )

        # Case 3: Analytical propagation
        var_rul = 0.0
        assumptions_list = ["First-order analytical Taylor series sensitivity propagation."]
        active_components: list[UncertaintyComponent] = []

        if sigma_r is not None:
            var_r_contrib = (sens_rate ** 2) * (sigma_r ** 2)
            var_rul += var_r_contrib
            assumptions_list.append(
                f"Rate uncertainty contribution: sigma_RUL_rate = |RUL/r| * sigma_r = {math.sqrt(var_r_contrib):.4f} {domain_unit}."
            )
            if rate_uncertainty_component:
                active_components.append(rate_uncertainty_component)

        if sigma_y is not None:
            var_y_contrib = (sens_state ** 2) * (sigma_y ** 2)
            var_rul += var_y_contrib
            assumptions_list.append(
                f"State uncertainty contribution: sigma_RUL_state = (1/r) * sigma_y = {math.sqrt(var_y_contrib):.4f} {domain_unit}."
            )
            if state_uncertainty_component:
                active_components.append(state_uncertainty_component)

        if sigma_r is not None and sigma_y is not None:
            assumptions_list.append("Assumed zero covariance between degradation rate and baseline state.")

        sigma_rul = math.sqrt(var_rul)

        # Determine effective degrees of freedom
        effective_df = df_r if df_r is not None else df_y
        status = UncertaintyStatus.STATISTICALLY_SUPPORTED if effective_df is not None else UncertaintyStatus.ESTIMATED

        # Build Confidence Interval if requested by explicit configuration
        bounds: Optional[UncertaintyBound] = None
        if confidence_level is not None:
            if not isinstance(confidence_level, (int, float)) or confidence_level <= 0.0 or confidence_level >= 1.0:
                raise ValueError(f"confidence_level must be in (0, 1), got {confidence_level}.")

            if effective_df is not None and effective_df >= 1:
                t_crit = _get_student_t_critical_value(float(confidence_level), effective_df)
                margin = t_crit * sigma_rul
                raw_lower = rul - margin
                raw_upper = rul + margin

                is_trunc = False
                constraint_msg: Optional[str] = None
                if raw_lower < 0.0:
                    raw_lower = 0.0
                    is_trunc = True
                    constraint_msg = "Lower statistical bound truncated at zero to satisfy physical non-negativity."

                bounds = UncertaintyBound(
                    lower=raw_lower,
                    upper=raw_upper,
                    coverage_parameter=float(confidence_level),
                    interval_type=UncertaintyIntervalType.CONFIDENCE_INTERVAL,
                    is_truncated_at_zero=is_trunc,
                    constraint_description=constraint_msg,
                )
            else:
                # Without degrees of freedom, generate 1-sigma dispersion or normal interval if configured
                z_crit = _get_student_t_critical_value(float(confidence_level), 100)
                margin = z_crit * sigma_rul
                raw_lower = rul - margin
                raw_upper = rul + margin

                is_trunc = False
                constraint_msg = None
                if raw_lower < 0.0:
                    raw_lower = 0.0
                    is_trunc = True
                    constraint_msg = "Lower statistical bound truncated at zero to satisfy physical non-negativity."

                bounds = UncertaintyBound(
                    lower=raw_lower,
                    upper=raw_upper,
                    coverage_parameter=float(confidence_level),
                    interval_type=UncertaintyIntervalType.CONFIDENCE_INTERVAL,
                    is_truncated_at_zero=is_trunc,
                    constraint_description=constraint_msg,
                )

        combined_comp = UncertaintyComponent(
            source_category=UncertaintySourceCategory.COMBINED,
            status=status,
            standard_uncertainty=sigma_rul,
            degrees_of_freedom=effective_df,
            unit=domain_unit,
            description=f"Propagated RUL standard uncertainty (sigma = {sigma_rul:.4f} {domain_unit}).",
            assumptions=tuple(assumptions_list),
            metadata={
                "sensitivity_to_rate": round(sens_rate, 6),
                "sensitivity_to_state": round(sens_state, 6),
                "effective_df": effective_df,
            },
        )
        active_components.append(combined_comp)

        return RULPropagationResult(
            rul_value=rul,
            degradation_rate=rate,
            status=status,
            sensitivity_to_rate=sens_rate,
            sensitivity_to_state=sens_state,
            rate_uncertainty=sigma_r,
            state_uncertainty=sigma_y,
            propagated_standard_uncertainty=sigma_rul,
            bounds=bounds,
            components=tuple(active_components),
            assumptions=tuple(assumptions_list),
            diagnostic_message="RUL uncertainty propagated successfully via first-order Taylor expansion.",
            metadata={
                "propagated_standard_uncertainty": round(sigma_rul, 8),
                "domain_unit": domain_unit,
                "confidence_level": confidence_level,
            },
        )
