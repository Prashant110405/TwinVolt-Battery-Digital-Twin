"""Physics Modeling and Electrochemical Solver Package.

Re-exports core physics interfaces and adapters from `src.models.physics`
for top-level package accessibility.
"""

from src.models.physics.base import (
    AbstractPhysicsBackend,
    PhysicsModelBackend,
    PhysicsStepResult,
)
from src.models.physics.parameters import (
    SUPPORTED_PHYSICS_MODELS,
    SUPPORTED_THERMAL_COUPLINGS,
    PhysicsModelParameters,
)
from src.models.physics.physics_adapter import PhysicsModelAdapter
from src.models.physics.pybamm_adapter import (
    PyBaMMModelAdapter,
    PyBaMMNativeBackend,
    SimulatedPhysicsBackend,
)

__all__ = [
    "PhysicsModelBackend",
    "AbstractPhysicsBackend",
    "PhysicsStepResult",
    "PhysicsModelParameters",
    "SUPPORTED_PHYSICS_MODELS",
    "SUPPORTED_THERMAL_COUPLINGS",
    "PhysicsModelAdapter",
    "PyBaMMModelAdapter",
    "PyBaMMNativeBackend",
    "SimulatedPhysicsBackend",
]
