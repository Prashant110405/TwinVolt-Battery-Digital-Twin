"""Battery State Estimation Engine Package.

Provides algorithms for State of Charge (SOC), State of Health (SOH),
internal resistance tracking, and Kalman filtering.
"""

from src.estimators.base import (
    AbstractStateEstimator,
    EstimationInput,
    EstimationOutput,
    EstimationState,
    StateEstimator,
)
from src.estimators.coulomb_counter import CoulombCounter
from src.estimators.ekf import ExtendedKalmanFilter
from src.estimators.exceptions import (
    EstimatorConvergenceError,
    EstimatorError,
    EstimatorInitializationError,
    InvalidEstimatorInputError,
)
from src.estimators.soh import SOHEstimator

__all__ = [
    # Protocols & Base Classes
    "StateEstimator",
    "AbstractStateEstimator",
    "EstimationState",
    "EstimationInput",
    "EstimationOutput",
    # Concrete Estimators
    "CoulombCounter",
    "ExtendedKalmanFilter",
    "SOHEstimator",
    # Exceptions
    "EstimatorError",
    "EstimatorInitializationError",
    "EstimatorConvergenceError",
    "InvalidEstimatorInputError",
]
