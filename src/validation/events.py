"""Domain events for Battery Behavioral Validation and Model Residual Tracking."""

from dataclasses import dataclass
from typing import Optional

from src.events.base import TwinEvent
from src.validation.types import ModelValidationReport


@dataclass(frozen=True)
class BatteryValidationUpdatedEvent(TwinEvent):
    """Published when behavioral validation completes a window or experiences a state transition."""

    validation_report: Optional[ModelValidationReport] = None
    event_type: str = "twin.validation"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.validation_report is not None:
            if self.source_id == "system":
                object.__setattr__(self, "source_id", self.validation_report.system_id)
            if self.timestamp_ns == 0:
                object.__setattr__(self, "timestamp_ns", self.validation_report.timestamp_ns)
            if not self.payload:
                object.__setattr__(self, "payload", self.validation_report.to_dict())
