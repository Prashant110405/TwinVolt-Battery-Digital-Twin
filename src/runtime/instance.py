"""Digital Twin Runtime Instance Orchestrator.

Central execution coordinator that binds physical domain structures (BatteryPack),
mathematical models (BatteryModel), state estimators (StateEstimator), ingestion pipelines,
event broadcasting (EventBus), and persistence repositories into a cohesive Digital Twin.
"""

from dataclasses import dataclass, field
import time
from typing import Any, Mapping, Optional, Union

from src.domain.battery.entities import BatteryPack
from src.estimators.base import EstimationState, StateEstimator
from src.events.base import AbstractEventBus
from src.events.types import (
    BatteryAnomalyDetectedEvent,
    StateEstimatedEvent,
    TelemetryPersistedEvent,
    TelemetryReceivedEvent,
    ThermalAlertEvent,
    TwinSynchronizedEvent,
)
from src.ingestion.base import IngestionStatus
from src.ingestion.pipeline import IngestionPipeline
from src.models.base import BatteryModel
from src.models.types import ModelState
from src.runtime.anomaly_detector import AnomalyReport, PhysicsAnomalyDetector
from src.runtime.config import RuntimeConfig
from src.runtime.exceptions import (
    InvalidRuntimeStateError,
    RuntimeExecutionError,
    RuntimeInitializationError,
    SynchronizationError,
)
from src.runtime.synchronizer import TwinSyncOutput, TwinSynchronizer
from src.storage.base import (
    StateHistoryRepository,
    TelemetryRepository,
    TwinStateRecord,
)
from src.telemetry.snapshots import TelemetrySnapshot


