"""Drive Cycle Simulation and Replay Application Service.

Coordinates benchmark drive-cycle simulation runs and tracking error evaluations
using DriveCycleReplayEngine over active DigitalTwinInstance objects.
"""

import threading
from typing import Optional

from src.replay.engine import (
    DriveCycleReplayEngine,
    ReplayConfig,
    ReplayResult,
)
from src.replay.profiles import DriveCycleProfile
from src.services.exceptions import InvalidServiceOperationError, TwinNotFoundError
from src.services.twin_service import TwinApplicationService
from src.storage.base import TelemetryRepository


class ReplayService:
    """Application service for orchestrating drive-cycle replays and tracking evaluations.

    Coordinates DriveCycleReplayEngine runs against digital twin instances managed
    by TwinApplicationService.
    """

    def __init__(
        self,
        twin_service: TwinApplicationService,
        replay_engine: Optional[DriveCycleReplayEngine] = None,
        telemetry_repo: Optional[TelemetryRepository] = None,
    ) -> None:
        if not isinstance(twin_service, TwinApplicationService):
            raise TypeError(f"Expected TwinApplicationService, got {type(twin_service).__name__}.")

        self._twin_service = twin_service
        self._engine = replay_engine or DriveCycleReplayEngine()
        self._telemetry_repo = telemetry_repo
        self._last_results: dict[str, ReplayResult] = {}
        self._lock = threading.RLock()

    @property
    def twin_service(self) -> TwinApplicationService:
        """Attached twin application service."""
        return self._twin_service

    @property
    def replay_engine(self) -> DriveCycleReplayEngine:
        """Attached drive cycle replay engine."""
        return self._engine

    def replay_profile(
        self,
        system_id: str,
        profile: DriveCycleProfile,
        config: Optional[ReplayConfig] = None,
    ) -> ReplayResult:
        """Executes a standard or custom drive cycle replay against an active digital twin.

        Args:
            system_id: Target battery system identifier.
            profile: DriveCycleProfile instance (WLTP, US06, DST, Pulse, CC).
            config: Optional replay configuration options.

        Returns:
            ReplayResult containing co-simulation outputs and tracking metrics report.

        Raises:
            TwinNotFoundError: If system_id is not registered in twin service.
        """
        twin = self._twin_service.get_twin(system_id)
        result = self._engine.replay_profile(
            instance=twin,
            profile=profile,
            config=config,
        )
        with self._lock:
            self._last_results[system_id] = result
        return result

    def replay_csv(
        self,
        system_id: str,
        csv_data: str,
        config: Optional[ReplayConfig] = None,
        profile_name: str = "csv_dataset",
    ) -> ReplayResult:
        """Replays a CSV time-series dataset against an active digital twin.

        Args:
            system_id: Target battery system identifier.
            csv_data: CSV text content or file path.
            config: Optional replay configuration options.
            profile_name: Dataset display name.

        Returns:
            ReplayResult.
        """
        twin = self._twin_service.get_twin(system_id)
        result = self._engine.replay_from_csv(
            instance=twin,
            csv_content_or_path=csv_data,
            config=config,
            profile_name=profile_name,
        )
        with self._lock:
            self._last_results[system_id] = result
        return result

    def replay_repository_data(
        self,
        system_id: str,
        start_time_ns: Optional[int] = None,
        end_time_ns: Optional[int] = None,
        config: Optional[ReplayConfig] = None,
    ) -> ReplayResult:
        """Replays stored historical telemetry snapshots from the repository against an active twin.

        Args:
            system_id: Target battery system identifier.
            start_time_ns: Optional start timestamp filter.
            end_time_ns: Optional end timestamp filter.
            config: Optional replay configuration options.

        Returns:
            ReplayResult.

        Raises:
            InvalidServiceOperationError: If no telemetry repository is configured.
        """
        twin = self._twin_service.get_twin(system_id)
        repo = self._telemetry_repo or twin.telemetry_repo

        if repo is None:
            raise InvalidServiceOperationError(
                f"Cannot replay repository data for '{system_id}': no TelemetryRepository available.",
                service_name="ReplayService",
            )

        result = self._engine.replay_from_repository(
            instance=twin,
            repository=repo,
            system_id=system_id,
            start_time_ns=start_time_ns,
            end_time_ns=end_time_ns,
            config=config,
        )
        with self._lock:
            self._last_results[system_id] = result
        return result

    def get_last_replay_result(self, system_id: str) -> Optional[ReplayResult]:
        """Retrieves the most recent replay result for a given battery system.

        Args:
            system_id: Battery system identifier.

        Returns:
            ReplayResult or None.
        """
        with self._lock:
            return self._last_results.get(system_id)
