"""Application Services and Orchestration Facades.

Provides transport-agnostic application services coordinating battery pack management,
digital twin instance lifecycles, telemetry ingestion, and drive-cycle replays.
"""

from src.services.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidServiceOperationError,
    PackNotFoundError,
    ServiceError,
    TwinNotFoundError,
)
from src.services.pack_service import PackManagementService
from src.services.replay_service import ReplayService
from src.services.telemetry_service import TelemetryIngestService
from src.services.twin_service import TwinApplicationService

__all__ = [
    # Services
    "PackManagementService",
    "TwinApplicationService",
    "TelemetryIngestService",
    "ReplayService",
    # Exceptions
    "ServiceError",
    "EntityNotFoundError",
    "PackNotFoundError",
    "TwinNotFoundError",
    "DuplicateEntityError",
    "InvalidServiceOperationError",
]
