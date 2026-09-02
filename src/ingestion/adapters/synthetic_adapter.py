"""Synthetic Telemetry Generator and Ingestion Adapter.

Generates realistic, physically plausible telemetry snapshots for testing,
simulation, HIL benchmarks, and mock streaming pipelines.
"""

from dataclasses import dataclass, field
import math
import random
import time
from typing import Any, Mapping, Optional, Union

from src.ingestion.base import AbstractIngestionAdapter, PacketMetadata
from src.schemas.telemetry_schema import validate_telemetry_payload
from src.telemetry.snapshots import TelemetrySnapshot


@dataclass(frozen=True)
class SyntheticTelemetryConfig:
    """Configuration parameters for synthetic battery telemetry generation."""

    system_id: str = "synthetic_battery_pack"
    cell_count: int = 4
    nominal_cell_voltage_v: float = 3.7
    nominal_capacity_ah: float = 2.5
    initial_soc_fraction: float = 0.90
    initial_temperature_c: float = 25.0
    current_mode: str = "PULSE"  # "CONSTANT", "PULSE", "SINE", "CHARGE"
    base_current_a: float = 2.0
    pulse_period_s: float = 10.0
    voltage_noise_std_v: float = 0.001
    temperature_noise_std_c: float = 0.05
    seed: Optional[int] = 42


class SyntheticTelemetryAdapter(AbstractIngestionAdapter):
    """Generates synthetic, deterministic battery telemetry streams."""

    def __init__(
        self,
        config: Optional[SyntheticTelemetryConfig] = None,
        adapter_name: str = "SyntheticTelemetryAdapter",
    ) -> None:
        super().__init__(adapter_name=adapter_name)
        self._config = config or SyntheticTelemetryConfig()
        self._rng = random.Random(self._config.seed)
        self._current_soc = self._config.initial_soc_fraction
        self._current_temp = self._config.initial_temperature_c

    def supports_format(self, format_identifier: str) -> bool:
        """Returns True if the format is SYNTHETIC or MOCK."""
        fmt = format_identifier.strip().upper()
        return fmt in ("SYNTHETIC", "MOCK", "GENERATOR")

    def generate_step(
        self,
        step_index: int,
        dt_s: float,
        override_current_a: Optional[float] = None,
        timestamp_ns: Optional[int] = None,
    ) -> TelemetrySnapshot:
        """Generates the next sequential synthetic TelemetrySnapshot."""
        t_s = step_index * dt_s
        ts_ns = timestamp_ns if timestamp_ns is not None else int(t_s * 1_000_000_000)

        # 1. Determine load current
        if override_current_a is not None:
            i_load = float(override_current_a)
        else:
            mode = self._config.current_mode.upper()
            if mode == "CONSTANT":
                i_load = self._config.base_current_a
            elif mode == "PULSE":
                # Square wave pulse: discharge for half period, rest for half period
                phase = (t_s % self._config.pulse_period_s) / self._config.pulse_period_s
                i_load = self._config.base_current_a if phase < 0.5 else 0.0
            elif mode == "SINE":
                omega = 2.0 * math.pi / self._config.pulse_period_s
                i_load = self._config.base_current_a * math.sin(omega * t_s)
            elif mode == "CHARGE":
                i_load = -abs(self._config.base_current_a)
            else:
                i_load = self._config.base_current_a

        # 2. Update internal SOC via Coulomb integration
        d_soc = -(i_load * dt_s) / (self._config.nominal_capacity_ah * 3600.0)
        self._current_soc = max(0.0, min(1.0, self._current_soc + d_soc))

        # 3. Update temperature via Joule heating approximation
        # P_loss = I^2 * R (assume 0.02 Ohm per cell)
        p_loss_total = (i_load**2) * 0.02 * self._config.cell_count
        # dT = (P_loss - hA(T - T_amb)) * dt / C_th (assume C_th=200 J/K, hA=1.0 W/K)
        d_temp = (p_loss_total - 1.0 * (self._current_temp - self._config.initial_temperature_c)) * dt_s / 200.0
        self._current_temp += d_temp

        # 4. Synthesize cell voltages with slight dispersion
        # OCV approximation: V_oc = 3.0 + 1.15 * soc + 0.05 * ln(soc + 1e-3)
        v_oc = 3.0 + 1.15 * self._current_soc + 0.05 * math.log(max(1e-3, self._current_soc))
        v_cell_mean = v_oc - (i_load / 1.0) * 0.02  # 1P branch

        direct_cells = []
        cell_voltages = []
        for c_idx in range(self._config.cell_count):
            # Deterministic variation per cell index
            imbalance = ((c_idx - self._config.cell_count / 2.0) * 0.005)
            noise_v = self._rng.gauss(0.0, self._config.voltage_noise_std_v)
            v_cell = max(2.5, min(4.3, v_cell_mean + imbalance + noise_v))
            cell_voltages.append(v_cell)
            direct_cells.append({
                "cell_id": f"cell_{c_idx}",
                "voltage_v": round(v_cell, 4),
                "temperature_c": round(self._current_temp + self._rng.gauss(0.0, self._config.temperature_noise_std_c), 2),
                "soc_fraction": round(self._current_soc, 4),
            })

        pack_voltage = sum(cell_voltages)
        noise_t = self._rng.gauss(0.0, self._config.temperature_noise_std_c)

        payload: dict[str, Any] = {
            "snapshot_id": f"{self._config.system_id}_{ts_ns}",
            "system_id": self._config.system_id,
            "timestamp_ns": ts_ns,
            "sequence_number": step_index,
            "pack_voltage_v": round(pack_voltage, 4),
            "pack_current_a": round(i_load, 4),
            "pack_power_w": round(pack_voltage * i_load, 3),
            "ambient_temperature_c": round(self._config.initial_temperature_c, 2),
            "max_cell_temperature_c": round(self._current_temp + noise_t, 2),
            "min_cell_temperature_c": round(self._current_temp - noise_t, 2),
            "avg_cell_temperature_c": round(self._current_temp, 2),
            "soc_fraction": round(self._current_soc, 4),
            "soh_fraction": 1.0,
            "direct_cells": direct_cells,
        }

        return validate_telemetry_payload(payload)

    def parse(
        self,
        raw_data: Union[str, bytes, Mapping[str, Any]],
        metadata: Optional[PacketMetadata] = None,
    ) -> TelemetrySnapshot:
        """Parses generator instructions or returns a generated snapshot."""
        if isinstance(raw_data, Mapping):
            step = int(raw_data.get("step_index", 0))
            dt = float(raw_data.get("dt_s", 0.1))
            current = raw_data.get("current_a")
            ts_ns = raw_data.get("timestamp_ns")
            return self.generate_step(step_index=step, dt_s=dt, override_current_a=current, timestamp_ns=ts_ns)
        return self.generate_step(step_index=0, dt_s=0.1)
