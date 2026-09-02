"""Universal Physics-Based Electrochemical Model Adapter.

Provides a typed, model-agnostic bridge between arbitrary PDE/electrochemical
solvers and the universal TwinVolt BatteryModel protocol.
"""

import math
from typing import Any, Mapping, Optional, Sequence, Union

from src.models.base import AbstractBatteryModel, ThermalModel
from src.models.exceptions import (
    InvalidModelInputError,
    InvalidModelParametersError,
    InvalidModelStateError,
    ModelEvaluationError,
    ModelInitializationError,
    NumericalInstabilityError,
    UnphysicalStateError,
)
from src.models.math import assert_finite, calculate_coulomb_soc_step, clamp
from src.models.physics.base import AbstractPhysicsBackend, PhysicsModelBackend, PhysicsStepResult
from src.models.physics.parameters import PhysicsModelParameters
from src.models.thermal.lumped import LumpedThermalModel
from src.models.types import (
    ABSOLUTE_ZERO_CELSIUS,
    ModelInput,
    ModelMetadata,
    ModelOutput,
    ModelState,
)


class PhysicsModelAdapter(AbstractBatteryModel):
    """Model-agnostic adapter integrating physics-based solvers into TwinVolt.

    Conforms to the universal BatteryModel protocol, supporting:
    - Electrochemical model execution across SPM, SPMe, DFN, and MSMR paradigms.
    - Full state/input/output separation ($x[k], u[k], y[k]$).
    - Optional electro-thermal coupling (internal solver or 0D lumped thermal model).
    - Microscopic state observation (surface concentrations, reaction overpotentials).
    - Rigorous mathematical and physical invariant defense.
    """

    def __init__(
        self,
        metadata: ModelMetadata,
        parameters: PhysicsModelParameters,
        backend: PhysicsModelBackend,
        thermal_model: Optional[ThermalModel] = None,
        initial_state: Optional[ModelState] = None,
    ) -> None:
        if not isinstance(parameters, PhysicsModelParameters):
            raise InvalidModelParametersError(
                f"parameters must be PhysicsModelParameters, got {type(parameters).__name__}."
            )
        self._physics_params = parameters

        if not isinstance(backend, (PhysicsModelBackend, AbstractPhysicsBackend)):
            raise InvalidModelParametersError(
                f"backend must implement PhysicsModelBackend, got {type(backend).__name__}."
            )
        self._backend = backend

        if thermal_model is not None:
            self._thermal_model = thermal_model
        else:
            self._thermal_model = LumpedThermalModel(
                thermal_capacitance_j_per_k=self._physics_params.thermal_mass_j_per_k,
                convective_heat_transfer_w_per_k=self._physics_params.convective_heat_transfer_w_per_k,
            )

        super().__init__(metadata, parameters, initial_state)

    @property
    def physics_parameters(self) -> PhysicsModelParameters:
        """Typed physics model parameters container."""
        return self._physics_params

    @property
    def backend(self) -> PhysicsModelBackend:
        """Active electrochemical solver backend."""
        return self._backend

    @property
    def thermal_model(self) -> ThermalModel:
        """Configured 0D thermal dynamics model."""
        return self._thermal_model

    def _create_initial_state(
        self,
        soc_init: float,
        temperature_c: float,
        **kwargs: Any,
    ) -> ModelState:
        """Initializes internal physics state and backend solver."""
        if not (0.0 <= soc_init <= 1.0):
            raise InvalidModelStateError(f"soc_init must be in [0.0, 1.0], got {soc_init}.")
        if temperature_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidModelStateError(f"temperature_c below absolute zero: {temperature_c}°C.")

        self._backend.initialize_solver(
            parameters=self._physics_params,
            initial_soc=soc_init,
            initial_temp_c=temperature_c,
            **kwargs,
        )
        return ModelState(
            soc_fraction=soc_init,
            temperature_c=temperature_c,
            polarization_voltages_v=(0.0,),
            timestamp_ns=kwargs.get("timestamp_ns"),
        )

    def _compute_step(
        self,
        model_input: ModelInput,
        current_state: ModelState,
    ) -> ModelOutput:
        """Advances physics model across discrete time step dt_s."""
        dt = model_input.dt_s
        i_load = model_input.current_a
        t_amb = model_input.ambient_temperature_c
        t_core = current_state.temperature_c

        try:
            raw_result = self._backend.step_simulation(
                current_a=i_load,
                dt_s=dt,
                ambient_temp_c=t_amb,
                current_state=current_state,
            )
        except Exception as exc:
            if isinstance(exc, (InvalidModelInputError, InvalidModelStateError, NumericalInstabilityError, UnphysicalStateError)):
                raise
            raise ModelEvaluationError(
                f"Physics solver '{self._backend.backend_name}' step failed: {exc}",
                model_id=self._metadata.model_id,
            ) from exc

        # Extract outputs from PhysicsStepResult or sequence
        if isinstance(raw_result, PhysicsStepResult):
            v_term = raw_result.terminal_voltage_v
            v_oc = raw_result.open_circuit_voltage_v
            soc_next = raw_result.soc_fraction
            temp_next = raw_result.temperature_c
            custom_states = dict(raw_result.custom_states)
            q_gen_backend = raw_result.heat_generation_w
            r_int_mohm = raw_result.internal_resistance_mohm or 25.0
            custom_derivs = dict(raw_result.derivatives)
        else:
            v_term, v_oc, soc_next, temp_next, custom_states = raw_result
            custom_states = dict(custom_states)
            q_gen_backend = None
            r_int_mohm = 25.0
            custom_derivs = {}

        # 1. Assert Numerical Finiteness
        assert_finite(v_term, "terminal_voltage_v")
        assert_finite(v_oc, "open_circuit_voltage_v")
        assert_finite(soc_next, "soc_fraction")
        assert_finite(temp_next, "temperature_c")

        # 2. Assert Physical Invariant Bounds
        if not (0.0 <= soc_next <= 1.0):
            raise UnphysicalStateError(
                f"Solver produced unphysical SOC fraction {soc_next} (must be in [0.0, 1.0]).",
                details={"soc_fraction": soc_next, "model_id": self._metadata.model_id},
            )
        if temp_next <= ABSOLUTE_ZERO_CELSIUS:
            raise UnphysicalStateError(
                f"Solver produced unphysical temperature {temp_next}°C (below absolute zero).",
                details={"temperature_c": temp_next, "model_id": self._metadata.model_id},
            )

        # 3. Electro-Thermal Heat Generation & Thermal Evolution
        if q_gen_backend is not None:
            assert_finite(q_gen_backend, "heat_generation_w")
            q_gen_total = max(0.0, q_gen_backend)
        else:
            # Overpotential and resistive dissipation: Q_loss = I * (V_oc - V_term)
            overpotential_loss = abs(i_load * (v_oc - v_term))
            q_gen_total = max(0.0, overpotential_loss)

        # If backend is isothermal, advance thermal state via external LumpedThermalModel
        if self._physics_params.thermal_coupling == "ISOTHERMAL":
            temp_next = current_state.temperature_c
        elif math.isclose(temp_next, current_state.temperature_c, abs_tol=1e-9) and abs(i_load) > 1e-6:
            # Backend did not evolve temperature; evolve via thermal model
            temp_next = self._thermal_model.step(
                heat_generation_w=q_gen_total,
                dt_s=dt,
                ambient_temperature_c=t_amb,
                current_temp_c=t_core,
            )

        # 4. Construct Next ModelState x[k+1]
        next_state = current_state.with_updates(
            soc_fraction=soc_next,
            temperature_c=temp_next,
            custom_states=custom_states,
            timestamp_ns=model_input.timestamp_ns,
        )

        # 5. Derivatives
        derivatives = {
            "d_soc_dt": (soc_next - current_state.soc_fraction) / dt if dt > 0 else 0.0,
            "d_temp_dt": (temp_next - current_state.temperature_c) / dt if dt > 0 else 0.0,
        }
        derivatives.update(custom_derivs)

        return ModelOutput(
            terminal_voltage_v=v_term,
            open_circuit_voltage_v=v_oc,
            state=next_state,
            heat_generation_w=q_gen_total,
            internal_resistance_mohm=r_int_mohm,
            derivatives=derivatives,
        )

    def reset(self, initial_state: Optional[ModelState] = None) -> None:
        """Resets both adapter state vector and underlying physics solver."""
        self._backend.reset()
        super().reset(initial_state)

    # --------------------------------------------------------------------------
    # Model Factory Helpers
    # --------------------------------------------------------------------------
    @classmethod
    def create_physics_model(
        cls,
        model_id: str,
        backend: PhysicsModelBackend,
        model_type: str = "SPM",
        nominal_capacity_ah: float = 2.2,
        nominal_voltage_v: float = 3.7,
        parameter_set_name: str = "Chen2020",
        thermal_coupling: str = "LUMPED",
        thermal_model: Optional[ThermalModel] = None,
        **kwargs: Any,
    ) -> "PhysicsModelAdapter":
        """Factory creating a model-agnostic PhysicsModelAdapter."""
        metadata = ModelMetadata(
            model_id=model_id,
            name=f"Physics {model_type.upper()} ({model_id})",
            paradigm=f"PHYSICS_{model_type.upper()}",
        )
        params = PhysicsModelParameters(
            nominal_capacity_ah=nominal_capacity_ah,
            nominal_voltage_v=nominal_voltage_v,
            model_type=model_type,
            parameter_set_name=parameter_set_name,
            thermal_coupling=thermal_coupling,
            **kwargs,
        )
        return cls(
            metadata=metadata,
            parameters=params,
            backend=backend,
            thermal_model=thermal_model,
        )
