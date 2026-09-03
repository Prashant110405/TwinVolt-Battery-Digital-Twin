"""Digital Twin Real-Time Synchronizer Core.

Coordinates execution steps across incoming telemetry, simulation models, and state estimators,
computing instantaneous physical residuals and state discrepancy diagnostics.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional

from src.estimators.base import (
    EstimationInput,
    EstimationOutput,
    StateEstimator,
)
from src.models.base import BatteryModel
from src.models.types import ModelInput, ModelOutput
from src.runtime.config import RuntimeConfig
from src.runtime.exceptions import (
    ClockSkewError,
    StaleTelemetryError,
    SynchronizationError,
)
from src.telemetry.enums import TelemetryQuality
from src.telemetry.snapshots import TelemetrySnapshot


@dataclass(frozen=True)
class TwinSyncOutput:
    """Synchronized discrete execution result for a single Digital Twin simulation cycle.

    Captures physical observations, simulated states, estimator outputs, and tracking residuals:
    - step_index: Monotonically increasing runtime cycle counter.
    - timestamp_ns: Nanosecond timestamp of the active observation.
    - dt_s: Effective discrete time step interval in seconds.
    - telemetry: Canonical telemetry snapshot that drove this cycle.
    - model_output: Output vector from the physical/mathematical simulation model.
    - estimation_output: Optional output vector from the internal state estimator.
    - residuals: Dictionary of computed physical residuals (e.g. voltage, temperature, SOC).
    - quality: Overall cycle data quality flag ("VALID", "DEGRADED", "STALE", "INVALID").
    - diagnostics: Diagnostic metrics and calculation details for observability.
    """

    step_index: int
    timestamp_ns: int
    dt_s: float
    telemetry: TelemetrySnapshot
    model_output: ModelOutput
    estimation_output: Optional[EstimationOutput] = None
    residuals: Mapping[str, float] = field(default_factory=dict)
    quality: str = "VALID"
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes synchronization output to dictionary."""
        return {
            "step_index": self.step_index,
            "timestamp_ns": self.timestamp_ns,
            "dt_s": self.dt_s,
            "telemetry": self.telemetry.to_dict(),
            "model_output": self.model_output.to_dict(),
            "estimation_output": self.estimation_output.to_dict() if self.estimation_output else None,
            "residuals": dict(self.residuals),
            "quality": self.quality,
            "diagnostics": dict(self.diagnostics),
        }


