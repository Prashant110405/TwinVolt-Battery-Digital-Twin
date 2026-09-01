"""Mathematical Core and Battery Modeling Exceptions Hierarchy.

Defines domain-specific exceptions for mathematical modeling, state variables,
parameter boundaries, ODE numerical evaluation, and physical invariant violations.
"""

from typing import Any, Mapping, Optional

from src.domain.exceptions import TwinVoltDomainError


class ModelError(TwinVoltDomainError):
    """Base exception for all battery mathematical modeling and simulation errors."""

    def __init__(
        self,
        message: str,
        details: Optional[Mapping[str, Any]] = None,
        model_id: Optional[str] = None,
    ) -> None:
        super().__init__(message, dict(details) if details else None)
        self.model_id = model_id


class InvalidModelParametersError(ModelError):
    """Raised when model physical parameters violate physical or domain boundaries."""


class InvalidModelStateError(ModelError):
    """Raised when a state variable vector is unphysical, malformed, or out of bounds."""


class InvalidModelInputError(ModelError):
    """Raised when an input vector (current, dt, ambient temp) is invalid or unphysical."""


class ModelInitializationError(ModelError):
    """Raised when a mathematical model fails to initialize its internal state."""


class ModelEvaluationError(ModelError):
    """Raised when an error occurs during model state propagation or output evaluation."""


class NumericalInstabilityError(ModelError):
    """Raised when an ODE solver or numerical step diverges or produces NaN/Inf."""


class UnphysicalStateError(ModelError):
    """Raised when a model calculation results in a physically impossible condition."""
