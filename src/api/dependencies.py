"""Dependency Injection Providers for TwinVolt REST API.

Provides clean, explicit service dependency wiring without global mutable singletons.
"""

from dataclasses import dataclass
from typing import Optional
from fastapi import Depends, Request

from src.events.bus import DigitalTwinEventBus
from src.ingestion.pipeline import IngestionPipeline
from src.services.pack_service import PackManagementService
from src.services.replay_service import ReplayService
from src.services.telemetry_service import TelemetryIngestService
from src.services.twin_service import TwinApplicationService
from src.storage.base import StateHistoryRepository, TelemetryRepository
from src.storage.memory_repository import (
    InMemoryStateHistoryRepository,
    InMemoryTelemetryRepository,
)


@dataclass
class ServiceContainer:
    """Dependency container aggregating core application services and infrastructure."""

    pack_service: PackManagementService
    twin_service: TwinApplicationService
    telemetry_service: TelemetryIngestService
    replay_service: ReplayService
    event_bus: DigitalTwinEventBus
    telemetry_repo: TelemetryRepository
    state_repo: StateHistoryRepository
    ingestion_pipeline: IngestionPipeline


def create_default_services(
    telemetry_repo: Optional[TelemetryRepository] = None,
    state_repo: Optional[StateHistoryRepository] = None,
    event_bus: Optional[DigitalTwinEventBus] = None,
    pipeline: Optional[IngestionPipeline] = None,
) -> ServiceContainer:
    """Factory creating fully wired application services with default in-memory infrastructure."""
    t_repo = telemetry_repo or InMemoryTelemetryRepository()
    s_repo = state_repo or InMemoryStateHistoryRepository()
    e_bus = event_bus or DigitalTwinEventBus()
    ingest_pipe = pipeline or IngestionPipeline()

    pack_svc = PackManagementService()
    twin_svc = TwinApplicationService(
        event_bus=e_bus,
        telemetry_repo=t_repo,
        state_repo=s_repo,
        ingestion_pipeline=ingest_pipe,
    )
    telemetry_svc = TelemetryIngestService(
        ingestion_pipeline=ingest_pipe,
        twin_service=twin_svc,
        telemetry_repo=t_repo,
    )
    replay_svc = ReplayService(
        twin_service=twin_svc,
        telemetry_repo=t_repo,
    )

    return ServiceContainer(
        pack_service=pack_svc,
        twin_service=twin_svc,
        telemetry_service=telemetry_svc,
        replay_service=replay_svc,
        event_bus=e_bus,
        telemetry_repo=t_repo,
        state_repo=s_repo,
        ingestion_pipeline=ingest_pipe,
    )


def get_service_container(request: Request) -> ServiceContainer:
    """Retrieves the active ServiceContainer from FastAPI app state."""
    container = getattr(request.app.state, "services", None)
    if container is None:
        container = create_default_services()
        request.app.state.services = container
    return container


def get_pack_service(
    container: ServiceContainer = Depends(get_service_container),
) -> PackManagementService:
    """Provides the active PackManagementService."""
    return container.pack_service


def get_twin_service(
    container: ServiceContainer = Depends(get_service_container),
) -> TwinApplicationService:
    """Provides the active TwinApplicationService."""
    return container.twin_service


def get_telemetry_service(
    container: ServiceContainer = Depends(get_service_container),
) -> TelemetryIngestService:
    """Provides the active TelemetryIngestService."""
    return container.telemetry_service


def get_replay_service(
    container: ServiceContainer = Depends(get_service_container),
) -> ReplayService:
    """Provides the active ReplayService."""
    return container.replay_service