class DigitalTwinInstance:
    """Universal Battery Digital Twin Runtime Instance.

    Coordinates discrete-time co-simulation, state estimation, physical residual tracking,
    anomaly detection, event publication, and state history persistence.
    """

    def __init__(
        self,
        battery_pack: BatteryPack,
        battery_model: BatteryModel,
        state_estimator: Optional[StateEstimator] = None,
        health_estimator: Optional[Any] = None,
        parameter_identifier: Optional[Any] = None,
        validation_engine: Optional[Any] = None,
        event_bus: Optional[AbstractEventBus] = None,
        telemetry_repo: Optional[TelemetryRepository] = None,
        state_repo: Optional[StateHistoryRepository] = None,
        ingestion_pipeline: Optional[IngestionPipeline] = None,
        config: Optional[RuntimeConfig] = None,
    ) -> None:
        if not isinstance(battery_pack, BatteryPack):
            raise RuntimeInitializationError(
                f"Expected BatteryPack instance, got {type(battery_pack).__name__}."
            )
        if not isinstance(battery_model, BatteryModel):
            raise RuntimeInitializationError(
                f"Expected BatteryModel instance, got {type(battery_model).__name__}."
            )
        if state_estimator is not None and not isinstance(state_estimator, StateEstimator):
            raise RuntimeInitializationError(
                f"Expected StateEstimator, got {type(state_estimator).__name__}."
            )
        if event_bus is not None and not isinstance(event_bus, AbstractEventBus):
            raise RuntimeInitializationError(
                f"Expected AbstractEventBus, got {type(event_bus).__name__}."
            )

        self._pack = battery_pack
        self._model = battery_model
        self._estimator = state_estimator
        self._health_estimator = health_estimator
        self._parameter_identifier = parameter_identifier
        self._validation_engine = validation_engine
        self._event_bus = event_bus
        self._telemetry_repo = telemetry_repo
        self._state_repo = state_repo
        self._pipeline = ingestion_pipeline
        self._config = config or RuntimeConfig(system_id=battery_pack.pack_id)

        # Internal engines
        self._synchronizer = TwinSynchronizer(
            battery_model=self._model,
            state_estimator=self._estimator,
            config=self._config,
        )
        self._anomaly_detector = PhysicsAnomalyDetector(config=self._config)

        # Lifecycle and tracking state
        self._is_initialized = False
        self._latest_sync_output: Optional[TwinSyncOutput] = None
        self._latest_state_record: Optional[TwinStateRecord] = None
        self._latest_health_state: Optional[Any] = None
        self._latest_identified_parameters: Optional[Any] = None
        self._latest_validation_report: Optional[Any] = None
        self._last_published_r0: Optional[float] = None
        self._last_published_gating_status: Optional[str] = None
        self._last_published_validation_state: Optional[Any] = None
        self._total_steps = 0
        self._total_anomalies = 0

    # --------------------------------------------------------------------------
    # Properties
    # --------------------------------------------------------------------------
    @property
    def system_id(self) -> str:
        """Configured system or pack identifier."""
        return self._config.system_id

    @property
    def battery_pack(self) -> BatteryPack:
        """Physical battery pack domain entity."""
        return self._pack

    @property
    def battery_model(self) -> BatteryModel:
        """Active battery mathematical simulation model."""
        return self._model

    @property
    def state_estimator(self) -> Optional[StateEstimator]:
        """Active state estimator instance."""
        return self._estimator

    @property
    def event_bus(self) -> Optional[AbstractEventBus]:
        """Attached event bus."""
        return self._event_bus

    @property
    def telemetry_repository(self) -> Optional[TelemetryRepository]:
        """Attached telemetry persistence repository."""
        return self._telemetry_repo

    @property
    def state_history_repository(self) -> Optional[StateHistoryRepository]:
        """Attached digital twin state history repository."""
        return self._state_repo

    @property
    def ingestion_pipeline(self) -> Optional[IngestionPipeline]:
        """Attached ingestion pipeline."""
        return self._pipeline

    @property
    def config(self) -> RuntimeConfig:
        """Active runtime configuration."""
        return self._config

    @property
    def synchronizer(self) -> TwinSynchronizer:
        """Underlying synchronizer engine."""
        return self._synchronizer

    @property
    def anomaly_detector(self) -> PhysicsAnomalyDetector:
        """Underlying physics anomaly detector."""
        return self._anomaly_detector

    @property
    def is_initialized(self) -> bool:
        """True if the runtime instance has completed initialization."""
        return self._is_initialized

    @property
    def current_model_state(self) -> ModelState:
        """Current internal state vector of the simulation model."""
        return self._model.state

    @property
    def current_estimation_state(self) -> Optional[EstimationState]:
        """Current internal state vector of the state estimator, if attached."""
        return self._estimator.state if self._estimator else None

    @property
    def health_estimator(self) -> Optional[Any]:
        """Active State of Health estimator, if attached."""
        return self._health_estimator

    @property
    def latest_health_state(self) -> Optional[Any]:
        """Most recent calculated battery health state."""
        return self._latest_health_state

    @property
    def parameter_identifier(self) -> Optional[Any]:
        """Active Online Parameter Identification engine, if attached."""
        return self._parameter_identifier

    @property
    def latest_identified_parameters(self) -> Optional[Any]:
        """Most recent online identified parameter snapshot."""
        return self._latest_identified_parameters

    @property
    def validation_engine(self) -> Optional[Any]:
        """Active Behavioral Validation and Residual Analysis engine, if attached."""
        return self._validation_engine

    @property
    def latest_validation_report(self) -> Optional[Any]:
        """Most recent ModelValidationReport."""
        return self._latest_validation_report

    @property
    def latest_sync_output(self) -> Optional[TwinSyncOutput]:
        """The most recent synchronization output vector."""
        return self._latest_sync_output

    @property
    def latest_state_record(self) -> Optional[TwinStateRecord]:
        """The most recent persisted digital twin state history record."""
        return self._latest_state_record

    @property
    def total_steps(self) -> int:
        """Total number of discrete synchronization steps executed."""
        return self._total_steps

    @property
    def total_anomalies(self) -> int:
        """Cumulative count of detected anomalies across all cycles."""
        return self._total_anomalies

    # --------------------------------------------------------------------------
    # Lifecycle Management
    # --------------------------------------------------------------------------
    def initialize(
        self,
        initial_soc: float = 1.0,
        initial_soh: float = 1.0,
        temperature_c: float = 25.0,
        **kwargs: Any,
    ) -> "DigitalTwinInstance":
        """Initializes all constituent models, estimators, and internal engines.

        Args:
            initial_soc: Initial State of Charge fraction in [0.0, 1.0].
            initial_soh: Initial State of Health fraction in [0.0, 1.0].
            temperature_c: Initial battery temperature in Celsius.
            **kwargs: Additional model/estimator-specific initialization arguments.

        Returns:
            Self for fluent method chaining.
        """
        try:
            self._model.initialize(
                soc_init=initial_soc,
                temperature_c=temperature_c,
                **kwargs,
            )
            if self._estimator is not None:
                self._estimator.initialize(
                    initial_soc=initial_soc,
                    initial_soh=initial_soh,
                    temperature_c=temperature_c,
                    **kwargs,
                )
            self._synchronizer.reset()
            self._anomaly_detector.reset()
            if self._health_estimator is not None and hasattr(self._health_estimator, "reset"):
                self._health_estimator.reset()
            if self._parameter_identifier is not None and hasattr(self._parameter_identifier, "reset"):
                self._parameter_identifier.reset()
            if self._validation_engine is not None and hasattr(self._validation_engine, "reset"):
                self._validation_engine.reset()
            self._latest_health_state = None
            self._latest_identified_parameters = None
            self._latest_validation_report = None
            self._last_published_r0 = None
            self._last_published_gating_status = None
            self._last_published_validation_state = None
            self._is_initialized = True
            return self
        except Exception as exc:
            self._is_initialized = False
            raise RuntimeInitializationError(
                f"DigitalTwinInstance '{self.system_id}' failed to initialize: {exc}",
                system_id=self.system_id,
            ) from exc

    def reset(self) -> None:
        """Resets the digital twin state and internal counters."""
        self._model.reset()
        if self._estimator is not None:
            self._estimator.reset()
        self._synchronizer.reset()
        self._anomaly_detector.reset()
        if self._health_estimator is not None and hasattr(self._health_estimator, "reset"):
            self._health_estimator.reset()
        if self._parameter_identifier is not None and hasattr(self._parameter_identifier, "reset"):
            self._parameter_identifier.reset()
        if self._validation_engine is not None and hasattr(self._validation_engine, "reset"):
            self._validation_engine.reset()
        self._latest_health_state = None
        self._latest_identified_parameters = None
        self._latest_validation_report = None
        self._last_published_r0 = None
        self._last_published_gating_status = None
        self._last_published_validation_state = None
        self._latest_sync_output = None
        self._latest_state_record = None
        self._total_steps = 0
        self._total_anomalies = 0
        self._is_initialized = False

    # --------------------------------------------------------------------------
    # Stepping & Orchestration
    # --------------------------------------------------------------------------
    def step(self, snapshot: TelemetrySnapshot) -> TwinSyncOutput:
        """Executes a full digital twin co-simulation cycle for incoming telemetry.

        Workflow:
        1. Auto-publishes TelemetryReceivedEvent to EventBus.
        2. Persists TelemetrySnapshot to TelemetryRepository (if configured).
        3. Executes TwinSynchronizer discrete step (Model + Estimator).
        4. Evaluates PhysicsAnomalyDetector on synchronization output.
        5. Constructs and persists TwinStateRecord to StateHistoryRepository.
        6. Publishes TwinSynchronizedEvent, StateEstimatedEvent, and Anomaly alerts to EventBus.

        Args:
            snapshot: Canonical TelemetrySnapshot.

        Returns:
            TwinSyncOutput containing complete co-simulation outputs and residuals.
        """
        if not self._is_initialized:
            # Auto-initialize with default parameters if step is called directly
            self.initialize(
                initial_soc=snapshot.soc_fraction if snapshot.soc_fraction is not None else 1.0,
                initial_soh=snapshot.soh_fraction if snapshot.soh_fraction is not None else 1.0,
                temperature_c=(
                    snapshot.avg_cell_temperature_c
                    if snapshot.avg_cell_temperature_c is not None
                    else (snapshot.max_cell_temperature_c or 25.0)
                ),
            )

        # 1. Event: Telemetry Received
        if self._event_bus is not None and self._config.auto_publish_events:
            self._event_bus.publish(
                TelemetryReceivedEvent(
                    snapshot=snapshot,
                    source_id=snapshot.system_id,
                    timestamp_ns=snapshot.timestamp_ns,
                )
            )

        # 2. Persistence: Telemetry Snapshot
        if self._telemetry_repo is not None and self._config.auto_persist_records:
            self._telemetry_repo.append(snapshot)
            if self._event_bus is not None and self._config.auto_publish_events:
                self._event_bus.publish(
                    TelemetryPersistedEvent(
                        snapshot_id=snapshot.snapshot_id,
                        system_id=snapshot.system_id,
                        storage_backend=getattr(self._telemetry_repo, "backend_name", "repository"),
                        timestamp_ns=snapshot.timestamp_ns,
                    )
                )

        # 3. Synchronizer Discrete Step
        try:
            sync_output = self._synchronizer.step(snapshot)
        except Exception as exc:
            raise RuntimeExecutionError(
                f"DigitalTwinInstance '{self.system_id}' step execution failed: {exc}",
                system_id=self.system_id,
                details={"snapshot_id": snapshot.snapshot_id, "timestamp_ns": snapshot.timestamp_ns},
            ) from exc

        # 4. Physics-Informed Anomaly Detection
        if self._config.enable_anomaly_detection:
            anomaly_report = self._anomaly_detector.evaluate(sync_output)
        else:
            anomaly_report = AnomalyReport()

        # 5. Construct TwinStateRecord
        record_id = f"rec_{snapshot.system_id}_{sync_output.step_index}_{snapshot.timestamp_ns}"
        twin_record = TwinStateRecord(
            record_id=record_id,
            system_id=snapshot.system_id,
            timestamp_ns=sync_output.timestamp_ns,
            model_state=sync_output.model_output.state,
            estimation_state=sync_output.estimation_output.state if sync_output.estimation_output else None,
            residuals=sync_output.residuals,
            quality=sync_output.quality,
            metadata={
                "step_index": str(sync_output.step_index),
                "max_anomaly_severity": anomaly_report.max_severity,
                "anomalies_count": str(len(anomaly_report.anomalies)),
            },
        )

        # 6. Persistence: Twin State Record
        if self._state_repo is not None and self._config.auto_persist_records:
            self._state_repo.append(twin_record)

        # 7. Events: Synchronization, Estimation, and Anomaly Broadcasts
        if self._event_bus is not None and self._config.auto_publish_events:
            # Broadcast Synchronized Event
            self._event_bus.publish(
                TwinSynchronizedEvent(
                    twin_record=twin_record,
                    source_id=snapshot.system_id,
                    timestamp_ns=snapshot.timestamp_ns,
                )
            )

            # Broadcast Estimator Update (if state estimator produced an output)
            if sync_output.estimation_output is not None:
                self._event_bus.publish(
                    StateEstimatedEvent(
                        estimation_state=sync_output.estimation_output.state,
                        source_id=snapshot.system_id,
                        timestamp_ns=snapshot.timestamp_ns,
                    )
                )

            # Broadcast Anomaly & Thermal Alerts
            for anomaly in anomaly_report.anomalies:
                self._event_bus.publish(
                    BatteryAnomalyDetectedEvent(
                        system_id=snapshot.system_id,
                        anomaly_type=anomaly.anomaly_type,
                        observed_value=anomaly.observed_value,
                        expected_value=anomaly.expected_value,
                        residual=anomaly.residual,
                        severity=anomaly.severity,
                        description=anomaly.description,
                        source_id=snapshot.system_id,
                        timestamp_ns=snapshot.timestamp_ns,
                    )
                )
                if anomaly.anomaly_type in ("THERMAL_RUNAWAY_PRECURSOR", "THERMAL_DIVERGENCE"):
                    self._event_bus.publish(
                        ThermalAlertEvent(
                            system_id=snapshot.system_id,
                            temperature_c=anomaly.observed_value,
                            threshold_c=anomaly.expected_value,
                            severity=anomaly.severity,
                            cell_id=anomaly.cell_id,
                            source_id=snapshot.system_id,
                            timestamp_ns=snapshot.timestamp_ns,
                        )
                    )

        # 8. State of Health (SOH) & Degradation Estimation
        if self._health_estimator is not None:
            try:
                health_state = self._health_estimator.update(
                    snapshot=snapshot,
                    dt_s=sync_output.dt_s,
                    pack=self._pack,
                    sync_output=sync_output,
                )
                self._latest_health_state = health_state

                if self._event_bus is not None and self._config.auto_publish_events:
                    from src.analytics.events import BatteryHealthUpdatedEvent
                    self._event_bus.publish(
                        BatteryHealthUpdatedEvent(
                            health_state=health_state,
                            source_id=snapshot.system_id,
                            timestamp_ns=snapshot.timestamp_ns,
                        )
                    )
            except Exception:
                pass

        # 9. Online Parameter Identification & Calibration (Level 5.2)
        if self._parameter_identifier is not None:
            try:
                param_set = self._parameter_identifier.update(
                    snapshot=snapshot,
                    sync_output=sync_output,
                    dt_s=sync_output.dt_s,
                )
                self._latest_identified_parameters = param_set

                # Throttled event publishing:
                # - R0 change > 1% relative to last published event, OR
                # - periodic heartbeat every 100 steps, OR
                # - gating status transition
                should_publish = False
                if self._last_published_r0 is None:
                    should_publish = True
                elif abs(param_set.r0_ohm - self._last_published_r0) / max(1e-6, self._last_published_r0) >= 0.01:
                    should_publish = True
                elif self._total_steps % 100 == 0:
                    should_publish = True
                elif param_set.gating_status != self._last_published_gating_status:
                    should_publish = True

                if should_publish and self._event_bus is not None and self._config.auto_publish_events:
                    from src.calibration.events import ParameterIdentificationUpdatedEvent
                    self._event_bus.publish(
                        ParameterIdentificationUpdatedEvent(
                            parameter_set=param_set,
                            source_id=snapshot.system_id,
                            timestamp_ns=snapshot.timestamp_ns,
                        )
                    )
                    self._last_published_r0 = param_set.r0_ohm
                    self._last_published_gating_status = param_set.gating_status
            except Exception:
                pass

        # 10. Behavioral Validation & Residual Analysis (Level 5.3)
        if self._validation_engine is not None:
            try:
                val_report = self._validation_engine.update(
                    snapshot=snapshot,
                    sync_output=sync_output,
                    latest_identified_params=self._latest_identified_parameters,
                    dt_s=sync_output.dt_s,
                )
                self._latest_validation_report = val_report

                # Throttled event publishing:
                # - initial sample, OR
                # - completed window sealed, OR
                # - validation state transition, OR
                # - periodic heartbeat every 100 steps
                should_publish_val = False
                curr_val_state = val_report.active_window.state
                if self._last_published_validation_state is None:
                    should_publish_val = True
                elif curr_val_state != self._last_published_validation_state:
                    should_publish_val = True
                elif val_report.latest_completed_window is not None and self._total_steps % 100 == 0:
                    should_publish_val = True

                if should_publish_val and self._event_bus is not None and self._config.auto_publish_events:
                    from src.validation.events import BatteryValidationUpdatedEvent
                    self._event_bus.publish(
                        BatteryValidationUpdatedEvent(
                            validation_report=val_report,
                            source_id=snapshot.system_id,
                            timestamp_ns=snapshot.timestamp_ns,
                        )
                    )
                    self._last_published_validation_state = curr_val_state
            except Exception:
                pass

        # 11. Update Internal Tracking
        self._latest_sync_output = sync_output
        self._latest_state_record = twin_record
        self._total_steps += 1
        self._total_anomalies += len(anomaly_report.anomalies)

        return sync_output

    def step_raw(
        self,
        raw_data: Union[str, bytes, Mapping[str, Any]],
        format_identifier: Optional[str] = None,
        source_id: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> TwinSyncOutput:
        """Ingests raw external telemetry payload and executes a digital twin synchronization step.

        Uses the attached IngestionPipeline (or instantiates a default IngestionPipeline)
        to parse and validate raw bytes, JSON strings, or CSV rows before stepping.

        Args:
            raw_data: Raw byte frame, JSON string, or dictionary.
            format_identifier: Optional format tag ("JSON", "CSV", "SERIAL_FRAME").
            source_id: Optional source system identifier override.
            headers: Optional transport metadata headers.

        Returns:
            TwinSyncOutput resulting from the ingested telemetry step.

        Raises:
            SynchronizationError: If the ingestion pipeline rejects or drops the payload.
        """
        pipeline = self._pipeline or IngestionPipeline()
        ingest_result = pipeline.ingest(
            raw_data=raw_data,
            format_identifier=format_identifier,
            source_id=source_id or self.system_id,
            headers=headers,
        )

        if not ingest_result.is_success or ingest_result.snapshot is None:
            err_msg = ", ".join(ingest_result.errors) if ingest_result.errors else "Payload rejected."
            raise SynchronizationError(
                f"Ingestion pipeline failed to parse payload ({ingest_result.status.value}): {err_msg}",
                system_id=self.system_id,
                details={"errors": list(ingest_result.errors), "status": ingest_result.status.value},
            )

        return self.step(ingest_result.snapshot)
