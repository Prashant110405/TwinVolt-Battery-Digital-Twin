"""Strongly-Typed Domain Events for TwinVolt.

Defines the specialized event representations for telemetry ingestion, state estimation,
twin synchronization, thermal safety alerts, and physical anomaly detection.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from src.estimators.base import EstimationState
from src.events.base import TwinEvent
from src.storage.base import TwinStateRecord
from src.telemetry.snapshots import TelemetrySnapshot


@dataclass(frozen=True)
class TelemetryReceivedEvent(TwinEvent):
    """Published when incoming battery telemetry is validated and parsed into a TelemetrySnapshot."""

    snapshot: Optional[TelemetrySnapshot] = None
    event_type: str = "telemetry.received"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.snapshot is not None:
            # Populate default source_id and timestamp_ns from snapshot if not explicitly set
            if self.source_id == "system":
                object.__setattr__(self, "source_id", self.snapshot.system_id)
            if self.timestamp_ns == 0:
                object.__setattr__(self, "timestamp_ns", self.snapshot.timestamp_ns)

    @property
    def system_id(self) -> str:
        """System identifier of the observed battery."""
        return self.snapshot.system_id if self.snapshot else self.source_id

    @property
    def pack_voltage_v(self) -> Optional[float]:
        """Observed pack terminal voltage."""
        return self.snapshot.pack_voltage_v if self.snapshot else None

    @property
    def pack_current_a(self) -> Optional[float]:
        """Observed pack load current."""
        return self.snapshot.pack_current_a if self.snapshot else None


@dataclass(frozen=True)
class TelemetryPersistedEvent(TwinEvent):
    """Published when a telemetry snapshot has been committed to a persistence repository."""

    snapshot_id: str = ""
    system_id: str = ""
    storage_backend: str = "memory"
    event_type: str = "telemetry.persisted"


@dataclass(frozen=True)
class StateEstimatedEvent(TwinEvent):
    """Published when state estimators (EKF, SOH, Coulomb Counter) complete a state update."""

    estimation_state: Optional[EstimationState] = None
    event_type: str = "state.estimated"

    @property
    def soc_fraction(self) -> Optional[float]:
        """Estimated State of Charge."""
        return self.estimation_state.soc_fraction if self.estimation_state else None

    @property
    def soh_fraction(self) -> Optional[float]:
        """Estimated State of Health."""
        return self.estimation_state.soh_fraction if self.estimation_state else None


@dataclass(frozen=True)
class TwinSynchronizedEvent(TwinEvent):
    """Published when the Digital Twin co-simulation engine completes a synchronization step with residuals."""

    twin_record: Optional[TwinStateRecord] = None
    event_type: str = "twin.synchronized"

    @property
    def voltage_residual_v(self) -> Optional[float]:
        """Instantaneous terminal voltage residual (V_meas - V_sim)."""
        if self.twin_record and "voltage_residual_v" in self.twin_record.residuals:
            return self.twin_record.residuals["voltage_residual_v"]
        return None

    @property
    def temp_residual_c(self) -> Optional[float]:
        """Instantaneous temperature residual (T_meas - T_sim)."""
        if self.twin_record and "temp_residual_c" in self.twin_record.residuals:
            return self.twin_record.residuals["temp_residual_c"]
        return None


@dataclass(frozen=True)
class ThermalAlertEvent(TwinEvent):
    """Published when cell or pack temperatures exceed critical thermal warning or cutoff thresholds."""

    system_id: str = ""
    temperature_c: float = 25.0
    threshold_c: float = 60.0
    cell_id: Optional[str] = None
    severity: str = "WARNING"  # "INFO", "WARNING", "CRITICAL", "EMERGENCY"
    event_type: str = "alert.thermal"


@dataclass(frozen=True)
class BatteryAnomalyDetectedEvent(TwinEvent):
    """Published when physical residuals or sensor statistics indicate anomalous battery behavior."""

    system_id: str = ""
    anomaly_type: str = "VOLTAGE_DIVERGENCE"
    observed_value: float = 0.0
    expected_value: float = 0.0
    residual: float = 0.0
    severity: str = "WARNING"
    description: str = ""
    event_type: str = "anomaly.detected"
