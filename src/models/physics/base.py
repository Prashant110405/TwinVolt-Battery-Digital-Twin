"""Physics-Based Electrochemical Model Backend Protocol and Abstractions.

Defines the universal backend contract for integrating high-fidelity electrochemical
and PDE-based battery solvers (e.g., PyBaMM SPM, SPMe, DFN) into TwinVolt.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Optional, Protocol, Union, runtime_checkable

from src.models.types import ModelParameters, ModelState


@dataclass(frozen=True)
class PhysicsStepResult:
    """Structured step result container produced by a physics simulation backend.

    Supports direct attribute access as well as 5-tuple sequence unpacking for
    complete backward compatibility:
        v_term, v_oc, soc_next, temp_next, custom_states = result
    """

    terminal_voltage_v: float
    open_circuit_voltage_v: float
    soc_fraction: float
    temperature_c: float
    custom_states: Mapping[str, float] = field(default_factory=dict)
    heat_generation_w: Optional[float] = None
    internal_resistance_mohm: Optional[float] = None
    derivatives: Mapping[str, float] = field(default_factory=dict)

    def __iter__(self) -> Iterator[Any]:
        return iter((
            self.terminal_voltage_v,
            self.open_circuit_voltage_v,
            self.soc_fraction,
            self.temperature_c,
            self.custom_states,
        ))

    def __getitem__(self, index: int) -> Any:
        return (
            self.terminal_voltage_v,
            self.open_circuit_voltage_v,
            self.soc_fraction,
            self.temperature_c,
            self.custom_states,
        )[index]

    def __len__(self) -> int:
        return 5


@runtime_checkable
class PhysicsModelBackend(Protocol):
    """Protocol governing electrochemical physics-based simulation backends."""

    @property
    def backend_name(self) -> str:
        """Name of the underlying physics engine (e.g., 'PyBaMM-DFN', 'PyBaMM-SPMe')."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether the physics solver and its dependencies are available in the runtime."""
        ...

    def initialize_solver(
        self,
        parameters: ModelParameters,
        initial_soc: float,
        initial_temp_c: float,
        **kwargs: Any,
    ) -> None:
        """Initializes and meshes the PDE solver with boundary conditions."""
        ...

    def step_simulation(
        self,
        current_a: float,
        dt_s: float,
        ambient_temp_c: float,
        current_state: ModelState,
    ) -> Union[PhysicsStepResult, tuple[float, float, float, float, Mapping[str, float]]]:
        """Executes a discrete time step $\\Delta t$.

        Returns:
            PhysicsStepResult or 5-tuple of:
            - terminal_voltage_v: float
            - open_circuit_voltage_v: float
            - next_soc_fraction: float
            - next_temperature_c: float
            - custom_internal_states: Mapping[str, float] (e.g. concentration gradients, overpotentials)
        """
        ...

    def reset(self) -> None:
        """Resets solver state vectors and spatial mesh."""
        ...


class AbstractPhysicsBackend(ABC):
    """Abstract Base Class for physics solver backends.

    Provides common lifecycle management and state tracking for electrochemical solvers.
    """

    def __init__(self, backend_name: str) -> None:
        self._backend_name = backend_name
        self._is_initialized = False

    @property
    def backend_name(self) -> str:
        """Identifier name of the physics backend engine."""
        return self._backend_name

    @property
    def is_available(self) -> bool:
        """Whether this backend is usable in the current environment."""
        return True

    @property
    def is_initialized(self) -> bool:
        """Whether the solver has been initialized."""
        return self._is_initialized

    @abstractmethod
    def initialize_solver(
        self,
        parameters: ModelParameters,
        initial_soc: float,
        initial_temp_c: float,
        **kwargs: Any,
    ) -> None:
        """Initializes solver boundary conditions, parameter sets, and spatial meshes."""
        ...

    @abstractmethod
    def step_simulation(
        self,
        current_a: float,
        dt_s: float,
        ambient_temp_c: float,
        current_state: ModelState,
    ) -> Union[PhysicsStepResult, tuple[float, float, float, float, Mapping[str, float]]]:
        """Executes a discrete time step across dt_s."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Resets solver state vectors and simulation clock."""
        ...