class TwinSynchronizer:
    """Real-Time Dual-Track Co-Simulation and Synchronization Engine.

    Executes synchronized discrete time steps advancing the battery model and state estimator
    in lockstep with physical telemetry, computing analytical discrepancy residuals.
    """

    def __init__(
        self,
        battery_model: BatteryModel,
        state_estimator: Optional[StateEstimator] = None,
        config: Optional[RuntimeConfig] = None,
    ) -> None:
        if not isinstance(battery_model, BatteryModel):
            raise SynchronizationError("battery_model must implement the BatteryModel protocol.")
        if state_estimator is not None and not isinstance(state_estimator, StateEstimator):
            raise SynchronizationError("state_estimator must implement the StateEstimator protocol.")

        self._model = battery_model
        self._estimator = state_estimator
        self._config = config or RuntimeConfig()

        self._prev_timestamp_ns: Optional[int] = None
        self._step_counter = 0

    @property
    def battery_model(self) -> BatteryModel:
        """Attached battery simulation model."""
        return self._model

    @property
    def state_estimator(self) -> Optional[StateEstimator]:
        """Attached state estimator instance."""
        return self._estimator

    @property
    def config(self) -> RuntimeConfig:
        """Attached runtime configuration."""
        return self._config

    @property
    def step_count(self) -> int:
        """Total number of completed synchronization steps."""
        return self._step_counter

    @property
    def previous_timestamp_ns(self) -> Optional[int]:
        """Nanosecond timestamp of the previous synchronization step."""
        return self._prev_timestamp_ns

    def step(self, snapshot: TelemetrySnapshot) -> TwinSyncOutput:
        """Executes a single discrete synchronization step for incoming telemetry.

        Args:
            snapshot: Canonical TelemetrySnapshot representing the current battery observation.

        Returns:
            TwinSyncOutput containing model outputs, estimator outputs, and computed residuals.

        Raises:
            ClockSkewError: If non-monotonic timestamps arrive when strict_monotonicity is enabled.
            SynchronizationError: On evaluation failures.
        """
        if not isinstance(snapshot, TelemetrySnapshot):
            raise SynchronizationError(
                f"Expected TelemetrySnapshot, got {type(snapshot).__name__}."
            )

        ts_ns = snapshot.timestamp_ns
        quality = "VALID"

        # 1. Determine Discrete Time Delta dt_s
        if self._prev_timestamp_ns is None:
            dt_s = self._config.default_dt_s
        else:
            delta_ns = ts_ns - self._prev_timestamp_ns
            if delta_ns < 0:
                if self._config.strict_monotonicity:
                    raise ClockSkewError(
                        f"Non-monotonic timestamp received: {ts_ns} < {self._prev_timestamp_ns}.",
                        system_id=snapshot.system_id,
                        details={
                            "current_ts_ns": ts_ns,
                            "prev_ts_ns": self._prev_timestamp_ns,
                        },
                    )
                quality = "DEGRADED"
                dt_s = self._config.default_dt_s
            elif delta_ns == 0:
                # Duplicate timestamp: advance by min_dt_s with degraded flag
                dt_s = self._config.min_dt_s
                quality = "DEGRADED"
            else:
                raw_dt_s = delta_ns / 1_000_000_000.0
                if raw_dt_s > self._config.stale_timeout_s:
                    quality = "STALE"
                # Clamp dt within allowable bounds for numerical stability
                dt_s = min(max(raw_dt_s, self._config.min_dt_s), self._config.max_dt_s)

        # Inherit snapshot quality if degraded or invalid
        if snapshot.quality == TelemetryQuality.INVALID:
            quality = "INVALID"
        elif snapshot.quality in (TelemetryQuality.DEGRADED, TelemetryQuality.STALE) and quality == "VALID":
            quality = snapshot.quality.value

        # 2. Prepare Model Input & Execute Model Step
        current_a = snapshot.pack_current_a if snapshot.pack_current_a is not None else 0.0
        amb_temp = (
            snapshot.ambient_temperature_c
            if snapshot.ambient_temperature_c is not None
            else 25.0
        )

        model_input = ModelInput(
            current_a=current_a,
            dt_s=dt_s,
            ambient_temperature_c=amb_temp,
            timestamp_ns=ts_ns,
        )

        try:
            model_output = self._model.step(model_input)
        except Exception as exc:
            raise SynchronizationError(
                f"Battery model step evaluation failed: {exc}",
                system_id=snapshot.system_id,
                details={"model_input": model_input.to_dict()},
            ) from exc

        # 3. Prepare Estimator Input & Execute Estimator Step (if present)
        estimation_output: Optional[EstimationOutput] = None
        if self._estimator is not None:
            # Fall back to simulated terminal voltage if telemetry omitted voltage
            v_meas = (
                snapshot.pack_voltage_v
                if snapshot.pack_voltage_v is not None
                else model_output.terminal_voltage_v
            )
            # Determine best available observed temperature
            t_meas = (
                snapshot.avg_cell_temperature_c
                if snapshot.avg_cell_temperature_c is not None
                else (
                    snapshot.max_cell_temperature_c
                    if snapshot.max_cell_temperature_c is not None
                    else model_output.state.temperature_c
                )
            )

            est_input = EstimationInput(
                current_a=current_a,
                voltage_v=v_meas,
                temperature_c=t_meas,
                dt_s=dt_s,
                timestamp_ns=ts_ns,
            )

            try:
                estimation_output = self._estimator.step(est_input)
            except Exception as exc:
                raise SynchronizationError(
                    f"State estimator step evaluation failed: {exc}",
                    system_id=snapshot.system_id,
                    details={"estimation_input": est_input.to_dict()},
                ) from exc

        # 4. Compute Analytical Physical Residuals
        residuals: dict[str, float] = {}

        # Terminal Voltage Residual: V_meas - V_sim
        if snapshot.pack_voltage_v is not None:
            residuals["voltage_residual_v"] = (
                snapshot.pack_voltage_v - model_output.terminal_voltage_v
            )

        # Temperature Residual: T_meas - T_sim
        obs_temp = (
            snapshot.avg_cell_temperature_c
            if snapshot.avg_cell_temperature_c is not None
            else snapshot.max_cell_temperature_c
        )
        if obs_temp is not None:
            residuals["temp_residual_c"] = obs_temp - model_output.state.temperature_c

        # State of Charge Discrepancy: SOC_sim - SOC_est
        if estimation_output is not None:
            residuals["soc_discrepancy"] = (
                model_output.state.soc_fraction - estimation_output.state.soc_fraction
            )

        # Power Residual (if pack power is declared in snapshot)
        if (
            snapshot.pack_power_w is not None
            and snapshot.pack_voltage_v is not None
            and snapshot.pack_current_a is not None
        ):
            calc_power = snapshot.pack_voltage_v * snapshot.pack_current_a
            residuals["power_residual_w"] = snapshot.pack_power_w - calc_power

        # Cell Voltage Delta Residual (for multi-cell pack models)
        if hasattr(model_output, "cell_voltage_delta_v") and snapshot.cell_voltage_delta_v() is not None:
            obs_delta = snapshot.cell_voltage_delta_v() or 0.0
            sim_delta = getattr(model_output, "cell_voltage_delta_v", 0.0)
            residuals["cell_voltage_delta_residual_v"] = obs_delta - sim_delta

        # 5. Update Synchronizer Internal State
        self._prev_timestamp_ns = ts_ns
        self._step_counter += 1

        diagnostics: dict[str, Any] = {
            "computed_dt_s": dt_s,
            "sim_terminal_voltage_v": model_output.terminal_voltage_v,
            "sim_temperature_c": model_output.state.temperature_c,
            "sim_soc_fraction": model_output.state.soc_fraction,
        }
        if estimation_output is not None:
            diagnostics["est_soc_fraction"] = estimation_output.state.soc_fraction
            diagnostics["est_soc_variance"] = estimation_output.state.soc_variance

        return TwinSyncOutput(
            step_index=self._step_counter,
            timestamp_ns=ts_ns,
            dt_s=dt_s,
            telemetry=snapshot,
            model_output=model_output,
            estimation_output=estimation_output,
            residuals=residuals,
            quality=quality,
            diagnostics=diagnostics,
        )

    def reset(self) -> None:
        """Resets synchronization sequencing state and previous timestamps."""
        self._prev_timestamp_ns = None
        self._step_counter = 0
