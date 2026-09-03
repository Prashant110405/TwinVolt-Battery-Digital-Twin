"""Telemetry Ingestion and Routing Application Service.

Coordinates heterogeneous payload ingestion through IngestionPipeline and routes
canonical snapshots to active Digital Twin instances or storage repositories.
"""

from typing import Any, Mapping, Optional, Sequence, Union

from src.ingestion.pipeline import IngestionPipeline
from src.runtime.synchronizer import TwinSyncOutput
from src.services.exceptions import InvalidServiceOperationError, TwinNotFoundError
from src.services.twin_service import TwinApplicationService
from src.storage.base import TelemetryRepository
from src.telemetry.snapshots import TelemetrySnapshot


class TelemetryIngestService:
    """Application service for ingesting raw or canonical telemetry into digital twins and storage.

    Remains purely transport-agnostic; delegates parsing to IngestionPipeline and stepping
    to TwinApplicationService.
    """

    def __init__(
        self,
        ingestion_pipeline: Optional[IngestionPipeline] = None,
        twin_service: Optional[TwinApplicationService] = None,
        telemetry_repo: Optional[TelemetryRepository] = None,
    ) -> None:
        self._pipeline = ingestion_pipeline or IngestionPipeline()
        self._twin_service = twin_service
        self._telemetry_repo = telemetry_repo

    @property
    def ingestion_pipeline(self) -> IngestionPipeline:
        """Attached ingestion pipeline."""
        return self._pipeline

    @property
    def twin_service(self) -> Optional[TwinApplicationService]:
        """Attached twin application service."""
        return self._twin_service

    @property
    def telemetry_repository(self) -> Optional[TelemetryRepository]:
        """Attached telemetry repository."""
        return self._telemetry_repo

    def ingest_raw(
        self,
        system_id: str,
        raw_payload: Union[str, bytes, Mapping[str, Any]],
        format_identifier: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> TwinSyncOutput:
        """Parses raw external telemetry payload and routes it through the target digital twin.

        Args:
            system_id: Target battery system identifier.
            raw_payload: Raw CSV string, JSON string/dict, or byte frame.
            format_identifier: Format hint ("CSV", "JSON", "SERIAL_FRAME").
            headers: Optional transport metadata headers.

        Returns:
            TwinSyncOutput resulting from the twin co-simulation step.

        Raises:
            TwinNotFoundError: If twin_service is attached and system_id does not exist.
            InvalidServiceOperationError: If ingestion parsing fails.
        """
        if self._twin_service is not None:
            # Delegate directly to twin service step_raw
            return self._twin_service.step_raw_twin(
                system_id=system_id,
                raw_payload=raw_payload,
                format_identifier=format_identifier,
                headers=headers,
            )

        # Fallback: parse via pipeline and persist
        ingest_result = self._pipeline.ingest(
            raw_data=raw_payload,
            format_identifier=format_identifier,
            source_id=system_id,
            headers=headers,
        )

        if not ingest_result.is_success or ingest_result.snapshot is None:
            err_msg = ", ".join(ingest_result.errors) if ingest_result.errors else "Ingestion rejected."
            raise InvalidServiceOperationError(
                f"Failed to ingest raw payload for system '{system_id}': {err_msg}",
                service_name="TelemetryIngestService",
                details={"errors": list(ingest_result.errors), "status": ingest_result.status.value},
            )

        if self._telemetry_repo is not None:
            self._telemetry_repo.append(ingest_result.snapshot)

        raise InvalidServiceOperationError(
            f"Cannot execute twin step for '{system_id}': no TwinApplicationService is attached.",
            service_name="TelemetryIngestService",
        )

    def ingest_snapshot(
        self,
        snapshot: TelemetrySnapshot,
    ) -> Optional[TwinSyncOutput]:
        """Routes a canonical TelemetrySnapshot directly to its target digital twin or repository.

        Args:
            snapshot: Canonical TelemetrySnapshot instance.

        Returns:
            TwinSyncOutput if twin was stepped, or None if only persisted.
        """
        if not isinstance(snapshot, TelemetrySnapshot):
            raise TypeError(f"Expected TelemetrySnapshot, got {type(snapshot).__name__}.")

        if self._twin_service is not None and self._twin_service.exists(snapshot.system_id):
            return self._twin_service.step_twin(snapshot.system_id, snapshot)

        if self._telemetry_repo is not None:
            self._telemetry_repo.append(snapshot)

        return None

    def ingest_batch(
        self,
        system_id: str,
        snapshots: Sequence[TelemetrySnapshot],
    ) -> tuple[TwinSyncOutput, ...]:
        """Ingests an ordered sequence of TelemetrySnapshot instances for a battery system.

        Args:
            system_id: Target battery system identifier.
            snapshots: Ordered sequence of snapshots.

        Returns:
            Tuple of TwinSyncOutput instances.
        """
        outputs: list[TwinSyncOutput] = []
        for snap in snapshots:
            out = self.ingest_snapshot(snap)
            if out is not None:
                outputs.append(out)
        return tuple(outputs)
