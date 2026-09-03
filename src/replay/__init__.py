"""TwinVolt Drive Cycle Replay and Tracking Evaluation Subsystem.

Provides deterministic time-series replay engines, benchmark automotive/grid driving schedules
(WLTP Class 3, US06, DST, Pulse, CC), and analytical tracking error evaluators (RMSE, MAE, R^2).
"""

from src.replay.engine import (
    DriveCycleReplayEngine,
    ReplayConfig,
    ReplayResult,
)
from src.replay.evaluator import (
    SignalTrackingMetrics,
    TrackingMetricsEvaluator,
    TrackingMetricsReport,
)
from src.replay.exceptions import (
    EvaluationError,
    InvalidProfileError,
    ReplayError,
    ReplayExecutionError,
)
from src.replay.profiles import (
    DriveCycleProfile,
    ProfilePoint,
    create_constant_current_profile,
    create_dst_profile,
    create_pulse_discharge_profile,
    create_us06_profile,
    create_wltp_class3_profile,
)

__all__ = [
    # Replay Engine & Result
    "DriveCycleReplayEngine",
    "ReplayConfig",
    "ReplayResult",
    # Evaluators & Metrics
    "TrackingMetricsEvaluator",
    "SignalTrackingMetrics",
    "TrackingMetricsReport",
    # Profiles & Generators
    "DriveCycleProfile",
    "ProfilePoint",
    "create_constant_current_profile",
    "create_pulse_discharge_profile",
    "create_wltp_class3_profile",
    "create_us06_profile",
    "create_dst_profile",
    # Exceptions
    "ReplayError",
    "InvalidProfileError",
    "EvaluationError",
    "ReplayExecutionError",
]
