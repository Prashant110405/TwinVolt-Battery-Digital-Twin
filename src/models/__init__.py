"""TwinVolt Mathematical Core and Battery Modeling Package.

Exports universal state vectors, mathematical protocols, ODE integrators,
and domain exception classes for battery simulation.
"""

from src.models.base import (
    AbstractBatteryModel,
    BatteryModel,
    OCVModel,
    ThermalModel,
)
from src.models.exceptions import (
    InvalidModelInputError,
    InvalidModelParametersError,
    InvalidModelStateError,
    ModelError,
    ModelEvaluationError,
    ModelInitializationError,
    NumericalInstabilityError,
    UnphysicalStateError,
)
from src.models.math import (
    ExplicitEulerIntegrator,
    NumericalIntegrator,
    RungeKutta4Integrator,
    assert_finite,
    calculate_coulomb_soc_step,
    clamp,
    is_finite_number,
    solve_rc_branch_voltage_step,
)
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import (
    GenericECMParameters,
    RCBranchParameters,
)
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.physics.base import PhysicsModelBackend
from src.models.physics.parameters import PhysicsModelParameters
from src.models.physics.pybamm_adapter import (
    PyBaMMModelAdapter,
    PyBaMMNativeBackend,
    SimulatedPhysicsBackend,
)
from src.models.thermal.lumped import LumpedThermalModel
from src.models.types import (
    ModelInput,
    ModelMetadata,
    ModelOutput,
    ModelParameters,
    ModelState,
)

__all__ = [
    # Protocols & Base Classes
    "BatteryModel",
    "AbstractBatteryModel",
    "OCVModel",
    "ThermalModel",
    "PhysicsModelBackend",
    # Concrete Models & Components
    "GenericECMModel",
    "GenericECMParameters",
    "RCBranchParameters",
    "PyBaMMModelAdapter",
    "PhysicsModelParameters",
    "PyBaMMNativeBackend",
    "SimulatedPhysicsBackend",
    "LumpedThermalModel",
    "LinearOCVModel",
    # Types & State Space
    "ModelState",
    "ModelInput",
    "ModelOutput",
    "ModelParameters",
    "ModelMetadata",
    # Math & Numerical Integrators
    "is_finite_number",
    "assert_finite",
    "clamp",
    "calculate_coulomb_soc_step",
    "NumericalIntegrator",
    "ExplicitEulerIntegrator",
    "RungeKutta4Integrator",
    "solve_rc_branch_voltage_step",
    # Exceptions
    "ModelError",
    "InvalidModelParametersError",
    "InvalidModelStateError",
    "InvalidModelInputError",
    "ModelInitializationError",
    "ModelEvaluationError",
    "NumericalInstabilityError",
    "UnphysicalStateError",
]
