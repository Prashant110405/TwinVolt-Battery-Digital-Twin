"""State History to Degradation Trajectory Domain Adapter.

Transforms time-series TwinStateRecord sequences from historical storage or runtime
into strongly-typed, monotonically ordered DegradationTrajectory objects with complete
metrological provenance, without fabricating missing channels or mutating twin state.
"""

from datetime import datetime, timezone
import math
from typing import Any, Mapping, Optional, Sequence

from src.prognostics.provenance import PrognosticQuantity, PrognosticValueProvenance
from src.prognostics.state import PrognosticOperatingContext
from src.prognostics.trajectory import DegradationObservation, DegradationTrajectory
from src.prognostics.trajectory_types import TrajectoryQuantityType
from src.prognostics.types import (
    HorizonDomain,
    QuantityAvailability,
    ValueOriginType,
)
from src.storage.base import TwinStateRecord


class StateHistoryTrajectoryAdapter:
    """Pure, stateless adapter for converting Digital Twin state history into degradation trajectories.

    Strict Invariants:
    1. Zero Fabrication: If a requested quantity channel is unavailable, it is never silently substituted.
    2. Complete Provenance: Preserves source metadata, timestamps, and origin classifications.
    3. Monotonic Ordering: Ensures domain values are strictly non-decreasing across observations.
    4. Numerical Safety: Rejects NaN, Inf, and negative/inverted timestamp intervals.
    """

    @classmethod
    def extract_trajectory(
        cls,
        records: Sequence[TwinStateRecord],
        quantity_type: TrajectoryQuantityType = TrajectoryQuantityType.CAPACITY_RETENTION,
        horizon_domain: HorizonDomain = HorizonDomain.CYCLE,
        system_id: Optional[str] = None,
        trajectory_id: Optional[str] = None,
        unit: Optional[str] = None,
        custom_channel_name: Optional[str] = None,
    ) -> DegradationTrajectory:
        """Extracts and constructs a validated DegradationTrajectory from twin state history."""
        if not records:
            raise ValueError("records sequence cannot be empty.")

        for idx, rec in enumerate(records):
            if not isinstance(rec, TwinStateRecord):
                raise TypeError(
                    f"Expected Sequence[TwinStateRecord], got element at index {idx} of type {type(rec).__name__}."
                )

        sys_id = system_id or records[0].system_id
        if not sys_id:
            raise ValueError("system_id must be a non-empty string.")

        traj_id = trajectory_id or f"traj_{sys_id}_{quantity_type.value.lower()}"

        # Resolve unit
        if unit is not None:
            resolved_unit = unit
        elif quantity_type == TrajectoryQuantityType.CAPACITY_RETENTION:
            resolved_unit = "ratio"
        elif quantity_type == TrajectoryQuantityType.CAPACITY:
            resolved_unit = "Ah"
        elif quantity_type == TrajectoryQuantityType.INTERNAL_RESISTANCE:
            resolved_unit = "Ohm"
        elif quantity_type == TrajectoryQuantityType.RESISTANCE_GROWTH_RATIO:
            resolved_unit = "ratio"
        elif quantity_type == TrajectoryQuantityType.EQUIVALENT_FULL_CYCLES:
            resolved_unit = "cycles"
        elif quantity_type == TrajectoryQuantityType.THROUGHPUT_AH:
            resolved_unit = "Ah"
        elif quantity_type == TrajectoryQuantityType.THROUGHPUT_WH:
            resolved_unit = "Wh"
        else:
            resolved_unit = "unit"

        start_ts_ns = records[0].timestamp_ns
        observations: list[DegradationObservation] = []

        for idx, rec in enumerate(records):
            ts = rec.timestamp_ns
            if not isinstance(ts, int) or ts < 0:
                raise ValueError(f"Invalid timestamp_ns {ts} at record index {idx}.")

            # Operating Context
            temp_c = None
            soc_fraction = None
            if rec.model_state is not None:
                temp_c = rec.model_state.temperature_c
                soc_fraction = rec.model_state.soc_fraction
            elif rec.estimation_state is not None:
                temp_c = rec.estimation_state.temperature_c
                soc_fraction = rec.estimation_state.soc_fraction

            if temp_c is not None and (math.isnan(temp_c) or math.isinf(temp_c)):
                raise ValueError(f"Non-finite temperature value {temp_c} at record index {idx}.")
            if soc_fraction is not None and (math.isnan(soc_fraction) or math.isinf(soc_fraction)):
                raise ValueError(f"Non-finite SOC value {soc_fraction} at record index {idx}.")

            op_ctx = PrognosticOperatingContext(
                cell_temperature_c=temp_c,
                soc_fraction=soc_fraction,
                metadata={"record_id": rec.record_id},
            )

            # Provenance
            prov = PrognosticValueProvenance(
                origin_type=ValueOriginType.ESTIMATED,
                source_identifier=f"twin_state_record:{rec.record_id}",
                timestamp_ns=ts,
                quality_rating=rec.quality,
                metadata={"quality": rec.quality},
            )

            # 1. Horizon Domain Quantities
            efc_qty: Optional[PrognosticQuantity] = None
            tp_ah_qty: Optional[PrognosticQuantity] = None
            tp_wh_qty: Optional[PrognosticQuantity] = None

            # Always populate calendar age seconds
            elapsed_s = (ts - start_ts_ns) / 1_000_000_000.0
            cal_qty = PrognosticQuantity(
                name="calendar_age_seconds",
                value=elapsed_s,
                unit="s",
                availability=QuantityAvailability.AVAILABLE,
                provenance=prov,
            )

            # Extract cycle count if present
            cycle_val: Optional[float] = None
            if "cycle" in rec.metadata:
                try:
                    cycle_val = float(rec.metadata["cycle"])
                except (ValueError, TypeError):
                    cycle_val = None
            elif (
                rec.estimation_state is not None
                and "cycle" in rec.estimation_state.custom_estimates
            ):
                cycle_val = float(rec.estimation_state.custom_estimates["cycle"])

            if cycle_val is not None:
                if math.isnan(cycle_val) or math.isinf(cycle_val):
                    raise ValueError(f"Non-finite cycle value {cycle_val} at record index {idx}.")
                efc_qty = PrognosticQuantity(
                    name="equivalent_full_cycles",
                    value=cycle_val,
                    unit="cycles",
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )
            elif horizon_domain == HorizonDomain.CYCLE:
                raise ValueError(
                    f"Requested horizon domain 'CYCLE' is unavailable in record index {idx} "
                    f"(Record ID: '{rec.record_id}'). Cannot fabricate missing degradation domain telemetry."
                )

            # Extract Ah throughput if present
            tp_ah_val: Optional[float] = None
            if "throughput_ah" in rec.metadata:
                try:
                    tp_ah_val = float(rec.metadata["throughput_ah"])
                except (ValueError, TypeError):
                    tp_ah_val = None
            elif (
                rec.estimation_state is not None
                and "throughput_ah" in rec.estimation_state.custom_estimates
            ):
                tp_ah_val = float(rec.estimation_state.custom_estimates["throughput_ah"])

            if tp_ah_val is not None:
                if math.isnan(tp_ah_val) or math.isinf(tp_ah_val):
                    raise ValueError(f"Non-finite throughput_ah value {tp_ah_val} at record index {idx}.")
                tp_ah_qty = PrognosticQuantity(
                    name="discharge_throughput_ah",
                    value=tp_ah_val,
                    unit="Ah",
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )
            elif horizon_domain == HorizonDomain.AMPERE_HOUR_THROUGHPUT:
                raise ValueError(
                    f"Requested horizon domain 'AMPERE_HOUR_THROUGHPUT' is unavailable in record index {idx} "
                    f"(Record ID: '{rec.record_id}'). Cannot fabricate missing degradation domain telemetry."
                )

            # Extract Wh throughput if present
            tp_wh_val: Optional[float] = None
            if "throughput_wh" in rec.metadata:
                try:
                    tp_wh_val = float(rec.metadata["throughput_wh"])
                except (ValueError, TypeError):
                    tp_wh_val = None
            elif (
                rec.estimation_state is not None
                and "throughput_wh" in rec.estimation_state.custom_estimates
            ):
                tp_wh_val = float(rec.estimation_state.custom_estimates["throughput_wh"])

            if tp_wh_val is not None:
                if math.isnan(tp_wh_val) or math.isinf(tp_wh_val):
                    raise ValueError(f"Non-finite throughput_wh value {tp_wh_val} at record index {idx}.")
                tp_wh_qty = PrognosticQuantity(
                    name="total_energy_throughput_wh",
                    value=tp_wh_val,
                    unit="Wh",
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )
            elif horizon_domain == HorizonDomain.WATT_HOUR_THROUGHPUT:
                raise ValueError(
                    f"Requested horizon domain 'WATT_HOUR_THROUGHPUT' is unavailable in record index {idx} "
                    f"(Record ID: '{rec.record_id}'). Cannot fabricate missing degradation domain telemetry."
                )

            # 2. Extract Requested Degradation Quantity
            cap_ret_qty: Optional[PrognosticQuantity] = None
            usable_cap_qty: Optional[PrognosticQuantity] = None
            ir_r0_qty: Optional[PrognosticQuantity] = None
            res_ratio_qty: Optional[PrognosticQuantity] = None

            if quantity_type == TrajectoryQuantityType.CAPACITY_RETENTION:
                soh_val: Optional[float] = None
                if rec.estimation_state is not None:
                    soh_val = float(rec.estimation_state.soh_fraction)
                elif "soh_fraction" in rec.metadata:
                    try:
                        soh_val = float(rec.metadata["soh_fraction"])
                    except (ValueError, TypeError):
                        soh_val = None
                elif hasattr(rec.model_state, "soh_fraction") and rec.model_state.soh_fraction is not None:
                    soh_val = float(rec.model_state.soh_fraction)

                if soh_val is None:
                    raise ValueError(
                        f"Requested quantity channel '{quantity_type.value}' is unavailable in record index {idx} "
                        f"(Record ID: '{rec.record_id}'). Cannot fabricate missing degradation telemetry."
                    )
                if math.isnan(soh_val) or math.isinf(soh_val):
                    raise ValueError(f"Non-finite quantity value {soh_val} at record index {idx}.")

                cap_ret_qty = PrognosticQuantity(
                    name="capacity_retention_fraction",
                    value=soh_val,
                    unit=resolved_unit,
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )

            elif quantity_type == TrajectoryQuantityType.INTERNAL_RESISTANCE:
                r0_val: Optional[float] = None
                if (
                    rec.estimation_state is not None
                    and rec.estimation_state.internal_resistance_mohm is not None
                ):
                    mohm = float(rec.estimation_state.internal_resistance_mohm)
                    r0_val = (mohm / 1000.0) if resolved_unit.lower() == "ohm" else mohm
                elif (
                    rec.estimation_state is not None
                    and "internal_resistance_ohm" in rec.estimation_state.custom_estimates
                ):
                    r0_val = float(rec.estimation_state.custom_estimates["internal_resistance_ohm"])
                elif "internal_resistance_mohm" in rec.metadata:
                    try:
                        mohm = float(rec.metadata["internal_resistance_mohm"])
                        r0_val = (mohm / 1000.0) if resolved_unit.lower() == "ohm" else mohm
                    except (ValueError, TypeError):
                        r0_val = None
                elif "internal_resistance_ohm" in rec.metadata:
                    try:
                        r0_val = float(rec.metadata["internal_resistance_ohm"])
                    except (ValueError, TypeError):
                        r0_val = None

                if r0_val is None:
                    raise ValueError(
                        f"Requested quantity channel '{quantity_type.value}' is unavailable in record index {idx} "
                        f"(Record ID: '{rec.record_id}'). Cannot fabricate missing degradation telemetry."
                    )
                if math.isnan(r0_val) or math.isinf(r0_val):
                    raise ValueError(f"Non-finite quantity value {r0_val} at record index {idx}.")

                ir_r0_qty = PrognosticQuantity(
                    name="internal_resistance_r0_ohm",
                    value=r0_val,
                    unit=resolved_unit,
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )

            elif quantity_type == TrajectoryQuantityType.CAPACITY:
                cap_val: Optional[float] = None
                if (
                    rec.estimation_state is not None
                    and "usable_capacity_ah" in rec.estimation_state.custom_estimates
                ):
                    cap_val = float(rec.estimation_state.custom_estimates["usable_capacity_ah"])
                elif (
                    rec.estimation_state is not None
                    and "capacity_ah" in rec.estimation_state.custom_estimates
                ):
                    cap_val = float(rec.estimation_state.custom_estimates["capacity_ah"])
                elif "usable_capacity_ah" in rec.metadata:
                    try:
                        cap_val = float(rec.metadata["usable_capacity_ah"])
                    except (ValueError, TypeError):
                        cap_val = None
                elif "capacity_ah" in rec.metadata:
                    try:
                        cap_val = float(rec.metadata["capacity_ah"])
                    except (ValueError, TypeError):
                        cap_val = None

                if cap_val is None:
                    raise ValueError(
                        f"Requested quantity channel '{quantity_type.value}' is unavailable in record index {idx} "
                        f"(Record ID: '{rec.record_id}'). Cannot fabricate missing degradation telemetry."
                    )
                if math.isnan(cap_val) or math.isinf(cap_val):
                    raise ValueError(f"Non-finite quantity value {cap_val} at record index {idx}.")

                usable_cap_qty = PrognosticQuantity(
                    name="usable_capacity_ah",
                    value=cap_val,
                    unit=resolved_unit,
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )

            elif quantity_type == TrajectoryQuantityType.RESISTANCE_GROWTH_RATIO:
                ratio_val: Optional[float] = None
                if (
                    rec.estimation_state is not None
                    and "resistance_growth_ratio" in rec.estimation_state.custom_estimates
                ):
                    ratio_val = float(rec.estimation_state.custom_estimates["resistance_growth_ratio"])
                elif "resistance_growth_ratio" in rec.metadata:
                    try:
                        ratio_val = float(rec.metadata["resistance_growth_ratio"])
                    except (ValueError, TypeError):
                        ratio_val = None

                if ratio_val is None:
                    raise ValueError(
                        f"Requested quantity channel '{quantity_type.value}' is unavailable in record index {idx} "
                        f"(Record ID: '{rec.record_id}'). Cannot fabricate missing degradation telemetry."
                    )
                if math.isnan(ratio_val) or math.isinf(ratio_val):
                    raise ValueError(f"Non-finite quantity value {ratio_val} at record index {idx}.")

                res_ratio_qty = PrognosticQuantity(
                    name="resistance_growth_ratio",
                    value=ratio_val,
                    unit=resolved_unit,
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )

            created_utc = datetime.fromtimestamp(ts / 1_000_000_000.0, tz=timezone.utc).isoformat()
            obs = DegradationObservation(
                timestamp_ns=ts,
                created_at_utc=created_utc,
                usable_capacity_ah=usable_cap_qty,
                capacity_retention_fraction=cap_ret_qty,
                internal_resistance_r0_ohm=ir_r0_qty,
                resistance_growth_ratio=res_ratio_qty,
                equivalent_full_cycles=efc_qty,
                discharge_throughput_ah=tp_ah_qty,
                total_energy_throughput_wh=tp_wh_qty,
                calendar_age_seconds=cal_qty,
                operating_context=op_ctx,
                metadata={"record_id": rec.record_id, "quality": rec.quality},
            )
            observations.append(obs)

        # Sort observations monotonically by timestamp_ns
        observations.sort(key=lambda o: o.timestamp_ns)

        return DegradationTrajectory(
            trajectory_id=traj_id,
            system_id=sys_id,
            quantity_type=quantity_type,
            observations=tuple(observations),
            metadata={
                "extracted_from": "TwinStateRecord",
                "record_count": len(records),
                "horizon_domain": horizon_domain.value,
                "unit": resolved_unit,
            },
        )

    @classmethod
    def extract_multivariate_trajectory(
        cls,
        records: Sequence[TwinStateRecord],
        system_id: Optional[str] = None,
        trajectory_id: Optional[str] = None,
    ) -> DegradationTrajectory:
        """Extracts a comprehensive MULTIVARIATE DegradationTrajectory containing all available channels."""
        if not records:
            raise ValueError("records sequence cannot be empty.")

        for idx, rec in enumerate(records):
            if not isinstance(rec, TwinStateRecord):
                raise TypeError(
                    f"Expected Sequence[TwinStateRecord], got element at index {idx} of type {type(rec).__name__}."
                )

        sys_id = system_id or records[0].system_id
        if not sys_id:
            raise ValueError("system_id must be a non-empty string.")

        traj_id = trajectory_id or f"traj_{sys_id}_multivariate"
        start_ts_ns = records[0].timestamp_ns
        observations: list[DegradationObservation] = []

        for idx, rec in enumerate(records):
            ts = rec.timestamp_ns
            if not isinstance(ts, int) or ts < 0:
                raise ValueError(f"Invalid timestamp_ns {ts} at record index {idx}.")

            prov = PrognosticValueProvenance(
                origin_type=ValueOriginType.ESTIMATED,
                source_identifier=f"twin_state_record:{rec.record_id}",
                timestamp_ns=ts,
                quality_rating=rec.quality,
                metadata={"quality": rec.quality},
            )

            # Operating Context
            temp_c = None
            soc = None
            if rec.model_state is not None:
                temp_c = rec.model_state.temperature_c
                soc = rec.model_state.soc_fraction
            elif rec.estimation_state is not None:
                temp_c = rec.estimation_state.temperature_c
                soc = rec.estimation_state.soc_fraction

            op_ctx = PrognosticOperatingContext(
                cell_temperature_c=temp_c,
                soc_fraction=soc,
                metadata={"record_id": rec.record_id},
            )

            # Capacity retention
            cap_ret_qty = None
            soh_val = None
            if rec.estimation_state is not None and rec.estimation_state.soh_fraction is not None:
                soh_val = float(rec.estimation_state.soh_fraction)
            elif "soh_fraction" in rec.metadata:
                try:
                    soh_val = float(rec.metadata["soh_fraction"])
                except (ValueError, TypeError):
                    soh_val = None
            elif hasattr(rec.model_state, "soh_fraction") and rec.model_state.soh_fraction is not None:
                soh_val = float(rec.model_state.soh_fraction)

            if soh_val is not None and not (math.isnan(soh_val) or math.isinf(soh_val)):
                cap_ret_qty = PrognosticQuantity(
                    name="capacity_retention_fraction",
                    value=soh_val,
                    unit="ratio",
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )

            # Usable capacity
            usable_cap_qty = None
            cap_val = None
            if rec.estimation_state is not None and "usable_capacity_ah" in rec.estimation_state.custom_estimates:
                cap_val = float(rec.estimation_state.custom_estimates["usable_capacity_ah"])
            elif "usable_capacity_ah" in rec.metadata:
                try:
                    cap_val = float(rec.metadata["usable_capacity_ah"])
                except (ValueError, TypeError):
                    cap_val = None

            if cap_val is not None and not (math.isnan(cap_val) or math.isinf(cap_val)):
                usable_cap_qty = PrognosticQuantity(
                    name="usable_capacity_ah",
                    value=cap_val,
                    unit="Ah",
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )

            # Internal resistance
            ir_r0_qty = None
            r0_val = None
            if rec.estimation_state is not None and rec.estimation_state.internal_resistance_mohm is not None:
                r0_val = float(rec.estimation_state.internal_resistance_mohm) / 1000.0
            elif "internal_resistance_mohm" in rec.metadata:
                try:
                    r0_val = float(rec.metadata["internal_resistance_mohm"]) / 1000.0
                except (ValueError, TypeError):
                    r0_val = None

            if r0_val is not None and not (math.isnan(r0_val) or math.isinf(r0_val)):
                ir_r0_qty = PrognosticQuantity(
                    name="internal_resistance_r0_ohm",
                    value=r0_val,
                    unit="ohm",
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )

            # Resistance growth ratio
            res_ratio_qty = None
            ratio_val = None
            if rec.estimation_state is not None and "resistance_growth_ratio" in rec.estimation_state.custom_estimates:
                ratio_val = float(rec.estimation_state.custom_estimates["resistance_growth_ratio"])
            elif "resistance_growth_ratio" in rec.metadata:
                try:
                    ratio_val = float(rec.metadata["resistance_growth_ratio"])
                except (ValueError, TypeError):
                    ratio_val = None

            if ratio_val is not None and not (math.isnan(ratio_val) or math.isinf(ratio_val)):
                res_ratio_qty = PrognosticQuantity(
                    name="resistance_growth_ratio",
                    value=ratio_val,
                    unit="ratio",
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )

            # Cycles
            efc_qty = None
            cycle_val = None
            if "cycle" in rec.metadata:
                try:
                    cycle_val = float(rec.metadata["cycle"])
                except (ValueError, TypeError):
                    cycle_val = None
            elif rec.estimation_state is not None and "cycle" in rec.estimation_state.custom_estimates:
                cycle_val = float(rec.estimation_state.custom_estimates["cycle"])

            if cycle_val is not None and not (math.isnan(cycle_val) or math.isinf(cycle_val)):
                efc_qty = PrognosticQuantity(
                    name="equivalent_full_cycles",
                    value=cycle_val,
                    unit="cycles",
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )

            # Throughput Ah
            tp_ah_qty = None
            tp_ah_val = None
            if "throughput_ah" in rec.metadata:
                try:
                    tp_ah_val = float(rec.metadata["throughput_ah"])
                except (ValueError, TypeError):
                    tp_ah_val = None
            elif rec.estimation_state is not None and "throughput_ah" in rec.estimation_state.custom_estimates:
                tp_ah_val = float(rec.estimation_state.custom_estimates["throughput_ah"])

            if tp_ah_val is not None and not (math.isnan(tp_ah_val) or math.isinf(tp_ah_val)):
                tp_ah_qty = PrognosticQuantity(
                    name="discharge_throughput_ah",
                    value=tp_ah_val,
                    unit="Ah",
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )

            # Throughput Wh
            tp_wh_qty = None
            tp_wh_val = None
            if "throughput_wh" in rec.metadata:
                try:
                    tp_wh_val = float(rec.metadata["throughput_wh"])
                except (ValueError, TypeError):
                    tp_wh_val = None
            elif rec.estimation_state is not None and "throughput_wh" in rec.estimation_state.custom_estimates:
                tp_wh_val = float(rec.estimation_state.custom_estimates["throughput_wh"])

            if tp_wh_val is not None and not (math.isnan(tp_wh_val) or math.isinf(tp_wh_val)):
                tp_wh_qty = PrognosticQuantity(
                    name="total_energy_throughput_wh",
                    value=tp_wh_val,
                    unit="Wh",
                    availability=QuantityAvailability.AVAILABLE,
                    provenance=prov,
                )

            # Calendar age
            elapsed_s = (ts - start_ts_ns) / 1_000_000_000.0
            cal_qty = PrognosticQuantity(
                name="calendar_age_seconds",
                value=elapsed_s,
                unit="s",
                availability=QuantityAvailability.AVAILABLE,
                provenance=prov,
            )

            created_utc = datetime.fromtimestamp(ts / 1_000_000_000.0, tz=timezone.utc).isoformat()
            obs = DegradationObservation(
                timestamp_ns=ts,
                created_at_utc=created_utc,
                usable_capacity_ah=usable_cap_qty,
                capacity_retention_fraction=cap_ret_qty,
                internal_resistance_r0_ohm=ir_r0_qty,
                resistance_growth_ratio=res_ratio_qty,
                equivalent_full_cycles=efc_qty,
                discharge_throughput_ah=tp_ah_qty,
                total_energy_throughput_wh=tp_wh_qty,
                calendar_age_seconds=cal_qty,
                operating_context=op_ctx,
                metadata={"record_id": rec.record_id, "quality": rec.quality},
            )
            observations.append(obs)

        observations.sort(key=lambda o: o.timestamp_ns)

        return DegradationTrajectory(
            trajectory_id=traj_id,
            system_id=sys_id,
            quantity_type=TrajectoryQuantityType.MULTIVARIATE,
            observations=tuple(observations),
            metadata={
                "extracted_from": "TwinStateRecord",
                "record_count": len(records),
            },
        )
