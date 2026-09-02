"""Universal Battery State Estimator Protocols and Abstract Base Classes.

Defines standardized contracts, state vectors, inputs, outputs, and validation
for State of Charge (SOC), State of Health (SOH), and parameter estimation algorithms.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from src.estimators.exceptions import (
    EstimatorConvergenceError,
    EstimatorError,
    EstimatorInitializationError,
    InvalidEstimatorInputError,
)
from src.models.exceptions import InvalidModelStateError
from src.models.math import assert_finite, clamp
from src.models.types import ABSOLUTE_ZERO_CELSIUS


@dataclass(frozen=True)
class EstimationState:
    r"""State vector container representing estimated internal battery state.

    All physical quantities use explicit SI units:
    - soc_fraction: Estimated State of Charge in range [0.0, 1.0].
    - soh_fraction: Estimated State of Health in range [0.0, 1.0].
    - soc_variance: Estimation error variance $\sigma^2_{SOC}$ ($\ge 0.0$).
    - temperature_c: Current core temperature in Celsius (> -273.15°C).
    - internal_resistance_mohm: Estimated high-frequency DC series resistance in m$\Omega$ ($\ge 0.0$).
    - polarization_voltages_v: Estimated transient RC branch overpotentials in Volts.
    - custom_estimates: Additional algorithm-specific estimated states (e.g. hysteresis, diffusion overpotential).
    - timestamp_ns: Nanosecond timestamp corresponding to this state snapshot.
    """

    soc_fraction: float
    soh_fraction: float = 1.0
    soc_variance: float = 0.0
    temperature_c: float = 25.0
    internal_resistance_mohm: Optional[float] = None
    polarization_voltages_v: tuple[float, ...] = ()
    custom_estimates: Mapping[str, float] = field(default_factory=dict)
    timestamp_ns: Optional[int] = None

    def __post_init__(self) -> None:
        assert_finite(self.soc_fraction, "soc_fraction")
        assert_finite(self.soh_fraction, "soh_fraction")
        assert_finite(self.soc_variance, "soc_variance")
        assert_finite(self.temperature_c, "temperature_c")

        if not (0.0 <= self.soc_fraction <= 1.0):
            raise InvalidModelStateError(
                f"soc_fraction must be in range [0.0, 1.0], got {self.soc_fraction}."
            )
        if not (0.0 <= self.soh_fraction <= 1.0):
            raise InvalidModelStateError(
                f"soh_fraction must be in range [0.0, 1.0], got {self.soh_fraction}."
            )
        if self.soc_variance < 0.0:
            raise InvalidModelStateError(
                f"soc_variance must be non-negative (>= 0.0), got {self.soc_variance}."
            )
        if self.temperature_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidModelStateError(
                f"temperature_c below absolute zero: {self.temperature_c}°C."
            )

        if self.internal_resistance_mohm is not None:
            assert_finite(self.internal_resistance_mohm, "internal_resistance_mohm")
            if self.internal_resistance_mohm < 0.0:
                raise InvalidModelStateError(
                    f"internal_resistance_mohm cannot be negative, got {self.internal_resistance_mohm}."
                )

        for idx, v in enumerate(self.polarization_voltages_v):
            assert_finite(v, f"polarization_voltages_v[{idx}]")

        if self.timestamp_ns is not None:
            if not isinstance(self.timestamp_ns, int) or self.timestamp_ns < 0:
                raise InvalidModelStateError(
                    f"timestamp_ns must be a non-negative integer, got {self.timestamp_ns}."
                )

    def with_updates(self, **kwargs: Any) -> "EstimationState":
        """Creates a new EstimationState with specified updated fields."""
        current_data = {
            "soc_fraction": self.soc_fraction,
            "soh_fraction": self.soh_fraction,
            "soc_variance": self.soc_variance,
            "temperature_c": self.temperature_c,
            "internal_resistance_mohm": self.internal_resistance_mohm,
            "polarization_voltages_v": self.polarization_voltages_v,
            "custom_estimates": dict(self.custom_estimates),
            "timestamp_ns": self.timestamp_ns,
        }
        current_data.update(kwargs)
        return EstimationState(**current_data)

    def to_dict(self) -> dict[str, Any]:
        """Serializes estimation state to dictionary."""
        return {
            "soc_fraction": self.soc_fraction,
            "soh_fraction": self.soh_fraction,
            "soc_variance": self.soc_variance,
            "temperature_c": self.temperature_c,
            "internal_resistance_mohm": self.internal_resistance_mohm,
            "polarization_voltages_v": list(self.polarization_voltages_v),
            "custom_estimates": dict(self.custom_estimates),
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass(frozen=True)
class EstimationInput:
    """Input observation vector driving a state estimator step.

    All physical quantities use explicit SI units:
    - current_a: Measured load current in Amperes (> 0 discharge, < 0 charge).
    - voltage_v: Measured terminal voltage in Volts (> 0.0).
    - temperature_c: Measured cell/module temperature in Celsius (> -273.15°C).
    - dt_s: Time step interval since previous observation in seconds (> 0.0).
    - timestamp_ns: Nanosecond timestamp of this measurement.
    """

    current_a: float
    voltage_v: float
    temperature_c: float = 25.0
    dt_s: float = 1.0
    timestamp_ns: Optional[int] = None

    def __post_init__(self) -> None:
        assert_finite(self.current_a, "current_a")
        assert_finite(self.voltage_v, "voltage_v")
        assert_finite(self.temperature_c, "temperature_c")
        assert_finite(self.dt_s, "dt_s")

        if self.voltage_v <= 0.0:
            raise InvalidEstimatorInputError(
                f"voltage_v must be strictly positive, got {self.voltage_v}V."
            )
        if self.dt_s <= 0.0:
            raise InvalidEstimatorInputError(
                f"dt_s must be strictly positive (> 0.0s), got {self.dt_s}s."
            )
        if self.temperature_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidEstimatorInputError(
                f"temperature_c below absolute zero: {self.temperature_c}°C."
            )
        if self.timestamp_ns is not None:
            if not isinstance(self.timestamp_ns, int) or self.timestamp_ns < 0:
                raise InvalidEstimatorInputError(
                    f"timestamp_ns must be a non-negative integer, got {self.timestamp_ns}."
                )

    def to_dict(self) -> dict[str, Any]:
        """Serializes input observation to dictionary."""
        return {
            "current_a": self.current_a,
            "voltage_v": self.voltage_v,
            "temperature_c": self.temperature_c,
            "dt_s": self.dt_s,
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass(frozen=True)
class EstimationOutput:
    r"""Output vector produced by a state estimation step.

    Contains updated EstimationState and diagnostic residuals:
    - state: Updated EstimationState snapshot.
    - predicted_voltage_v: Model-predicted terminal voltage prior to measurement update.
    - innovation_v: Measurement residual $\tilde{y} = V_{meas} - \hat{V}_{pred}$.
    - innovation_variance_v2: Residual covariance $S = C P C^T + R$.
    - derivatives: Estimated instantaneous state derivatives ($dSOC/dt$, $dT/dt$).
    - diagnostics: Algorithm-specific convergence and health indicators.
    """

    state: EstimationState
    predicted_voltage_v: Optional[float] = None
    innovation_v: Optional[float] = None
    innovation_variance_v2: Optional[float] = None
    derivatives: Mapping[str, float] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.predicted_voltage_v is not None:
            assert_finite(self.predicted_voltage_v, "predicted_voltage_v")
        if self.innovation_v is not None:
            assert_finite(self.innovation_v, "innovation_v")
        if self.innovation_variance_v2 is not None:
            assert_finite(self.innovation_variance_v2, "innovation_variance_v2")
            if self.innovation_variance_v2 < 0.0:
                raise EstimatorConvergenceError("innovation_variance_v2 cannot be negative.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes estimation output to dictionary."""
        return {
            "state": self.state.to_dict(),
            "predicted_voltage_v": self.predicted_voltage_v,
            "innovation_v": self.innovation_v,
            "innovation_variance_v2": self.innovation_variance_v2,
            "derivatives": dict(self.derivatives),
            "diagnostics": dict(self.diagnostics),
        }


