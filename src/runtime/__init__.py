"""TwinVolt Digital Twin Runtime & Real-Time Synchronization Engine.

Provides the execution core orchestrating physical battery domain entities, simulation models,
state estimators, telemetry ingestion, anomaly detection, and time-series persistence.
"""

from src.runtime.anomaly_detector import (
    AnomalyReport,
    DetectedAnomaly,
    PhysicsAnomalyDetector,
)
from src.runtime.config import (
    AnomalyThresholds,
    ResidualTolerances,
    RuntimeConfig,
)
from src.runtime.exceptions import (
    AnomalyDetectionError,
    ClockSkewError,
    InvalidRuntimeStateError,
    RuntimeCoreError,
    RuntimeExecutionError,
    RuntimeInitializationError,
    StaleTelemetryError,
    SynchronizationError,
)
from src.runtime.instance import DigitalTwinInstance
from src.runtime.synchronizer import (
    TwinSyncOutput,
    TwinSynchronizer,
)

__all__ = [
    # Core Runtime Classes
    "DigitalTwinInstance",
    "TwinSynchronizer",
    "TwinSyncOutput",
    "PhysicsAnomalyDetector",
    "AnomalyReport",
    "DetectedAnomaly",
    # Configuration
    "RuntimeConfig",
    "ResidualTolerances",
    "AnomalyThresholds",
    # Exceptions
    "RuntimeCoreError",
    "RuntimeInitializationError",
    "RuntimeExecutionError",
    "SynchronizationError",
    "StaleTelemetryError",
    "ClockSkewError",
    "InvalidRuntimeStateError",
    "AnomalyDetectionError",
]
