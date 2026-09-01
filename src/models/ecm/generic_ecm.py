"""Generic N-RC Equivalent Circuit Electro-Thermal Battery Model.

Implements discrete-time state-space electro-thermal dynamics supporting:
- 0-RC ($R_{int}$ Internal Resistance Model)
- 1-RC (Thevenin Model)
- 2-RC (Dual Polarization Model)
- Arbitrary N-RC Polarization Topologies
"""

from typing import Any, Optional, Sequence

from src.models.base import AbstractBatteryModel, OCVModel, ThermalModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.exceptions import InvalidModelParametersError, InvalidModelStateError
from src.models.math import (
    assert_finite,
    calculate_coulomb_soc_step,
    clamp,
    solve_rc_branch_voltage_step,
)
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.thermal.lumped import LumpedThermalModel
from src.models.types import (
    ModelInput,
    ModelMetadata,
    ModelOutput,
    ModelState,
)


class GenericECMModel(AbstractBatteryModel):
    """Universal Electro-Thermal Equivalent Circuit Model (ECM).

    Equations:
    - Electrical Terminal Voltage:
        V_term = V_oc(SOC, T) - I * R_0 - sum(V_rc,i) - V_hysteresis
    - Polarization Branch Evolution:
        V_rc,i[k+1] = V_rc,i[k] * exp(-dt / tau_i) + I * R_i * (1 - exp(-dt / tau_i))
    - State of Charge Evolution:
        SOC[k+1] = SOC[k] - (I * dt * eta) / (Q_nom * 3600)
    - Heat Generation Rate:
        Q_gen = I^2 * R_0 + sum(V_rc,i^2 / R_i) + I * T_kelvin * (dOCV/dT)
    - Thermal Evolution (Lumped 0D):
        C_th * dT/dt = Q_gen - hA * (T - T_amb)
    """

    def __init__(
        self,
        metadata: ModelMetadata,
        parameters: GenericECMParameters,
        ocv_model: Optional[OCVModel] = None,
        thermal_model: Optional[ThermalModel] = None,
        initial_state: Optional[ModelState] = None,
    ) -> None:
        if not isinstance(parameters, GenericECMParameters):
            raise InvalidModelParametersError(
                f"parameters must be GenericECMParameters, got {type(parameters).__name__}."
            )
        self._ecm_params = parameters

        if ocv_model is not None:
            self._ocv_model = ocv_model
        else:
            # Default linear OCV spanning 0.8 * V_nom to 1.14 * V_nom
            v_nom = self._ecm_params.nominal_voltage_v
            self._ocv_model = LinearOCVModel(
                v_min_v=v_nom * 0.8,
                v_max_v=v_nom * 1.135,
                d_ocv_d_temp_v_per_k=self._ecm_params.entropic_coefficient_v_per_k,
            )

        if thermal_model is not None:
            self._thermal_model = thermal_model
        else:
            self._thermal_model = LumpedThermalModel(
                thermal_capacitance_j_per_k=self._ecm_params.thermal_mass_j_per_k,
                convective_heat_transfer_w_per_k=self._ecm_params.convective_heat_transfer_w_per_k,
            )

        super().__init__(metadata, parameters, initial_state)

    @property
    def ecm_parameters(self) -> GenericECMParameters:
        """Typed ECM parameters."""
        return self._ecm_params

    @property
    def ocv_model(self) -> OCVModel:
        """Configured OCV-SOC relationship provider."""
        return self._ocv_model

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
        """Creates initial ModelState with zero initial polarization voltages."""
        initial_polarizations = tuple(0.0 for _ in range(self._ecm_params.branch_count))
        return ModelState(
            soc_fraction=soc_init,
            temperature_c=temperature_c,
            polarization_voltages_v=initial_polarizations,
            hysteresis_voltage_v=kwargs.get("hysteresis_voltage_v", 0.0),
            timestamp_ns=kwargs.get("timestamp_ns"),
        )

    def _compute_step(
        self,
        model_input: ModelInput,
        current_state: ModelState,
    ) -> ModelOutput:
        """Executes one discrete electro-thermal time step."""
        i_load = model_input.current_a
        dt = model_input.dt_s
        t_amb = model_input.ambient_temperature_c
        t_core = current_state.temperature_c

        # 1. State of Charge Update (Coulomb counting)
        d_soc = calculate_coulomb_soc_step(
            current_a=i_load,
            dt_s=dt,
            nominal_capacity_ah=self._ecm_params.nominal_capacity_ah,
            coulombic_efficiency=self._ecm_params.coulombic_efficiency,
        )
        soc_next = clamp(current_state.soc_fraction + d_soc, 0.0, 1.0)

        # 2. RC Polarization Branch States Update
        v_rc_next_list = []
        current_polarizations = current_state.polarization_voltages_v
        for idx, branch in enumerate(self._ecm_params.rc_branches):
            v_rc_prev = current_polarizations[idx] if idx < len(current_polarizations) else 0.0
            v_rc_next = solve_rc_branch_voltage_step(
                v_rc_current=v_rc_prev,
                current_a=i_load,
                resistance_r_ohm=branch.resistance_r_ohm,
                capacitance_c_farad=branch.capacitance_c_farad,
                dt_s=dt,
            )
            v_rc_next_list.append(v_rc_next)
        v_rc_next_tuple = tuple(v_rc_next_list)

        # 3. Voltage Calculation
        v_oc = self._ocv_model.get_ocv(soc_next, t_core)
        v_r0_drop = i_load * self._ecm_params.series_resistance_r0_ohm
        v_pol_total = sum(v_rc_next_tuple)
        v_term = v_oc - v_r0_drop - v_pol_total - current_state.hysteresis_voltage_v
        assert_finite(v_term, "terminal_voltage_v")

        # 4. Heat Generation Calculation
        # Q_joule = I^2 * R0
        q_joule = (i_load ** 2) * self._ecm_params.series_resistance_r0_ohm

        # Q_polarization = sum(V_rc,i^2 / R_i)
        q_pol = 0.0
        for idx, branch in enumerate(self._ecm_params.rc_branches):
            if branch.resistance_r_ohm > 0.0:
                q_pol += (v_rc_next_tuple[idx] ** 2) / branch.resistance_r_ohm

        # Q_entropic = I * T_kelvin * (dOCV/dT)
        t_kelvin = t_core + 273.15
        d_ocv_d_temp = self._ocv_model.get_docv_dtemp(soc_next, t_core)
        q_entropic = i_load * t_kelvin * d_ocv_d_temp

        q_gen_total = max(0.0, q_joule + q_pol + q_entropic)
        assert_finite(q_gen_total, "heat_generation_w")

        # 5. Thermal Evolution Step
        next_temp_c = self._thermal_model.step(
            heat_generation_w=q_gen_total,
            dt_s=dt,
            ambient_temperature_c=t_amb,
            current_temp_c=t_core,
        )
        assert_finite(next_temp_c, "next_temp_c")

        # 6. Construct Next ModelState x[k+1]
        next_state = current_state.with_updates(
            soc_fraction=soc_next,
            temperature_c=next_temp_c,
            polarization_voltages_v=v_rc_next_tuple,
            timestamp_ns=model_input.timestamp_ns,
        )

        # 7. Construct ModelOutput
        return ModelOutput(
            terminal_voltage_v=v_term,
            open_circuit_voltage_v=v_oc,
            state=next_state,
            heat_generation_w=q_gen_total,
            internal_resistance_mohm=self._ecm_params.total_dc_resistance_mohm,
            derivatives={
                "d_soc_dt": d_soc / dt if dt > 0 else 0.0,
                "d_temp_dt": (next_temp_c - t_core) / dt if dt > 0 else 0.0,
            },
        )

    # --------------------------------------------------------------------------
    # Model Factory Helpers
    # --------------------------------------------------------------------------
    @classmethod
    def create_rint_model(
        cls,
        model_id: str,
        nominal_capacity_ah: float,
        nominal_voltage_v: float,
        r0_ohm: float = 0.025,
        cell_mass_kg: float = 0.045,
        coulombic_efficiency: float = 1.0,
        ocv_model: Optional[OCVModel] = None,
    ) -> "GenericECMModel":
        """Factory creating a 0-RC Internal Resistance ($R_{int}$) model."""
        metadata = ModelMetadata(
            model_id=model_id,
            name=f"0-RC Rint Model ({model_id})",
            paradigm="ECM_0RC",
        )
        params = GenericECMParameters(
            nominal_capacity_ah=nominal_capacity_ah,
            nominal_voltage_v=nominal_voltage_v,
            cell_mass_kg=cell_mass_kg,
            series_resistance_r0_ohm=r0_ohm,
            rc_branches=(),
            coulombic_efficiency=coulombic_efficiency,
        )
        return cls(metadata=metadata, parameters=params, ocv_model=ocv_model)

    @classmethod
    def create_thevenin_1rc_model(
        cls,
        model_id: str,
        nominal_capacity_ah: float,
        nominal_voltage_v: float,
        r0_ohm: float = 0.025,
        r1_ohm: float = 0.015,
        c1_farad: float = 1200.0,
        cell_mass_kg: float = 0.045,
        coulombic_efficiency: float = 1.0,
        ocv_model: Optional[OCVModel] = None,
    ) -> "GenericECMModel":
        """Factory creating a standard 1-RC Thevenin equivalent circuit model."""
        metadata = ModelMetadata(
            model_id=model_id,
            name=f"1-RC Thevenin Model ({model_id})",
            paradigm="ECM_1RC",
        )
        params = GenericECMParameters(
            nominal_capacity_ah=nominal_capacity_ah,
            nominal_voltage_v=nominal_voltage_v,
            cell_mass_kg=cell_mass_kg,
            series_resistance_r0_ohm=r0_ohm,
            rc_branches=(RCBranchParameters(resistance_r_ohm=r1_ohm, capacitance_c_farad=c1_farad),),
            coulombic_efficiency=coulombic_efficiency,
        )
        return cls(metadata=metadata, parameters=params, ocv_model=ocv_model)

    @classmethod
    def create_dual_polarization_2rc_model(
        cls,
        model_id: str,
        nominal_capacity_ah: float,
        nominal_voltage_v: float,
        r0_ohm: float = 0.025,
        r1_ohm: float = 0.015,
        c1_farad: float = 1200.0,
        r2_ohm: float = 0.010,
        c2_farad: float = 4500.0,
        cell_mass_kg: float = 0.045,
        coulombic_efficiency: float = 1.0,
        ocv_model: Optional[OCVModel] = None,
    ) -> "GenericECMModel":
        """Factory creating a 2-RC Dual Polarization equivalent circuit model."""
        metadata = ModelMetadata(
            model_id=model_id,
            name=f"2-RC Dual Polarization Model ({model_id})",
            paradigm="ECM_2RC",
        )
        params = GenericECMParameters(
            nominal_capacity_ah=nominal_capacity_ah,
            nominal_voltage_v=nominal_voltage_v,
            cell_mass_kg=cell_mass_kg,
            series_resistance_r0_ohm=r0_ohm,
            rc_branches=(
                RCBranchParameters(resistance_r_ohm=r1_ohm, capacitance_c_farad=c1_farad),
                RCBranchParameters(resistance_r_ohm=r2_ohm, capacitance_c_farad=c2_farad),
            ),
            coulombic_efficiency=coulombic_efficiency,
        )
        return cls(metadata=metadata, parameters=params, ocv_model=ocv_model)
