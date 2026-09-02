"""Base Event Model and EventBus Protocols.

Defines the core immutable TwinEvent container and the runtime EventBus protocol.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time
from typing import Any, Callable, Mapping, Optional, Protocol, runtime_checkable
import uuid

from src.events.exceptions import InvalidEventError


@dataclass(frozen=True)
class TwinEvent:
    """Immutable, strongly-typed domain event representing a significant state change or observation."""

    event_type: str
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())
    source_id: str = "system"
    correlation_id: Optional[str] = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_type or not self.event_type.strip():
            raise InvalidEventError("event_type cannot be empty.")
        if not self.event_id or not self.event_id.strip():
            raise InvalidEventError("event_id cannot be empty.")
        if self.timestamp_ns < 0:
            raise InvalidEventError(f"timestamp_ns cannot be negative, got {self.timestamp_ns}.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes event to a dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp_ns": self.timestamp_ns,
            "source_id": self.source_id,
            "correlation_id": self.correlation_id,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
        }


# Type alias for event handler callbacks
EventHandler = Callable[[TwinEvent], None]


@runtime_checkable
class EventBus(Protocol):
    """Protocol for in-process event publish-subscribe notification brokers."""

    def publish(self, event: TwinEvent) -> int:
        """Publishes an event to all registered matching subscribers.

        Returns:
            The number of subscribers successfully invoked.
        """
        ...

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        priority: int = 100,
    ) -> str:
        """Subscribes an event handler callback to a specific event type or wildcard pattern.

        Args:
            event_type: Target event type string (e.g., "telemetry.received" or "*").
            handler: Callable accepting a single TwinEvent argument.
            priority: Invocation priority (lower integer = executed earlier, default 100).

        Returns:
            Unique subscription ID for subsequent unsubscription.
        """
        ...

    def unsubscribe(self, subscription_id: str) -> bool:
        """Removes a subscriber by its subscription ID.

        Returns:
            True if the subscription was found and removed, False otherwise.
        """
        ...

    def clear_subscribers(self) -> None:
        """Removes all registered subscribers."""
        ...

    def subscribers_count(self, event_type: Optional[str] = None) -> int:
        """Returns the number of active subscribers for a given event type or all types."""
        ...


class AbstractEventBus(ABC, EventBus):
    """Abstract base class for EventBus implementations."""

    @abstractmethod
    def publish(self, event: TwinEvent) -> int:
        """Publishes event."""
        ...

    @abstractmethod
    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        priority: int = 100,
    ) -> str:
        """Subscribes handler."""
        ...

    @abstractmethod
    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribes handler."""
        ...

    @abstractmethod
    def clear_subscribers(self) -> None:
        """Clears subscribers."""
        ...

    @abstractmethod
    def subscribers_count(self, event_type: Optional[str] = None) -> int:
        """Counts subscribers."""
        ...
