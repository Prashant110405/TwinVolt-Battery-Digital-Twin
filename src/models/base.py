"""Core Battery Mathematical Model Interfaces and Base Abstractions.

Defines the universal BatteryModel Protocol and AbstractBaseModel class
governing all simulation models (ECM, Physics, Empirical) in TwinVolt.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Protocol, runtime_checkable

from src.models.exceptions import (
    InvalidModelInputError,
    ModelEvaluationError,
    ModelInitializationError,
)
from src.models.types import (
    ModelInput,
    ModelMetadata,
    ModelOutput,
    ModelParameters,
    ModelState,
)


@runtime_checkable
class OCVModel(Protocol):
    """Protocol for Open-Circuit Voltage models: $V_{oc} = f(SOC, T)$."""

    def get_ocv(self, soc_fraction: float, temperature_c: float = 25.0) -> float:
        """Returns open-circuit voltage in Volts for given SOC and temperature."""
        ...

    def get_docv_dsoc(self, soc_fraction: float, temperature_c: float = 25.0) -> float:
        """Returns derivative $dOCV/dSOC$ in V/fraction."""
        ...

    def get_docv_dtemp(self, soc_fraction: float, temperature_c: float = 25.0) -> float:
        """Returns entropic thermal derivative $dOCV/dT$ in V/K."""
        ...


@runtime_checkable
class ThermalModel(Protocol):
    """Protocol for thermal state evolution models: $T_{k+1} = f(T_k, Q_{gen}, T_{amb}, dt)$."""

    def step(
        self,
        heat_generation_w: float,
        dt_s: float,
        ambient_temperature_c: float,
        current_temp_c: float,
    ) -> float:
        """Calculates updated temperature in Celsius after time step dt_s."""
        ...


@runtime_checkable
class BatteryModel(Protocol):
    """Universal Protocol governing all mathematical battery simulation models in TwinVolt."""

    @property
    def metadata(self) -> ModelMetadata:
        """Descriptive model metadata, paradigm, and version."""
        ...

    @property
    def state(self) -> ModelState:
        """Current internal state vector $x[k]$."""
        ...

    @property
    def parameters(self) -> ModelParameters:
        """Configured physical parameter set."""
        ...

    def initialize(
        self,
        soc_init: float = 1.0,
        temperature_c: float = 25.0,
        **kwargs: Any,
    ) -> ModelState:
        """Initializes the internal state vector."""
        ...

    def step(
        self,
        model_input: ModelInput,
        state: Optional[ModelState] = None,
    ) -> ModelOutput:
        """Executes a discrete time step: $x[k+1], y[k] = f(x[k], u[k], \\Delta t)$."""
        ...

    def reset(self, initial_state: Optional[ModelState] = None) -> None:
        """Resets model state to default or provided state vector."""
        ...


class AbstractBatteryModel(ABC):
    """Abstract Base Class providing common lifecycle and validation logic for BatteryModel implementations."""

    def __init__(
        self,
        metadata: ModelMetadata,
        parameters: ModelParameters,
        initial_state: Optional[ModelState] = None,
    ) -> None:
        self._metadata = metadata
        self._parameters = parameters
        if initial_state is not None:
            self._state = initial_state
        else:
            self._state = self._create_initial_state(
                soc_init=1.0,
                temperature_c=25.0,
            )

    @property
    def metadata(self) -> ModelMetadata:
        """Descriptive model metadata."""
        return self._metadata

    @property
    def state(self) -> ModelState:
        """Current internal state vector."""
        return self._state

    @property
    def parameters(self) -> ModelParameters:
        """Configured physical parameter set."""
        return self._parameters

    def initialize(
        self,
        soc_init: float = 1.0,
        temperature_c: float = 25.0,
        **kwargs: Any,
    ) -> ModelState:
        """Initializes and records the internal state vector."""
        try:
            new_state = self._create_initial_state(soc_init, temperature_c, **kwargs)
            self._state = new_state
            return self._state
        except Exception as exc:
            raise ModelInitializationError(
                f"Failed to initialize model '{self._metadata.model_id}': {exc}",
                model_id=self._metadata.model_id,
            ) from exc

    def step(
        self,
        model_input: ModelInput,
        state: Optional[ModelState] = None,
    ) -> ModelOutput:
        """Validates inputs and executes a discrete simulation step."""
        current_state = state if state is not None else self._state

        try:
            output = self._compute_step(model_input, current_state)
            if state is None:
                self._state = output.state
            return output
        except Exception as exc:
            if isinstance(exc, (InvalidModelInputError, ModelEvaluationError)):
                raise
            raise ModelEvaluationError(
                f"Model '{self._metadata.model_id}' evaluation failed: {exc}",
                model_id=self._metadata.model_id,
            ) from exc

    def reset(self, initial_state: Optional[ModelState] = None) -> None:
        """Resets the model state."""
        if initial_state is not None:
            self._state = initial_state
        else:
            self._state = self._create_initial_state(soc_init=1.0, temperature_c=25.0)

    @abstractmethod
    def _create_initial_state(
        self,
        soc_init: float,
        temperature_c: float,
        **kwargs: Any,
    ) -> ModelState:
        """Creates model-specific initial state vector."""
        ...

    @abstractmethod
    def _compute_step(
        self,
        model_input: ModelInput,
        current_state: ModelState,
    ) -> ModelOutput:
        """Computes next state and outputs for given input and current state."""
        ...
