"""Event Bus and Observability Subsystem.

Provides immutable domain events, priority-ordered in-process EventBus dispatching,
fault isolation, and lightweight observability metrics.
"""

from src.events.base import (
    AbstractEventBus,
    EventBus,
    EventHandler,
    TwinEvent,
)
from src.events.bus import DigitalTwinEventBus
from src.events.exceptions import (
    EventError,
    HandlerExecutionError,
    InvalidEventError,
    SubscriptionError,
)
from src.events.observability import (
    DiagnosticAuditLogger,
    ObservabilityMetrics,
)
from src.events.types import (
    BatteryAnomalyDetectedEvent,
    StateEstimatedEvent,
    TelemetryPersistedEvent,
    TelemetryReceivedEvent,
    ThermalAlertEvent,
    TwinSynchronizedEvent,
)

__all__ = [
    "TwinEvent",
    "EventBus",
    "AbstractEventBus",
    "EventHandler",
    "DigitalTwinEventBus",
    "TelemetryReceivedEvent",
    "TelemetryPersistedEvent",
    "StateEstimatedEvent",
    "TwinSynchronizedEvent",
    "ThermalAlertEvent",
    "BatteryAnomalyDetectedEvent",
    "ObservabilityMetrics",
    "DiagnosticAuditLogger",
    "EventError",
    "InvalidEventError",
    "SubscriptionError",
    "HandlerExecutionError",
]
