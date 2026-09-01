"""Physics-Based Electrochemical Model Backend Protocol and Abstractions.

Defines the universal backend contract for integrating high-fidelity electrochemical
and PDE-based battery solvers (e.g., PyBaMM SPM, SPMe, DFN) into TwinVolt.
"""

from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from src.models.types import ModelInput, ModelMetadata, ModelParameters, ModelState


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
    ) -> tuple[float, float, float, float, Mapping[str, float]]:
        """Executes a discrete time step $\\Delta t$.

        Returns:
            Tuple of:
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