@runtime_checkable
class StateEstimator(Protocol):
    """Universal Protocol governing all battery state estimators in TwinVolt."""

    @property
    def estimator_id(self) -> str:
        """Unique identifier of this estimator instance."""
        ...

    @property
    def state(self) -> EstimationState:
        """Current estimated state snapshot."""
        ...

    def initialize(
        self,
        initial_soc: float = 1.0,
        initial_soh: float = 1.0,
        temperature_c: float = 25.0,
        **kwargs: Any,
    ) -> EstimationState:
        """Initializes internal states and covariance matrices."""
        ...

    def step(self, estimation_input: EstimationInput) -> EstimationOutput:
        """Executes one estimation cycle for the given measurement observation."""
        ...

    def reset(self, initial_state: Optional[EstimationState] = None) -> None:
        """Resets estimator state to initial or provided state vector."""
        ...


class AbstractStateEstimator(ABC):
    """Abstract Base Class providing common lifecycle management and validation for StateEstimators."""

    def __init__(
        self,
        estimator_id: str,
        initial_state: Optional[EstimationState] = None,
    ) -> None:
        if not estimator_id.strip():
            raise EstimatorInitializationError("estimator_id cannot be empty.")
        self._estimator_id = estimator_id

        if initial_state is not None:
            self._state = initial_state
        else:
            self._state = self._create_initial_state(
                initial_soc=1.0,
                initial_soh=1.0,
                temperature_c=25.0,
            )

    @property
    def estimator_id(self) -> str:
        """Unique identifier for this estimator."""
        return self._estimator_id

    @property
    def state(self) -> EstimationState:
        """Current estimated state vector."""
        return self._state

    def initialize(
        self,
        initial_soc: float = 1.0,
        initial_soh: float = 1.0,
        temperature_c: float = 25.0,
        **kwargs: Any,
    ) -> EstimationState:
        """Initializes internal state vector and covariance."""
        try:
            new_state = self._create_initial_state(
                initial_soc=initial_soc,
                initial_soh=initial_soh,
                temperature_c=temperature_c,
                **kwargs,
            )
            self._state = new_state
            return self._state
        except Exception as exc:
            if isinstance(exc, (EstimatorError, InvalidModelStateError)):
                raise
            raise EstimatorInitializationError(
                f"Estimator '{self._estimator_id}' initialization failed: {exc}",
                estimator_id=self._estimator_id,
            ) from exc

    def step(self, estimation_input: EstimationInput) -> EstimationOutput:
        """Executes a discrete estimation cycle with invariant and numerical checks."""
        try:
            output = self._compute_step(estimation_input, self._state)
            self._state = output.state
            return output
        except Exception as exc:
            if isinstance(exc, (EstimatorError, InvalidEstimatorInputError, EstimatorConvergenceError)):
                raise
            raise EstimatorConvergenceError(
                f"Estimator '{self._estimator_id}' step failed: {exc}",
                estimator_id=self._estimator_id,
            ) from exc

    def reset(self, initial_state: Optional[EstimationState] = None) -> None:
        """Resets the estimator state."""
        if initial_state is not None:
            self._state = initial_state
        else:
            self._state = self._create_initial_state(initial_soc=1.0, initial_soh=1.0, temperature_c=25.0)

    @abstractmethod
    def _create_initial_state(
        self,
        initial_soc: float,
        initial_soh: float,
        temperature_c: float,
        **kwargs: Any,
    ) -> EstimationState:
        """Creates estimator-specific initial state."""
        ...

    @abstractmethod
    def _compute_step(
        self,
        estimation_input: EstimationInput,
        current_state: EstimationState,
    ) -> EstimationOutput:
        """Executes algorithm-specific state propagation and measurement update."""
        ...
