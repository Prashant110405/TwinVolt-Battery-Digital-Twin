"""Battery Model Tracking Accuracy and Error Metrics Evaluator.

Calculates standardized statistical error metrics (RMSE, MAE, Max Error, MBE, R^2, NRMSE)
comparing physical/reference observations against digital twin co-simulation outputs.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence

from src.models.math import assert_finite
from src.replay.exceptions import EvaluationError
from src.runtime.synchronizer import TwinSyncOutput


@dataclass(frozen=True)
class SignalTrackingMetrics:
    """Statistical tracking error metrics for a single physical observation signal."""

    signal_name: str
    sample_count: int
    rmse: float
    mae: float
    max_error: float
    mean_bias_error: float
    r_squared: float
    nrmse: float
    observed_mean: float = 0.0
    observed_min: float = 0.0
    observed_max: float = 0.0
    simulated_mean: float = 0.0
    simulated_min: float = 0.0
    simulated_max: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serializes signal tracking metrics to a dictionary."""
        return {
            "signal_name": self.signal_name,
            "sample_count": self.sample_count,
            "rmse": self.rmse,
            "mae": self.mae,
            "max_error": self.max_error,
            "mean_bias_error": self.mean_bias_error,
            "r_squared": self.r_squared,
            "nrmse": self.nrmse,
            "observed_mean": self.observed_mean,
            "observed_min": self.observed_min,
            "observed_max": self.observed_max,
            "simulated_mean": self.simulated_mean,
            "simulated_min": self.simulated_min,
            "simulated_max": self.simulated_max,
        }


@dataclass(frozen=True)
class TrackingMetricsReport:
    """Comprehensive evaluation report aggregating tracking metrics across all evaluated signals."""

    system_id: str
    profile_name: str
    total_samples: int
    signals: Mapping[str, SignalTrackingMetrics] = field(default_factory=dict)
    is_passing: bool = True
    evaluation_metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def voltage_metrics(self) -> Optional[SignalTrackingMetrics]:
        """Terminal voltage tracking metrics, if evaluated."""
        return self.signals.get("voltage_v")

    @property
    def temperature_metrics(self) -> Optional[SignalTrackingMetrics]:
        """Core/pack temperature tracking metrics, if evaluated."""
        return self.signals.get("temperature_c")

    @property
    def soc_metrics(self) -> Optional[SignalTrackingMetrics]:
        """State of Charge tracking metrics, if evaluated."""
        return self.signals.get("soc_fraction")

    def to_dict(self) -> dict[str, Any]:
        """Serializes tracking metrics report to dictionary."""
        return {
            "system_id": self.system_id,
            "profile_name": self.profile_name,
            "total_samples": self.total_samples,
            "is_passing": self.is_passing,
            "signals": {k: v.to_dict() for k, v in self.signals.items()},
            "evaluation_metadata": dict(self.evaluation_metadata),
        }


