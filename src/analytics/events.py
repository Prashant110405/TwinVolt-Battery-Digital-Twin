"""Domain events for Battery Health and Degradation Analytics."""

from dataclasses import dataclass
from typing import Optional

from src.analytics.types import BatteryHealthState
from src.events.base import TwinEvent


@dataclass(frozen=True)
class BatteryHealthUpdatedEvent(TwinEvent):
    """Published when battery State of Health (SOH) and degradation metrics are updated."""

    health_state: Optional[BatteryHealthState] = None
    event_type: str = "twin.health"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.health_state is not None:
            if self.source_id == "system":
                object.__setattr__(self, "source_id", self.health_state.system_id)
            if self.timestamp_ns == 0:
                object.__setattr__(self, "timestamp_ns", self.health_state.timestamp_ns)
            if not self.payload:
                object.__setattr__(self, "payload", self.health_state.to_dict())
