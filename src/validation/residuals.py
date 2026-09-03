"""Numerically stable streaming residual accumulation and statistical metrics computation.

Implements Welford-style one-pass algorithms for calculating RMSE, MAE, Max Error,
Mean Bias Error (MBE), sample standard deviation, and paired-signal R^2 with zero-variance safeguards.
"""

import math
from typing import Optional

from src.validation.types import SignalProvenance, SignalResidualMetrics


class ResidualStatisticsAccumulator:
    """One-pass numerically stable statistics accumulator for paired physical signals."""

    def __init__(self) -> None:
        self._count: int = 0
        self._sum_error: float = 0.0
        self._sum_abs_error: float = 0.0
        self._sum_sq_error: float = 0.0
        self._max_abs_error: float = 0.0

        # Welford state for residual sample variance
        self._mean_res: float = 0.0
        self._m2_res: float = 0.0

        # Welford state for measured signal variance (for paired R^2 computation)
        self._mean_meas: float = 0.0
        self._m2_meas: float = 0.0

    @property
    def sample_count(self) -> int:
        """Total accumulated observations."""
        return self._count

    def update(self, measured: float, simulated: float) -> None:
        """Ingests a single paired observation (measured, simulated).

        Residual sign convention: error = measured - simulated
        """
        if math.isnan(measured) or math.isinf(measured) or math.isnan(simulated) or math.isinf(simulated):
            return

        err = measured - simulated
        abs_err = abs(err)

        self._count += 1
        n = self._count

        self._sum_error += err
        self._sum_abs_error += abs_err
        self._sum_sq_error += err * err
        if abs_err > self._max_abs_error:
            self._max_abs_error = abs_err

        # Welford update for residual
        delta_res = err - self._mean_res
        self._mean_res += delta_res / n
        delta_res_2 = err - self._mean_res
        self._m2_res += delta_res * delta_res_2

        # Welford update for measured signal (for Total Sum of Squares SST)
        delta_meas = measured - self._mean_meas
        self._mean_meas += delta_meas / n
        delta_meas_2 = measured - self._mean_meas
        self._m2_meas += delta_meas * delta_meas_2

    def compute_metrics(
        self,
        signal_name: str,
        provenance_a: SignalProvenance = SignalProvenance.MEASURED,
        provenance_b: SignalProvenance = SignalProvenance.MODEL_PREDICTED,
    ) -> SignalResidualMetrics:
        """Computes statistical metrics over accumulated samples.

        Returns:
            SignalResidualMetrics with all derived statistics.
        """
        if self._count == 0:
            return SignalResidualMetrics(
                signal_name=signal_name,
                provenance_a=provenance_a,
                provenance_b=provenance_b,
                sample_count=0,
                rmse=0.0,
                mae=0.0,
                max_error=0.0,
                mean_bias_error=0.0,
                std_dev=0.0,
                r_squared=None,
                r_squared_diagnostic="INSUFFICIENT_SAMPLES",
            )

        n = self._count
        mbe = self._sum_error / n
        mae = self._sum_abs_error / n
        rmse = math.sqrt(self._sum_sq_error / n)
        max_err = self._max_abs_error
        std_dev = math.sqrt(self._m2_res / (n - 1)) if n > 1 else 0.0

        # Compute paired R^2 = 1 - (SSE / SST)
        sse = self._sum_sq_error
        sst = self._m2_meas

        r2: Optional[float] = None
        r2_diag: Optional[str] = None

        if n < 2:
            r2_diag = "INSUFFICIENT_SAMPLES"
        elif sst < 1.0e-8:
            r2_diag = "ZERO_MEASURED_VARIANCE"
        else:
            r2_val = 1.0 - (sse / sst)
            # Bound R^2 plausibly or report negative if model tracking is worse than horizontal mean line
            r2 = r2_val
            r2_diag = None

        return SignalResidualMetrics(
            signal_name=signal_name,
            provenance_a=provenance_a,
            provenance_b=provenance_b,
            sample_count=n,
            rmse=rmse,
            mae=mae,
            max_error=max_err,
            mean_bias_error=mbe,
            std_dev=std_dev,
            r_squared=r2,
            r_squared_diagnostic=r2_diag,
        )

    def reset(self) -> None:
        """Resets accumulator state to zero."""
        self._count = 0
        self._sum_error = 0.0
        self._sum_abs_error = 0.0
        self._sum_sq_error = 0.0
        self._max_abs_error = 0.0
        self._mean_res = 0.0
        self._m2_res = 0.0
        self._mean_meas = 0.0
        self._m2_meas = 0.0
