"""Domain events for Online Parameter Identification and Calibration."""

from dataclasses import dataclass
from typing import Optional

from src.calibration.types import IdentifiedParameterSet
from src.events.base import TwinEvent


@dataclass(frozen=True)
class ParameterIdentificationUpdatedEvent(TwinEvent):
    """Published when online parameter identification produces a significantly updated or heartbeat parameter snapshot."""

    parameter_set: Optional[IdentifiedParameterSet] = None
    event_type: str = "twin.calibration"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.parameter_set is not None:
            if self.source_id == "system":
                object.__setattr__(self, "source_id", self.parameter_set.system_id)
            if self.timestamp_ns == 0:
                object.__setattr__(self, "timestamp_ns", self.parameter_set.timestamp_ns)
            if not self.payload:
                object.__setattr__(self, "payload", self.parameter_set.to_dict())
