"""State of Health (SOH) Estimation Engine.

Orchestrates stress accumulation, empirical degradation evaluation, and dual-aspect
(capacity-based and resistance-based) State of Health synthesis.
"""

from typing import Any, Optional, Protocol, runtime_checkable

from src.analytics.degradation import ArrheniusSEIEmpiricalDegradationModel, DegradationModel
from src.analytics.stress import StressAccumulator
from src.analytics.types import BatteryHealthState, CalibrationStatus
from src.domain.battery.entities import BatteryPack
from src.telemetry.snapshots import TelemetrySnapshot


@runtime_checkable
class StateOfHealthEstimator(Protocol):
    """Protocol for battery State of Health estimators."""

    def update(
        self,
        snapshot: TelemetrySnapshot,
        dt_s: Optional[float] = None,
        pack: Optional[BatteryPack] = None,
        sync_output: Optional[Any] = None,
    ) -> BatteryHealthState:
        """Updates internal health state and returns an immutable BatteryHealthState."""
        ...

    def get_health_state(self) -> Optional[BatteryHealthState]:
        """Returns the current estimated BatteryHealthState."""
        ...

    def reset(self) -> None:
        """Resets the estimator state."""
        ...


class ThroughputHealthEstimator:
    """Deterministic throughput and degradation-driven State of Health estimator.

    Computes:
    - SOH_Capacity = Q_usable / Q_nominal = (1.0 - Total Capacity Fade)
    - SOH_Resistance = max(0.0, 1.0 - (Resistance Growth / EOL Growth Limit)) [when R0 configured]
    - SOH_Unified = min(SOH_Capacity, SOH_Resistance) [or SOH_Capacity if resistance unconfigured]
    """

    def __init__(
        self,
        system_id: str,
        nominal_capacity_ah: float,
        nominal_resistance_ohm: Optional[float] = None,
        degradation_model: Optional[DegradationModel] = None,
        calibration_status: CalibrationStatus = CalibrationStatus.UNCALIBRATED_PARAMETRIC_MODEL,
        max_integration_interval_s: float = 60.0,
    ) -> None:
        self._system_id = system_id
        self._nominal_capacity_ah = max(0.001, float(nominal_capacity_ah))
        self._nominal_resistance_ohm = float(nominal_resistance_ohm) if nominal_resistance_ohm is not None else None
        self._degradation_model = degradation_model or ArrheniusSEIEmpiricalDegradationModel()
        self._calibration_status = calibration_status
        self._stress_accumulator = StressAccumulator(
            nominal_capacity_ah=self._nominal_capacity_ah,
            max_integration_interval_s=max_integration_interval_s,
        )
        self._latest_health_state: Optional[BatteryHealthState] = None

    @property
    def system_id(self) -> str:
        """System identifier."""
        return self._system_id

    @property
    def stress_accumulator(self) -> StressAccumulator:
        """Attached stress accumulator instance."""
        return self._stress_accumulator

    @property
    def degradation_model(self) -> DegradationModel:
        """Attached degradation model instance."""
        return self._degradation_model

    def update(
        self,
        snapshot: TelemetrySnapshot,
        dt_s: Optional[float] = None,
        pack: Optional[BatteryPack] = None,
        sync_output: Optional[Any] = None,
    ) -> BatteryHealthState:
        """Updates health estimation from an incoming observation."""
        # Update nominal capacity from pack if provided
        if pack is not None and pack.nominal_capacity_ah > 0.0:
            self._nominal_capacity_ah = pack.nominal_capacity_ah
            self._stress_accumulator.set_nominal_capacity(pack.nominal_capacity_ah)

        # 1. Update stress accumulation
        stress_state = self._stress_accumulator.update(snapshot=snapshot, dt_s=dt_s)

        # 2. Extract operating temperature and SOC
        temp_c = 25.0
        if snapshot.avg_cell_temperature_c is not None:
            temp_c = snapshot.avg_cell_temperature_c
        elif snapshot.max_cell_temperature_c is not None:
            temp_c = snapshot.max_cell_temperature_c

        soc_val = 0.5
        if snapshot.soc_fraction is not None:
            soc_val = max(0.0, min(1.0, snapshot.soc_fraction))
        elif sync_output is not None and hasattr(sync_output, "model_output"):
            soc_val = sync_output.model_output.state.soc_fraction

        # 3. Evaluate degradation model
        degradation = self._degradation_model.evaluate(
            stress=stress_state,
            temperature_c=temp_c,
            avg_soc=soc_val,
        )

        # 4. Synthesize capacity SOH
        soh_c = max(0.0, min(1.0, 1.0 - degradation.total_capacity_fade_fraction))
        estimated_cap_ah = soh_c * self._nominal_capacity_ah

        # 5. Synthesize resistance SOH if nominal resistance is configured
        soh_r: Optional[float] = None
        estimated_r0: Optional[float] = None

        if self._nominal_resistance_ohm is not None and self._nominal_resistance_ohm > 0.0:
            growth_limit = getattr(getattr(self._degradation_model, "params", None), "eol_resistance_growth_limit", 1.0)
            r_growth_fraction = degradation.resistance_growth_fraction
            estimated_r0 = self._nominal_resistance_ohm * (1.0 + r_growth_fraction)
            soh_r = max(0.0, min(1.0, 1.0 - (r_growth_fraction / growth_limit)))

        # 6. Unified SOH aggregation
        soh_unified = min(soh_c, soh_r) if soh_r is not None else soh_c

        health_state = BatteryHealthState(
            timestamp_ns=snapshot.timestamp_ns,
            system_id=self._system_id,
            soh_capacity_fraction=soh_c,
            soh_resistance_fraction=soh_r,
            soh_unified_fraction=soh_unified,
            cumulative_throughput_ah=stress_state.total_throughput_ah,
            cumulative_energy_throughput_wh=stress_state.energy_throughput_wh,
            equivalent_full_cycles=stress_state.equivalent_full_cycles,
            estimated_capacity_ah=estimated_cap_ah,
            estimated_series_resistance_ohm=estimated_r0,
            capacity_fade_fraction=degradation.total_capacity_fade_fraction,
            resistance_growth_fraction=degradation.resistance_growth_fraction,
            calibration_status=self._calibration_status,
            metadata={
                "calendar_fade_fraction": degradation.calendar_capacity_fade_fraction,
                "cycling_fade_fraction": degradation.cycling_capacity_fade_fraction,
                "charge_throughput_ah": stress_state.charge_throughput_ah,
                "discharge_throughput_ah": stress_state.discharge_throughput_ah,
            },
        )

        self._latest_health_state = health_state
        return health_state

    def get_health_state(self) -> Optional[BatteryHealthState]:
        """Returns the most recent calculated health state."""
        return self._latest_health_state

    def reset(self) -> None:
        """Resets stress and health tracking state."""
        self._stress_accumulator.reset()
        self._latest_health_state = None
