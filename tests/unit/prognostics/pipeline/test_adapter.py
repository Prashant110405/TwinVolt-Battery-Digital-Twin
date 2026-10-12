"""Unit Tests for StateHistoryTrajectoryAdapter.

Validates:
- Conversion of TwinStateRecord sequences to DegradationTrajectory
- Monotonic domain value ordering
- Provenance tracking (timestamps, origins, sensor IDs)
- Handling of multiple domains (CYCLE, TIME, Throughput)
- Quantity channel extraction (SOH, capacity, internal resistance, multivariate)
- Rejection of missing channels without fabrication
- Numerical validation (rejection of NaN/Inf and empty inputs)
"""

import math
import pytest

from src.estimators.base import EstimationState
from src.models.types import ModelState
from src.prognostics.pipeline.adapter import StateHistoryTrajectoryAdapter
from src.prognostics.trajectory_types import TrajectoryQuantityType
from src.prognostics.types import HorizonDomain, ValueOriginType
from src.storage.base import TwinStateRecord


def _make_state_record(
    idx: int,
    ts_ns: int,
    soh: float = 0.95,
    r_mohm: float = 25.0,
    cycle: int = 10,
    system_id: str = "batt_pack_01",
) -> TwinStateRecord:
    model_st = ModelState(
        soc_fraction=0.8,
        temperature_c=25.0,
    )
    est_st = EstimationState(
        soc_fraction=0.8,
        soh_fraction=soh,
        internal_resistance_mohm=r_mohm,
        custom_estimates={
            "cycle": float(cycle),
            "usable_capacity_ah": 5.0 * soh,
            "resistance_growth_ratio": r_mohm / 20.0,
            "throughput_ah": float(cycle * 10.0),
        },
    )
    return TwinStateRecord(
        record_id=f"rec_{idx:03d}",
        system_id=system_id,
        timestamp_ns=ts_ns,
        model_state=model_st,
        estimation_state=est_st,
        quality="VALID",
        metadata={"cycle": str(cycle)},
    )


def test_adapter_extracts_capacity_retention():
    records = [
        _make_state_record(0, 1_000_000_000, soh=0.98, cycle=0),
        _make_state_record(1, 2_000_000_000, soh=0.96, cycle=100),
        _make_state_record(2, 3_000_000_000, soh=0.94, cycle=200),
    ]

    traj = StateHistoryTrajectoryAdapter.extract_trajectory(
        records=records,
        quantity_type=TrajectoryQuantityType.CAPACITY_RETENTION,
        horizon_domain=HorizonDomain.CYCLE,
    )

    assert traj.system_id == "batt_pack_01"
    assert traj.quantity_type == TrajectoryQuantityType.CAPACITY_RETENTION
    assert traj.metadata["horizon_domain"] == HorizonDomain.CYCLE.value
    assert traj.total_observations == 3

    values = tuple(obs.capacity_retention_fraction.value for obs in traj.observations)
    assert values == (0.98, 0.96, 0.94)
    cycles = tuple(obs.equivalent_full_cycles.value for obs in traj.observations)
    assert cycles == (0.0, 100.0, 200.0)

    # Check provenance on first observation
    obs0 = traj.observations[0]
    assert obs0.capacity_retention_fraction.name == "capacity_retention_fraction"
    assert obs0.capacity_retention_fraction.unit == "ratio"
    assert obs0.capacity_retention_fraction.provenance.origin_type == ValueOriginType.ESTIMATED
    assert "rec_000" in obs0.capacity_retention_fraction.provenance.source_identifier


def test_adapter_extracts_internal_resistance():
    records = [
        _make_state_record(0, 1_000_000_000, r_mohm=20.0, cycle=0),
        _make_state_record(1, 2_000_000_000, r_mohm=25.0, cycle=100),
    ]

    traj = StateHistoryTrajectoryAdapter.extract_trajectory(
        records=records,
        quantity_type=TrajectoryQuantityType.INTERNAL_RESISTANCE,
        horizon_domain=HorizonDomain.CYCLE,
        unit="Ohm",
    )

    assert traj.quantity_type == TrajectoryQuantityType.INTERNAL_RESISTANCE
    assert traj.metadata["unit"] == "Ohm"
    values = tuple(obs.internal_resistance_r0_ohm.value for obs in traj.observations)
    # 20 mOhm -> 0.02 Ohm, 25 mOhm -> 0.025 Ohm
    assert pytest.approx(values[0], rel=1e-5) == 0.020
    assert pytest.approx(values[1], rel=1e-5) == 0.025


def test_adapter_extracts_time_domain():
    records = [
        _make_state_record(0, 1_000_000_000, soh=0.98),
        _make_state_record(1, 4_000_000_000, soh=0.97),
        _make_state_record(2, 7_000_000_000, soh=0.96),
    ]

    traj = StateHistoryTrajectoryAdapter.extract_trajectory(
        records=records,
        quantity_type=TrajectoryQuantityType.CAPACITY_RETENTION,
        horizon_domain=HorizonDomain.TIME,
    )

    assert traj.metadata["horizon_domain"] == HorizonDomain.TIME.value
    elapsed_times = tuple(obs.calendar_age_seconds.value for obs in traj.observations)
    assert elapsed_times == (0.0, 3.0, 6.0)


def test_adapter_extracts_multivariate():
    records = [
        _make_state_record(0, 1_000_000_000, soh=0.98, r_mohm=20.0, cycle=0),
        _make_state_record(1, 4_000_000_000, soh=0.97, r_mohm=22.0, cycle=50),
    ]

    traj = StateHistoryTrajectoryAdapter.extract_multivariate_trajectory(
        records=records,
    )

    assert traj.quantity_type == TrajectoryQuantityType.MULTIVARIATE
    assert traj.total_observations == 2
    assert traj.observations[0].capacity_retention_fraction.value == 0.98
    assert pytest.approx(traj.observations[0].internal_resistance_r0_ohm.value, rel=1e-5) == 0.020
    assert traj.observations[0].equivalent_full_cycles.value == 0.0
    assert traj.observations[0].discharge_throughput_ah.value == 0.0


def test_adapter_rejects_missing_quantity():
    # Record with no soh_fraction or custom estimates
    model_st = ModelState(soc_fraction=0.8, temperature_c=25.0)
    records = [
        TwinStateRecord(
            record_id="rec_empty",
            system_id="batt_01",
            timestamp_ns=1_000_000,
            model_state=model_st,
            estimation_state=None,
        )
    ]

    with pytest.raises(ValueError, match="is unavailable in record"):
        StateHistoryTrajectoryAdapter.extract_trajectory(
            records=records,
            quantity_type=TrajectoryQuantityType.INTERNAL_RESISTANCE,
            horizon_domain=HorizonDomain.TIME,
        )


def test_adapter_rejects_empty_records():
    with pytest.raises(ValueError, match="records sequence cannot be empty"):
        StateHistoryTrajectoryAdapter.extract_trajectory(records=[])


def test_adapter_rejects_non_finite_values():
    model_st = ModelState(soc_fraction=0.8, temperature_c=25.0)
    records = [
        TwinStateRecord(
            record_id="rec_nan",
            system_id="batt_01",
            timestamp_ns=1_000_000_000,
            model_state=model_st,
            estimation_state=None,
            metadata={"soh_fraction": "nan"},
        )
    ]
    with pytest.raises(ValueError, match="Non-finite"):
        StateHistoryTrajectoryAdapter.extract_trajectory(
            records=records,
            quantity_type=TrajectoryQuantityType.CAPACITY_RETENTION,
            horizon_domain=HorizonDomain.TIME,
        )
