"""Multi-Cell and Battery Pack Scale Aggregator Model.

Simulates Series-Parallel (NsNp) battery pack assemblies, modeling cell-to-cell parameter
variations, voltage dispersion, thermal gradients, hotspot localization, and passive balancing.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from src.domain.battery.value_objects import BatteryTopology
from src.models.aggregator.balancing_model import PassiveBalancingModel
from src.models.base import AbstractBatteryModel, BatteryModel
from src.models.exceptions import (
    InvalidModelInputError,
    InvalidModelParametersError,
    InvalidModelStateError,
    ModelInitializationError,
)
from src.models.math import assert_finite, clamp
from src.models.types import (
    ModelInput,
    ModelMetadata,
    ModelOutput,
    ModelParameters,
    ModelState,
)


@dataclass(frozen=True)
class PackModelOutput(ModelOutput):
    """Extended simulation output container for multi-cell battery packs.

    Provides pack aggregate metrics alongside cell dispersion diagnostics:
    - min_cell_voltage_v: Minimum cell terminal voltage in the pack.
    - max_cell_voltage_v: Maximum cell terminal voltage in the pack.
    - cell_voltage_delta_v: Voltage dispersion across series cells ($V_{max} - V_{min}$).
    - min_cell_soc_fraction: Minimum State of Charge across all cells.
    - max_cell_soc_fraction: Maximum State of Charge across all cells.
    - min_cell_temperature_c: Lowest cell temperature in the pack.
    - max_cell_temperature_c: Thermal hotspot temperature in the pack.
    - total_heat_generation_w: Combined thermal dissipation (cell losses + balancing bypass).
    - balancing_currents_a: Tuple of active bypass currents for each series cell.
    - cell_outputs: Full output vectors from each constituent cell simulation model.
    """

    min_cell_voltage_v: float = 0.0
    max_cell_voltage_v: float = 0.0
    cell_voltage_delta_v: float = 0.0
    min_cell_soc_fraction: float = 0.0
    max_cell_soc_fraction: float = 0.0
    min_cell_temperature_c: float = 25.0
    max_cell_temperature_c: float = 25.0
    total_heat_generation_w: float = 0.0
    balancing_currents_a: tuple[float, ...] = ()
    cell_outputs: tuple[ModelOutput, ...] = ()


class BatteryPackModel(AbstractBatteryModel):
    """Aggregated Battery Pack Simulator for Series-Parallel (NsNp) Assemblies.

    Manages $N_s \times N_p$ cell-level models conforming to the `BatteryModel` protocol:
    - Distributes pack terminal current $I_{pack}$ across parallel branches.
    - Computes series sum of stage voltages to yield total pack terminal voltage $V_{pack}$.
    - Tracks cell-to-cell dispersion ($V_{delta}, SOC_{delta}, T_{delta}$).
    - Simulates active/passive cell balancing dissipation via `PassiveBalancingModel`.
    """

    def __init__(
        self,
        metadata: ModelMetadata,
        topology: BatteryTopology,
        cell_models: Sequence[BatteryModel],
        balancing_model: Optional[PassiveBalancingModel] = None,
    ) -> None:
        if not isinstance(topology, BatteryTopology):
            raise InvalidModelParametersError(
                f"topology must be BatteryTopology, got {type(topology).__name__}."
            )

        expected_cell_count = topology.total_cells
        if len(cell_models) != expected_cell_count:
            raise InvalidModelParametersError(
                f"Topology requires {expected_cell_count} cells ({topology.series_count}S{topology.parallel_count}P), "
                f"but {len(cell_models)} cell_models were provided."
            )

        for idx, cm in enumerate(cell_models):
            if not isinstance(cm, BatteryModel):
                raise InvalidModelParametersError(
                    f"cell_models[{idx}] does not implement BatteryModel protocol."
                )

        self._topology = topology
        self._cells = tuple(cell_models)
        self._balancing_model = balancing_model or PassiveBalancingModel()

        # Representative parameters from first cell
        first_params = self._cells[0].parameters
        super().__init__(metadata=metadata, parameters=first_params)

    @property
    def topology(self) -> BatteryTopology:
        """Configured Series-Parallel pack topology."""
        return self._topology

    @property
    def cell_models(self) -> tuple[BatteryModel, ...]:
        """Tuple of all individual constituent cell model instances."""
        return self._cells

    @property
    def balancing_model(self) -> PassiveBalancingModel:
        """Active cell balancing strategy model."""
        return self._balancing_model

    # --------------------------------------------------------------------------
    # Lifecycle & Abstract Methods
    # --------------------------------------------------------------------------
    def _create_initial_state(
        self,
        soc_init: Union[float, Sequence[float]] = 1.0,
        temperature_c: Union[float, Sequence[float]] = 25.0,
        **kwargs: Any,
    ) -> ModelState:
        """Initializes all constituent cells across the pack and creates aggregate state."""
        n_cells = len(self._cells)

        if isinstance(soc_init, (int, float)):
            soc_list = [float(soc_init)] * n_cells
        else:
            if len(soc_init) != n_cells:
                raise ModelInitializationError(
                    f"soc_init length ({len(soc_init)}) != total cells ({n_cells})."
                )
            soc_list = [float(s) for s in soc_init]

        if isinstance(temperature_c, (int, float)):
            temp_list = [float(temperature_c)] * n_cells
        else:
            if len(temperature_c) != n_cells:
                raise ModelInitializationError(
                    f"temperature_c length ({len(temperature_c)}) != total cells ({n_cells})."
                )
            temp_list = [float(t) for t in temperature_c]

        # Initialize each cell
        self._prev_cell_voltages = []
        for i, cell in enumerate(self._cells):
            cell.initialize(soc_init=soc_list[i], temperature_c=temp_list[i], **kwargs)
            # Estimate initial cell resting open-circuit voltage
            if hasattr(cell, "ocv_model") and cell.ocv_model is not None:
                v_init = cell.ocv_model.get_ocv(cell.state.soc_fraction, cell.state.temperature_c)
            elif hasattr(cell, "parameters") and hasattr(cell.parameters, "nominal_voltage_v"):
                v_init = getattr(cell.parameters, "nominal_voltage_v", 3.7)
            else:
                v_init = 3.7
            self._prev_cell_voltages.append(v_init)

        # Aggregate pack state
        avg_soc = sum(c.state.soc_fraction for c in self._cells) / n_cells
        avg_temp = sum(c.state.temperature_c for c in self._cells) / n_cells
        pack_voltage = sum(self._prev_cell_voltages) / self._topology.parallel_count

        return ModelState(
            soc_fraction=avg_soc,
            temperature_c=avg_temp,
            custom_states={
                "cell_count": float(n_cells),
                "pack_voltage_v": pack_voltage,
            },
        )

    def initialize(
        self,
        soc_init: Union[float, Sequence[float]] = 1.0,
        temperature_c: Union[float, Sequence[float]] = 25.0,
        **kwargs: Any,
    ) -> ModelState:
        """Initializes and records the internal state vector across all cells."""
        new_state = self._create_initial_state(soc_init=soc_init, temperature_c=temperature_c, **kwargs)
        self._state = new_state
        return self._state

    def reset(self, initial_state: Optional[ModelState] = None) -> None:
        """Resets all cell models in the pack."""
        for cell in self._cells:
            cell.reset()
        super().reset(initial_state)

    # --------------------------------------------------------------------------
    # Stepping & Current Distribution
    # --------------------------------------------------------------------------
    def _compute_step(
        self,
        model_input: ModelInput,
        current_state: ModelState,
    ) -> PackModelOutput:
        """Advances pack simulation by time step dt_s under pack load current current_a."""
        i_pack = model_input.current_a
        dt = model_input.dt_s
        t_amb = model_input.ambient_temperature_c

        n_s = self._topology.series_count
        n_p = self._topology.parallel_count

        # 1. Gather current cell terminal voltages for balancing calculation
        stage_voltages = []
        for s in range(n_s):
            v_stage = sum(self._prev_cell_voltages[s * n_p : (s + 1) * n_p]) / n_p
            stage_voltages.append(v_stage)

        # 2. Compute balancing bypass currents
        is_charging = i_pack < 0.0
        balancing_currents = self._balancing_model.compute_balancing_currents(
            stage_voltages,
            is_charging=is_charging,
        )
        balancing_heat_w = self._balancing_model.compute_balancing_heat_w(
            stage_voltages,
            balancing_currents,
        )

        # 3. Step individual cell models with effective currents
        cell_outputs: list[ModelOutput] = []
        total_cell_heat_w = 0.0

        for s in range(n_s):
            i_bleed_stage = balancing_currents[s] if s < len(balancing_currents) else 0.0
            # Total current through this stage
            i_stage_total = i_pack + i_bleed_stage
            i_cell_eff = i_stage_total / n_p

            for p in range(n_p):
                cell_idx = s * n_p + p
                cell = self._cells[cell_idx]
                cell_input = ModelInput(
                    current_a=i_cell_eff,
                    dt_s=dt,
                    ambient_temperature_c=t_amb,
                )
                out = cell.step(cell_input)
                cell_outputs.append(out)
                total_cell_heat_w += out.heat_generation_w

        # 4. Aggregate Pack Output Metrics
        all_cell_voltages = [o.terminal_voltage_v for o in cell_outputs]
        all_cell_socs = [o.state.soc_fraction for o in cell_outputs]
        all_cell_temps = [o.state.temperature_c for o in cell_outputs]

        # Total pack terminal voltage = sum of stage average voltages
        pack_voltage = 0.0
        for s in range(n_s):
            v_stage = sum(all_cell_voltages[s * n_p : (s + 1) * n_p]) / n_p
            pack_voltage += v_stage

        avg_soc = sum(all_cell_socs) / len(all_cell_socs)
        avg_temp = sum(all_cell_temps) / len(all_cell_temps)
        total_balancing_heat = sum(balancing_heat_w)
        total_pack_heat = total_cell_heat_w + total_balancing_heat

        min_v = min(all_cell_voltages)
        max_v = max(all_cell_voltages)
        min_soc = min(all_cell_socs)
        max_soc = max(all_cell_socs)
        min_temp = min(all_cell_temps)
        max_temp = max(all_cell_temps)

        # Update cell voltages cache for next balancing evaluation
        self._prev_cell_voltages = list(all_cell_voltages)

        # Update pack state
        next_state = ModelState(
            soc_fraction=avg_soc,
            temperature_c=avg_temp,
            custom_states={
                "pack_voltage_v": pack_voltage,
                "min_cell_voltage_v": min_v,
                "max_cell_voltage_v": max_v,
                "cell_voltage_delta_v": max_v - min_v,
                "hotspot_temperature_c": max_temp,
                "total_heat_generation_w": total_pack_heat,
            },
        )

        return PackModelOutput(
            terminal_voltage_v=pack_voltage,
            open_circuit_voltage_v=sum(o.open_circuit_voltage_v for o in cell_outputs) / n_p,
            heat_generation_w=total_pack_heat,
            state=next_state,
            min_cell_voltage_v=min_v,
            max_cell_voltage_v=max_v,
            cell_voltage_delta_v=max_v - min_v,
            min_cell_soc_fraction=min_soc,
            max_cell_soc_fraction=max_soc,
            min_cell_temperature_c=min_temp,
            max_cell_temperature_c=max_temp,
            total_heat_generation_w=total_pack_heat,
            balancing_currents_a=tuple(balancing_currents),
            cell_outputs=tuple(cell_outputs),
        )

    def step(
        self,
        model_input: ModelInput,
        state: Optional[ModelState] = None,
    ) -> PackModelOutput:
        """Executes a discrete pack simulation step and updates internal pack state."""
        current_state = state if state is not None else self._state
        output = self._compute_step(model_input, current_state)
        if state is None:
            self._state = output.state
        return output

    # --------------------------------------------------------------------------
    # Factory Constructors
    # --------------------------------------------------------------------------
    @classmethod
    def from_cell_factory(
        cls,
        metadata: ModelMetadata,
        topology: BatteryTopology,
        cell_factory: Callable[[int], BatteryModel],
        balancing_model: Optional[PassiveBalancingModel] = None,
    ) -> "BatteryPackModel":
        """Constructs a pack model by generating each constituent cell model via a factory callable."""
        total_cells = topology.total_cells
        cells = [cell_factory(i) for i in range(total_cells)]
        return cls(
            metadata=metadata,
            topology=topology,
            cell_models=cells,
            balancing_model=balancing_model,
        )
