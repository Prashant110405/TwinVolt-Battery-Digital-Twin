"""Battery Health, SOH Estimation, and Degradation Analytics Package."""

from src.analytics.degradation import (
    ArrheniusSEIEmpiricalDegradationModel,
    DegradationModel,
    DegradationParameters,
)
from src.analytics.events import BatteryHealthUpdatedEvent
from src.analytics.soh import StateOfHealthEstimator, ThroughputHealthEstimator
from src.analytics.stress import StressAccumulator
from src.analytics.types import (
    BatteryHealthState,
    CalibrationStatus,
    DegradationMetrics,
    StressAccumulatorState,
)

__all__ = [
    # Data Models & Enums
    "CalibrationStatus",
    "StressAccumulatorState",
    "DegradationMetrics",
    "BatteryHealthState",
    # Stress Accumulation
    "StressAccumulator",
    # Degradation Models
    "DegradationParameters",
    "DegradationModel",
    "ArrheniusSEIEmpiricalDegradationModel",
    # SOH Estimators
    "StateOfHealthEstimator",
    "ThroughputHealthEstimator",
    # Events
    "BatteryHealthUpdatedEvent",
]
