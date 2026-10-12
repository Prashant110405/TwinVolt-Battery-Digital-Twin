"""Trajectory and Trend Uncertainty Evaluation for Battery Prognostics.

Calculates rigorous descriptive Ordinary Least Squares (OLS) residual statistics,
degrees of freedom, residual standard error, slope standard error, and intercept
standard error for historical degradation trajectories.

Crucial Distinction:
Ordinary Least Squares (OLS) and descriptive R² are historical descriptive metrics
characterizing explanatory fit under the chosen linear model. They do NOT establish
future RUL predictive confidence or universal physical battery behavior.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence, Tuple

from src.prognostics.uncertainty.types import (
    UncertaintyComponent,
    UncertaintySourceCategory,
    UncertaintyStatus,
)


@dataclass(frozen=True)
class TrajectoryTrendStatistics:
    """Immutable mathematical and descriptive statistics for a degradation trajectory trend."""

    sample_count: int
    degrees_of_freedom: int
    status: UncertaintyStatus
    slope: Optional[float] = None
    intercept: Optional[float] = None
    mean_x: Optional[float] = None
    mean_y: Optional[float] = None
    sum_squares_xx: Optional[float] = None
    sum_squares_yy: Optional[float] = None
    sum_squares_xy: Optional[float] = None
    residual_sum_of_squares: Optional[float] = None
    residual_variance: Optional[float] = None
    residual_standard_error: Optional[float] = None
    slope_standard_error: Optional[float] = None
    intercept_standard_error: Optional[float] = None
    r_squared: Optional[float] = None
    unit_x: str = ""
    unit_y: str = ""
    slope_component: Optional[UncertaintyComponent] = None
    diagnostic_message: Optional[str] = None
    method_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes trajectory trend statistics to dictionary."""
        return {
            "sample_count": self.sample_count,
            "degrees_of_freedom": self.degrees_of_freedom,
            "status": self.status.value,
            "slope": round(float(self.slope), 8) if self.slope is not None else None,
            "intercept": round(float(self.intercept), 6) if self.intercept is not None else None,
            "mean_x": round(float(self.mean_x), 6) if self.mean_x is not None else None,
            "mean_y": round(float(self.mean_y), 6) if self.mean_y is not None else None,
            "sum_squares_xx": round(float(self.sum_squares_xx), 8) if self.sum_squares_xx is not None else None,
            "sum_squares_yy": round(float(self.sum_squares_yy), 8) if self.sum_squares_yy is not None else None,
            "sum_squares_xy": round(float(self.sum_squares_xy), 8) if self.sum_squares_xy is not None else None,
            "residual_sum_of_squares": (
                round(float(self.residual_sum_of_squares), 8)
                if self.residual_sum_of_squares is not None
                else None
            ),
            "residual_variance": (
                round(float(self.residual_variance), 8) if self.residual_variance is not None else None
            ),
            "residual_standard_error": (
                round(float(self.residual_standard_error), 8)
                if self.residual_standard_error is not None
                else None
            ),
            "slope_standard_error": (
                round(float(self.slope_standard_error), 8)
                if self.slope_standard_error is not None
                else None
            ),
            "intercept_standard_error": (
                round(float(self.intercept_standard_error), 8)
                if self.intercept_standard_error is not None
                else None
            ),
            "r_squared": round(float(self.r_squared), 6) if self.r_squared is not None else None,
            "unit_x": self.unit_x,
            "unit_y": self.unit_y,
            "slope_component": self.slope_component.to_dict() if self.slope_component else None,
            "diagnostic_message": self.diagnostic_message,
            "method_metadata": dict(self.method_metadata),
        }