class TrackingMetricsEvaluator:
    """Statistical Tracking Error and Accuracy Evaluation Engine.

    Computes analytical metrics for observed physical telemetry vs. simulated state vectors.
    """

    @staticmethod
    def compute_signal_metrics(
        signal_name: str,
        observed: Sequence[float],
        simulated: Sequence[float],
    ) -> SignalTrackingMetrics:
        """Computes statistical accuracy metrics comparing observed vs simulated series.

        Args:
            signal_name: Name of the evaluated signal (e.g., 'voltage_v', 'temperature_c').
            observed: Sequence of reference/measured observations.
            simulated: Sequence of digital twin simulated/estimated values.

        Returns:
            SignalTrackingMetrics value object.

        Raises:
            EvaluationError: If sequence lengths mismatch or sequences are empty.
        """
        n_obs = len(observed)
        n_sim = len(simulated)

        if n_obs == 0:
            raise EvaluationError(f"Cannot evaluate signal '{signal_name}' with empty observed sequence.")
        if n_obs != n_sim:
            raise EvaluationError(
                f"Length mismatch for signal '{signal_name}': observed has {n_obs} samples, "
                f"simulated has {n_sim} samples."
            )

        for idx, (y, y_hat) in enumerate(zip(observed, simulated)):
            if not isinstance(y, (int, float)) or math.isnan(y) or math.isinf(y):
                raise EvaluationError(f"observed[{idx}] for '{signal_name}' is non-finite: {y}.")
            if not isinstance(y_hat, (int, float)) or math.isnan(y_hat) or math.isinf(y_hat):
                raise EvaluationError(f"simulated[{idx}] for '{signal_name}' is non-finite: {y_hat}.")

        # 1. Error terms: e_i = y_i - y_hat_i
        errors = [float(y - y_hat) for y, y_hat in zip(observed, simulated)]
        abs_errors = [abs(e) for e in errors]
        sq_errors = [e * e for e in errors]

        # 2. MAE, RMSE, Max Error, MBE
        mae = sum(abs_errors) / n_obs
        mse = sum(sq_errors) / n_obs
        rmse = math.sqrt(mse)
        max_error = max(abs_errors)
        mbe = sum(errors) / n_obs

        # 3. Statistical summary
        obs_mean = sum(observed) / n_obs
        obs_min = min(observed)
        obs_max = max(observed)
        sim_mean = sum(simulated) / n_sim
        sim_min = min(simulated)
        sim_max = max(simulated)

        # 4. R^2 Coefficient of Determination: 1 - (SS_res / SS_tot)
        ss_res = sum(sq_errors)
        ss_tot = sum((y - obs_mean) ** 2 for y in observed)

        if ss_tot > 1e-12:
            r_squared = 1.0 - (ss_res / ss_tot)
        else:
            # Constant signal edge case: perfect match yields 1.0, otherwise 0.0
            r_squared = 1.0 if ss_res < 1e-12 else 0.0

        # 5. Normalized RMSE (NRMSE = RMSE / Range)
        obs_range = obs_max - obs_min
        if obs_range > 1e-12:
            nrmse = rmse / obs_range
        else:
            nrmse = 0.0

        return SignalTrackingMetrics(
            signal_name=signal_name,
            sample_count=n_obs,
            rmse=rmse,
            mae=mae,
            max_error=max_error,
            mean_bias_error=mbe,
            r_squared=r_squared,
            nrmse=nrmse,
            observed_mean=obs_mean,
            observed_min=obs_min,
            observed_max=obs_max,
            simulated_mean=sim_mean,
            simulated_min=sim_min,
            simulated_max=sim_max,
        )

    def evaluate_from_sync_outputs(
        self,
        sync_outputs: Sequence[TwinSyncOutput],
        system_id: str = "battery_system",
        profile_name: str = "drive_cycle",
        target_voltage_rmse_v: Optional[float] = None,
        target_temp_rmse_c: Optional[float] = None,
        target_soc_rmse: Optional[float] = None,
    ) -> TrackingMetricsReport:
        """Extracts paired observation and simulation signals from TwinSyncOutput sequence and evaluates accuracy.

        Args:
            sync_outputs: Sequence of completed synchronization outputs.
            system_id: Battery system identifier.
            profile_name: Name of evaluated drive cycle.
            target_voltage_rmse_v: Optional maximum permissible voltage RMSE for passing score.
            target_temp_rmse_c: Optional maximum permissible temperature RMSE for passing score.
            target_soc_rmse: Optional maximum permissible SOC RMSE for passing score.

        Returns:
            TrackingMetricsReport.
        """
        if not sync_outputs:
            return TrackingMetricsReport(
                system_id=system_id,
                profile_name=profile_name,
                total_samples=0,
                is_passing=True,
            )

        # Extract available paired signal arrays
        obs_voltages: list[float] = []
        sim_voltages: list[float] = []

        obs_temps: list[float] = []
        sim_temps: list[float] = []

        obs_socs: list[float] = []
        sim_socs: list[float] = []

        for out in sync_outputs:
            # Voltage
            if out.telemetry.pack_voltage_v is not None:
                obs_voltages.append(out.telemetry.pack_voltage_v)
                sim_voltages.append(out.model_output.terminal_voltage_v)

            # Temperature
            t_obs = (
                out.telemetry.avg_cell_temperature_c
                if out.telemetry.avg_cell_temperature_c is not None
                else out.telemetry.max_cell_temperature_c
            )
            if t_obs is not None:
                obs_temps.append(t_obs)
                sim_temps.append(out.model_output.state.temperature_c)

            # SOC (Observed vs Model or Estimator)
            if out.telemetry.soc_fraction is not None:
                obs_socs.append(out.telemetry.soc_fraction)
                # Compare against state estimator if available, else model state
                soc_val = (
                    out.estimation_output.state.soc_fraction
                    if out.estimation_output is not None
                    else out.model_output.state.soc_fraction
                )
                sim_socs.append(soc_val)

        signals_map: dict[str, SignalTrackingMetrics] = {}
        is_passing = True

        # Compute Voltage Metrics
        if obs_voltages:
            v_metrics = self.compute_signal_metrics("voltage_v", obs_voltages, sim_voltages)
            signals_map["voltage_v"] = v_metrics
            if target_voltage_rmse_v is not None and v_metrics.rmse > target_voltage_rmse_v:
                is_passing = False

        # Compute Temperature Metrics
        if obs_temps:
            t_metrics = self.compute_signal_metrics("temperature_c", obs_temps, sim_temps)
            signals_map["temperature_c"] = t_metrics
            if target_temp_rmse_c is not None and t_metrics.rmse > target_temp_rmse_c:
                is_passing = False

        # Compute SOC Metrics
        if obs_socs:
            soc_metrics = self.compute_signal_metrics("soc_fraction", obs_socs, sim_socs)
            signals_map["soc_fraction"] = soc_metrics
            if target_soc_rmse is not None and soc_metrics.rmse > target_soc_rmse:
                is_passing = False

        return TrackingMetricsReport(
            system_id=system_id,
            profile_name=profile_name,
            total_samples=len(sync_outputs),
            signals=signals_map,
            is_passing=is_passing,
            evaluation_metadata={
                "evaluated_signals_count": len(signals_map),
                "has_voltage": "voltage_v" in signals_map,
                "has_temperature": "temperature_c" in signals_map,
                "has_soc": "soc_fraction" in signals_map,
            },
        )
