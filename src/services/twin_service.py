"""Digital Twin Lifecycle and Co-Simulation Application Service.

Coordinates instantiation, stepping, history querying, and lifecycle operations
for DigitalTwinInstance objects without transport or HTTP dependencies.
"""

import threading
from typing import Any, Mapping, Optional, Sequence, Union

from src.domain.battery.entities import BatteryPack
from src.estimators.base import StateEstimator
from src.events.bus import AbstractEventBus
from src.ingestion.pipeline import IngestionPipeline
from src.models.base import BatteryModel
from src.runtime.config import RuntimeConfig
from src.runtime.instance import DigitalTwinInstance
from src.runtime.synchronizer import TwinSyncOutput
from src.services.exceptions import DuplicateEntityError, TwinNotFoundError
from src.storage.base import (
    StateHistoryRepository,
    TelemetryRepository,
    TwinStateRecord,
)
from src.telemetry.snapshots import TelemetrySnapshot


class TwinApplicationService:
    """Application service for managing active Digital Twin instances and runtime lifecycles.

    Coordinates model assembly, dependency injection (EventBus, Repositories, Pipeline),
    discrete-time co-simulation steps, and historical state queries.
    """

    def __init__(
        self,
        event_bus: Optional[AbstractEventBus] = None,
        telemetry_repo: Optional[TelemetryRepository] = None,
        state_repo: Optional[StateHistoryRepository] = None,
        ingestion_pipeline: Optional[IngestionPipeline] = None,
    ) -> None:
        self._event_bus = event_bus
        self._telemetry_repo = telemetry_repo
        self._state_repo = state_repo
        self._pipeline = ingestion_pipeline
        self._twins: dict[str, DigitalTwinInstance] = {}
        self._lock = threading.RLock()

    @property
    def event_bus(self) -> Optional[AbstractEventBus]:
        """Injected domain event bus."""
        return self._event_bus

    @property
    def telemetry_repository(self) -> Optional[TelemetryRepository]:
        """Injected telemetry repository."""
        return self._telemetry_repo

    @property
    def state_history_repository(self) -> Optional[StateHistoryRepository]:
        """Injected state history repository."""
        return self._state_repo

    @property
    def ingestion_pipeline(self) -> Optional[IngestionPipeline]:
        """Injected ingestion pipeline."""
        return self._pipeline

    def create_twin(
        self,
        system_id: str,
        battery_pack: BatteryPack,
        battery_model: BatteryModel,
        state_estimator: Optional[StateEstimator] = None,
        health_estimator: Optional[Any] = None,
        parameter_identifier: Optional[Any] = None,
        validation_engine: Optional[Any] = None,
        config: Optional[RuntimeConfig] = None,
        overwrite: bool = False,
    ) -> DigitalTwinInstance:
        """Assembles and registers a new DigitalTwinInstance with injected infrastructure.

        Args:
            system_id: Unique battery system identifier.
            battery_pack: BatteryPack domain entity.
            battery_model: BatteryModel simulation engine.
            state_estimator: Optional StateEstimator.
            health_estimator: Optional StateOfHealthEstimator.
            parameter_identifier: Optional Online Parameter Identifier engine.
            validation_engine: Optional Behavioral Validation & Residual Analysis engine.
            config: Optional RuntimeConfig.
            overwrite: If True, replaces existing twin with same system_id.

        Returns:
            Registered DigitalTwinInstance.

        Raises:
            DuplicateEntityError: If system_id is already active and overwrite is False.
        """
        with self._lock:
            if system_id in self._twins and not overwrite:
                raise DuplicateEntityError(
                    f"Digital twin instance '{system_id}' already exists.",
                    service_name="TwinApplicationService",
                    details={"system_id": system_id},
                )

            twin_cfg = config or RuntimeConfig(system_id=system_id)
            instance = DigitalTwinInstance(
                battery_pack=battery_pack,
                battery_model=battery_model,
                state_estimator=state_estimator,
                health_estimator=health_estimator,
                parameter_identifier=parameter_identifier,
                validation_engine=validation_engine,
                event_bus=self._event_bus,
                telemetry_repo=self._telemetry_repo,
                state_repo=self._state_repo,
                ingestion_pipeline=self._pipeline,
                config=twin_cfg,
            )

            self._twins[system_id] = instance
            return instance

    def register_twin_instance(
        self,
        instance: DigitalTwinInstance,
        overwrite: bool = False,
    ) -> DigitalTwinInstance:
        """Registers an existing pre-assembled DigitalTwinInstance.

        Args:
            instance: DigitalTwinInstance to register.
            overwrite: If True, replaces existing twin with same system_id.

        Returns:
            The registered DigitalTwinInstance.
        """
        if not isinstance(instance, DigitalTwinInstance):
            raise TypeError(f"Expected DigitalTwinInstance, got {type(instance).__name__}.")

        with self._lock:
            sys_id = instance.system_id
            if sys_id in self._twins and not overwrite:
                raise DuplicateEntityError(
                    f"Digital twin instance '{sys_id}' already exists.",
                    service_name="TwinApplicationService",
                    details={"system_id": sys_id},
                )
            self._twins[sys_id] = instance
            return instance

    def get_twin(self, system_id: str) -> DigitalTwinInstance:
        """Retrieves an active DigitalTwinInstance by system identifier.

        Args:
            system_id: Target battery system identifier.

        Returns:
            DigitalTwinInstance.

        Raises:
            TwinNotFoundError: If twin is not active in the registry.
        """
        with self._lock:
            twin = self._twins.get(system_id)
            if twin is None:
                raise TwinNotFoundError(
                    f"Digital twin '{system_id}' not found.",
                    service_name="TwinApplicationService",
                    details={"system_id": system_id},
                )
            return twin

    def initialize_twin(
        self,
        system_id: str,
        initial_soc: float = 1.0,
        initial_soh: float = 1.0,
        temperature_c: float = 25.0,
        **kwargs: Any,
    ) -> DigitalTwinInstance:
        """Initializes an active digital twin instance.

        Args:
            system_id: Battery system identifier.
            initial_soc: Initial SOC fraction in [0.0, 1.0].
            initial_soh: Initial SOH fraction in [0.0, 1.0].
            temperature_c: Initial temperature in Celsius.

        Returns:
            Initialized DigitalTwinInstance.
        """
        twin = self.get_twin(system_id)
        twin.initialize(
            initial_soc=initial_soc,
            initial_soh=initial_soh,
            temperature_c=temperature_c,
            **kwargs,
        )
        return twin

    def step_twin(
        self,
        system_id: str,
        snapshot: TelemetrySnapshot,
    ) -> TwinSyncOutput:
        """Executes a synchronized discrete co-simulation step for a digital twin.

        Args:
            system_id: Target battery system identifier.
            snapshot: Canonical TelemetrySnapshot observation.

        Returns:
            TwinSyncOutput containing model outputs, estimator state, and physical residuals.
        """
        twin = self.get_twin(system_id)
        return twin.step(snapshot)

    def step_raw_twin(
        self,
        system_id: str,
        raw_payload: Union[str, bytes, Mapping[str, Any]],
        format_identifier: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> TwinSyncOutput:
        """Parses raw external payload and executes a synchronized step on the target twin.

        Args:
            system_id: Target battery system identifier.
            raw_payload: Raw CSV string, JSON string/dict, or byte frame.
            format_identifier: Format hint ("CSV", "JSON", "SERIAL_FRAME").
            headers: Optional transport metadata headers.

        Returns:
            TwinSyncOutput.
        """
        twin = self.get_twin(system_id)
        return twin.step_raw(
            raw_data=raw_payload,
            format_identifier=format_identifier,
            source_id=system_id,
            headers=headers,
        )

    def get_latest_state(self, system_id: str) -> Optional[TwinStateRecord]:
        """Retrieves the latest state record for a given battery system.

        First checks the active in-memory twin instance; falls back to state history repository.

        Args:
            system_id: Battery system identifier.

        Returns:
            Latest TwinStateRecord, or None if no state is available.
        """
        with self._lock:
            twin = self._twins.get(system_id)
            if twin is not None and twin.latest_state_record is not None:
                return twin.latest_state_record

            if self._state_repo is not None:
                return self._state_repo.get_latest(system_id)

            return None

    def get_twin_health(self, system_id: str) -> Optional[Any]:
        """Retrieves the latest BatteryHealthState for an active digital twin.

        Args:
            system_id: Target battery system identifier.

        Returns:
            Latest BatteryHealthState, or None if health estimator is unconfigured or not yet stepped.

        Raises:
            TwinNotFoundError: If the twin instance does not exist.
        """
        twin = self.get_twin(system_id)
        return twin.latest_health_state

    def get_twin_calibration(self, system_id: str) -> Optional[Any]:
        """Retrieves the latest IdentifiedParameterSet for an active digital twin.

        Args:
            system_id: Target battery system identifier.

        Returns:
            Latest IdentifiedParameterSet, or None if parameter identification is unconfigured or not yet stepped.

        Raises:
            TwinNotFoundError: If the twin instance does not exist.
        """
        twin = self.get_twin(system_id)
        return twin.latest_identified_parameters

    def get_twin_validation(self, system_id: str) -> Optional[Any]:
        """Retrieves the latest ModelValidationReport for an active digital twin.

        Args:
            system_id: Target battery system identifier.

        Returns:
            Latest ModelValidationReport, or None if validation engine is unconfigured or not yet stepped.

        Raises:
            TwinNotFoundError: If the twin instance does not exist.
        """
        twin = self.get_twin(system_id)
        return twin.latest_validation_report

    def get_twin_validation_history(self, system_id: str) -> tuple[Any, ...]:
        """Retrieves completed validation window reports from the twin's in-memory ring buffer.

        Args:
            system_id: Target battery system identifier.

        Returns:
            Tuple of ValidationWindowReport snapshots.

        Raises:
            TwinNotFoundError: If the twin instance does not exist.
        """
        twin = self.get_twin(system_id)
        if twin.validation_engine is not None:
            return twin.validation_engine.validation_history
        return ()

    def get_twin_parameter_validation(self, system_id: str) -> Optional[Any]:
        """Retrieves the latest ParameterValidationEvidence for an active digital twin.

        Args:
            system_id: Target battery system identifier.

        Returns:
            Latest ParameterValidationEvidence, or None if unavailable.

        Raises:
            TwinNotFoundError: If the twin instance does not exist.
        """
        report = self.get_twin_validation(system_id)
        if report is not None:
            return report.parameter_evidence
        return None

    def get_state_history(
        self,
        system_id: str,
        start_time_ns: Optional[int] = None,
        end_time_ns: Optional[int] = None,
        limit: Optional[int] = None,
        descending: bool = False,
    ) -> tuple[TwinStateRecord, ...]:
        """Queries historical digital twin state records from the repository.

        Args:
            system_id: Battery system identifier.
            start_time_ns: Optional start timestamp filter.
            end_time_ns: Optional end timestamp filter.
            limit: Maximum records to return.
            descending: Order descending if True.

        Returns:
            Tuple of TwinStateRecord instances.
        """
        if self._state_repo is None:
            return ()
        return self._state_repo.query_by_time_range(
            system_id=system_id,
            start_time_ns=start_time_ns,
            end_time_ns=end_time_ns,
            limit=limit,
            descending=descending,
        )

    def get_telemetry_history(
        self,
        system_id: str,
        start_time_ns: Optional[int] = None,
        end_time_ns: Optional[int] = None,
        limit: Optional[int] = None,
        descending: bool = False,
    ) -> tuple[TelemetrySnapshot, ...]:
        """Queries historical telemetry snapshots from the repository.

        Args:
            system_id: Battery system identifier.
            start_time_ns: Optional start timestamp filter.
            end_time_ns: Optional end timestamp filter.
            limit: Maximum records to return.
            descending: Order descending if True.

        Returns:
            Tuple of TelemetrySnapshot instances.
        """
        if self._telemetry_repo is None:
            return ()
        return self._telemetry_repo.query_by_time_range(
            system_id=system_id,
            start_time_ns=start_time_ns,
            end_time_ns=end_time_ns,
            limit=limit,
            descending=descending,
        )

    def reset_twin(self, system_id: str) -> None:
        """Resets the internal state and history of an active digital twin.

        Args:
            system_id: Battery system identifier.
        """
        twin = self.get_twin(system_id)
        twin.reset()

    def delete_twin(self, system_id: str) -> bool:
        """Unregisters and removes a digital twin instance.

        Args:
            system_id: Battery system identifier.

        Returns:
            True if removed, False if twin was not registered.
        """
        with self._lock:
            if system_id in self._twins:
                del self._twins[system_id]
                return True
            return False

    def list_active_twins(self) -> tuple[str, ...]:
        """Lists identifiers of all currently registered digital twin instances."""
        with self._lock:
            return tuple(self._twins.keys())

    def exists(self, system_id: str) -> bool:
        """Checks if a digital twin identifier is active in the registry."""
        with self._lock:
            return system_id in self._twins

    @property
    def count(self) -> int:
        """Total number of active twin instances."""
        with self._lock:
            return len(self._twins)

    def clear(self) -> None:
        """Clears all active twin instances."""
        with self._lock:
            self._twins.clear()
