"""State Estimation Exceptions Hierarchy.

Defines domain-specific exceptions for battery state estimation, Kalman filters,
Coulomb counting, covariance divergence, and parameter tracking errors.
"""

from typing import Any, Mapping, Optional

from src.domain.exceptions import TwinVoltDomainError


class EstimatorError(TwinVoltDomainError):
    """Base exception for all battery state estimation errors."""

    def __init__(
        self,
        message: str,
        details: Optional[Mapping[str, Any]] = None,
        estimator_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, dict(details) if details else None)
        self.estimator_id = estimator_id


class EstimatorInitializationError(EstimatorError):
    """Raised when an estimator fails to initialize its state vector or covariance matrix."""


class EstimatorConvergenceError(EstimatorError):
    """Raised when an estimation filter diverges, produces non-positive-definite covariance, or fails numerical checks."""


class InvalidEstimatorInputError(EstimatorError):
    """Raised when an estimation measurement input (current, voltage, temp, dt) is non-finite or out of physical bounds."""
