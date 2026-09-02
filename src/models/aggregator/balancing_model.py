"""Passive Cell Balancing Model and Strategy for Multi-Cell Packs.

Simulates dissipative shunt/bleed resistor switching during top balancing to equalize
cell-to-cell State of Charge and voltage dispersion in series-connected battery strings.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from src.models.exceptions import InvalidModelParametersError, InvalidModelStateError
from src.models.math import assert_finite, clamp


@dataclass(frozen=True)
class PassiveBalancingConfig:
    r"""Configuration parameters for passive dissipative cell balancing.

    All physical quantities use explicit SI units:
    - bleed_resistance_ohm: Resistance of the dissipative bypass resistor in Ohms (> 0.0).
    - voltage_threshold_v: Minimum cell voltage below which balancing is inhibited in Volts (> 0.0).
    - voltage_delta_threshold_v: Voltage deviation above the minimum cell required to trigger bleed in Volts (> 0.0).
    - max_balancing_current_a: Maximum allowable bypass current limiter in Amperes (> 0.0).
    - enabled: Master enable toggle for balancing logic.
    """

    bleed_resistance_ohm: float = 33.0
    voltage_threshold_v: float = 3.40
    voltage_delta_threshold_v: float = 0.010
    max_balancing_current_a: Optional[float] = 0.20
    enabled: bool = True

    def __post_init__(self) -> None:
        assert_finite(self.bleed_resistance_ohm, "bleed_resistance_ohm")
        assert_finite(self.voltage_threshold_v, "voltage_threshold_v")
        assert_finite(self.voltage_delta_threshold_v, "voltage_delta_threshold_v")

        if self.bleed_resistance_ohm <= 0.0:
            raise InvalidModelParametersError("bleed_resistance_ohm must be strictly positive (> 0.0).")
        if self.voltage_threshold_v <= 0.0:
            raise InvalidModelParametersError("voltage_threshold_v must be strictly positive (> 0.0).")
        if self.voltage_delta_threshold_v <= 0.0:
            raise InvalidModelParametersError("voltage_delta_threshold_v must be strictly positive (> 0.0).")

        if self.max_balancing_current_a is not None:
            assert_finite(self.max_balancing_current_a, "max_balancing_current_a")
            if self.max_balancing_current_a <= 0.0:
                raise InvalidModelParametersError("max_balancing_current_a must be strictly positive.")


class PassiveBalancingModel:
    """Simulates passive cell balancing by calculating shunt bleed currents and heat dissipation."""

    def __init__(self, config: Optional[PassiveBalancingConfig] = None) -> None:
        self._config = config or PassiveBalancingConfig()

    @property
    def config(self) -> PassiveBalancingConfig:
        """Active balancing configuration."""
        return self._config

    def compute_balancing_currents(
        self,
        cell_voltages_v: Sequence[float],
        is_charging: bool = True,
    ) -> tuple[float, ...]:
        r"""Calculates instantaneous bleed current drawn from each series cell in Amperes.

        Args:
            cell_voltages_v: Sequence of terminal voltages for each series cell.
            is_charging: Whether the battery is currently under charging conditions.

        Returns:
            Tuple of bleed currents $I_{bleed, i} \ge 0.0$ in Amperes.
        """
        if not cell_voltages_v:
            return ()

        for idx, v in enumerate(cell_voltages_v):
            assert_finite(v, f"cell_voltages_v[{idx}]")
            if v <= 0.0:
                raise InvalidModelStateError(f"Cell voltage must be strictly positive, got {v}V at index {idx}.")

        if not self._config.enabled:
            return tuple(0.0 for _ in cell_voltages_v)

        min_v = min(cell_voltages_v)
        bleed_currents = []

        for v in cell_voltages_v:
            delta_v = v - min_v
            # Trigger balancing only if cell voltage is above absolute threshold AND delta threshold
            if v >= self._config.voltage_threshold_v and delta_v >= self._config.voltage_delta_threshold_v:
                i_bleed = v / self._config.bleed_resistance_ohm
                if self._config.max_balancing_current_a is not None:
                    i_bleed = min(i_bleed, self._config.max_balancing_current_a)
                bleed_currents.append(i_bleed)
            else:
                bleed_currents.append(0.0)

        return tuple(bleed_currents)

    def compute_balancing_heat_w(
        self,
        cell_voltages_v: Sequence[float],
        balancing_currents_a: Sequence[float],
    ) -> tuple[float, ...]:
        r"""Calculates instantaneous thermal dissipation $P_{bleed} = V \cdot I_{bleed}$ in Watts."""
        if len(cell_voltages_v) != len(balancing_currents_a):
            raise InvalidModelStateError("Length mismatch between cell voltages and balancing currents.")

        heat_w = []
        for v, i_bleed in zip(cell_voltages_v, balancing_currents_a):
            heat_w.append(v * i_bleed)

        return tuple(heat_w)