class OLSTrendUncertaintyEvaluator:
    """Calculates descriptive OLS trend statistics and slope uncertainty from paired trajectory coordinates.

    Mathematical Formulation:
        Given coordinate pairs (x_i, y_i) for i = 1..n:
        mean_x = (1/n) * sum(x_i)
        mean_y = (1/n) * sum(y_i)
        SS_xx = sum((x_i - mean_x)^2)
        SS_yy = sum((y_i - mean_y)^2)  [Total Sum of Squares TSS]
        SS_xy = sum((x_i - mean_x) * (y_i - mean_y))

        m = SS_xy / SS_xx
        c = mean_y - m * mean_x
        e_i = y_i - (m * x_i + c)
        RSS = sum(e_i^2)
        df = n - 2
        s^2 = RSS / df
        s = sqrt(s^2)  [Residual standard error]
        SE(m) = s / sqrt(SS_xx)
        SE(c) = s * sqrt(1/n + mean_x^2 / SS_xx)
        R^2 = 1 - (RSS / SS_yy)  (for SS_yy > 0)
    """

    @classmethod
    def evaluate_pairs(
        cls,
        pairs: Sequence[Tuple[float, float]],
        unit_x: str = "cycles",
        unit_y: str = "Ah",
    ) -> TrajectoryTrendStatistics:
        """Evaluates descriptive OLS trend statistics and slope uncertainty from (x, y) coordinate pairs."""
        n = len(pairs)

        # 1. Check for Insufficient Samples (n < 2)
        if n < 2:
            comp = UncertaintyComponent(
                source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
                status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
                unit=f"{unit_y}/{unit_x}",
                description="Insufficient trajectory points (n < 2) for slope trend evaluation.",
                assumptions=("Minimum 2 points required for linear slope.",),
            )
            return TrajectoryTrendStatistics(
                sample_count=n,
                degrees_of_freedom=0,
                status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
                unit_x=unit_x,
                unit_y=unit_y,
                slope_component=comp,
                diagnostic_message=f"Insufficient observation count ({n} < 2).",
            )

        # 2. Check for Endpoint Slope Case (n == 2)
        if n == 2:
            x0, y0 = pairs[0]
            x1, y1 = pairs[1]
            dx = x1 - x0
            if abs(dx) <= 1e-15:
                comp = UncertaintyComponent(
                    source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
                    status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
                    unit=f"{unit_y}/{unit_x}",
                    description="Domain span is zero; both coordinates have identical x.",
                )
                return TrajectoryTrendStatistics(
                    sample_count=2,
                    degrees_of_freedom=0,
                    status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
                    unit_x=unit_x,
                    unit_y=unit_y,
                    slope_component=comp,
                    diagnostic_message="Domain span delta_x is zero.",
                )

            m = (y1 - y0) / dx
            c = y0 - m * x0
            # 2 points define a deterministic line; residual df = 0, no statistical regression interval
            comp = UncertaintyComponent(
                source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
                status=UncertaintyStatus.DETERMINISTIC_ONLY,
                standard_uncertainty=None,
                degrees_of_freedom=0,
                unit=f"{unit_y}/{unit_x}",
                description="Endpoint slope evaluated from 2 points does not support a statistical regression interval.",
                assumptions=(
                    "Two observation points define an exact deterministic secant line.",
                    "Residual degrees of freedom df=0 prevents statistical regression variance estimation.",
                ),
            )
            return TrajectoryTrendStatistics(
                sample_count=2,
                degrees_of_freedom=0,
                status=UncertaintyStatus.DETERMINISTIC_ONLY,
                slope=m,
                intercept=c,
                mean_x=(x0 + x1) / 2.0,
                mean_y=(y0 + y1) / 2.0,
                sum_squares_xx=((x0 - (x0 + x1) / 2.0) ** 2) + ((x1 - (x0 + x1) / 2.0) ** 2),
                residual_sum_of_squares=0.0,
                residual_variance=None,
                residual_standard_error=None,
                slope_standard_error=None,
                intercept_standard_error=None,
                r_squared=1.0,
                unit_x=unit_x,
                unit_y=unit_y,
                slope_component=comp,
                diagnostic_message="Deterministic endpoint slope; df=0 prevents statistical dispersion estimation.",
            )

        # 3. Standard OLS Evaluation (n >= 3, df >= 1)
        x_vals = [float(p[0]) for p in pairs]
        y_vals = [float(p[1]) for p in pairs]

        mean_x = sum(x_vals) / n
        mean_y = sum(y_vals) / n

        ss_xx = sum((x - mean_x) ** 2 for x in x_vals)
        ss_yy = sum((y - mean_y) ** 2 for y in y_vals)
        ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, y_vals))

        if ss_xx <= 1e-15:
            comp = UncertaintyComponent(
                source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
                status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
                unit=f"{unit_y}/{unit_x}",
                description="Domain variance SS_xx is zero; all observation x coordinates are identical.",
            )
            return TrajectoryTrendStatistics(
                sample_count=n,
                degrees_of_freedom=n - 2,
                status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
                mean_x=mean_x,
                mean_y=mean_y,
                sum_squares_xx=ss_xx,
                sum_squares_yy=ss_yy,
                sum_squares_xy=ss_xy,
                unit_x=unit_x,
                unit_y=unit_y,
                slope_component=comp,
                diagnostic_message="All x coordinates are identical (SS_xx = 0).",
            )

        slope = ss_xy / ss_xx
        intercept = mean_y - slope * mean_x

        # Compute residuals and residual sum of squares
        residuals = [y - (slope * x + intercept) for x, y in zip(x_vals, y_vals)]
        rss = sum(e ** 2 for e in residuals)

        df = n - 2
        res_var = max(0.0, rss / df)
        res_se = math.sqrt(res_var)

        # Standard error of the slope SE(m)
        se_slope = res_se / math.sqrt(ss_xx)

        # Standard error of intercept SE(c)
        se_intercept = res_se * math.sqrt((1.0 / n) + (mean_x ** 2 / ss_xx))

        # Coefficient of determination R^2
        if ss_yy > 1e-15:
            r2 = max(0.0, min(1.0, 1.0 - (rss / ss_yy)))
        else:
            r2 = 1.0 if rss <= 1e-15 else 0.0

        assumptions = (
            "Ordinary Least Squares (OLS) descriptive linear regression over historical trajectory.",
            f"Residual degrees of freedom df = {df}.",
            "R² describes historical explanatory fit under linear model; does NOT represent future confidence.",
        )

        slope_comp = UncertaintyComponent(
            source_category=UncertaintySourceCategory.TRAJECTORY_TREND,
            status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            standard_uncertainty=se_slope,
            degrees_of_freedom=df,
            unit=f"{unit_y}/{unit_x}",
            description=f"Standard error of historical OLS degradation slope (df={df}).",
            assumptions=assumptions,
            metadata={
                "residual_standard_error": round(res_se, 8),
                "r_squared": round(r2, 6),
                "sum_squares_xx": round(ss_xx, 8),
                "residual_sum_of_squares": round(rss, 8),
            },
        )

        return TrajectoryTrendStatistics(
            sample_count=n,
            degrees_of_freedom=df,
            status=UncertaintyStatus.STATISTICALLY_SUPPORTED,
            slope=slope,
            intercept=intercept,
            mean_x=mean_x,
            mean_y=mean_y,
            sum_squares_xx=ss_xx,
            sum_squares_yy=ss_yy,
            sum_squares_xy=ss_xy,
            residual_sum_of_squares=rss,
            residual_variance=res_var,
            residual_standard_error=res_se,
            slope_standard_error=se_slope,
            intercept_standard_error=se_intercept,
            r_squared=r2,
            unit_x=unit_x,
            unit_y=unit_y,
            slope_component=slope_comp,
            diagnostic_message="OLS descriptive trend statistics computed successfully.",
            method_metadata={
                "algorithm": "ORDINARY_LEAST_SQUARES",
                "df": df,
                "explanatory_fit_r2": round(r2, 6),
            },
        )
