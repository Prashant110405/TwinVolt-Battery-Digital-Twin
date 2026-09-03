"""Digital Twin Resource Routes."""

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.dependencies import get_pack_service, get_twin_service
from src.api.schemas.telemetry import TelemetrySnapshotDTO
from src.api.schemas.twin import (
    TwinCreateDTO,
    TwinInitializeDTO,
    TwinStateRecordResponseDTO,
    TwinStatusResponseDTO,
    TwinStepRawDTO,
    TwinStepSnapshotDTO,
    TwinSyncOutputResponseDTO,
)
from src.estimators.coulomb_counter import CoulombCounter
from src.estimators.ekf import ExtendedKalmanFilter
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelMetadata
from src.runtime.config import RuntimeConfig
from src.runtime.instance import DigitalTwinInstance
from src.runtime.synchronizer import TwinSyncOutput
from src.services.pack_service import PackManagementService
from src.services.twin_service import TwinApplicationService
from src.storage.base import TwinStateRecord
from src.telemetry.snapshots import TelemetrySnapshot

router = APIRouter(prefix="/api/v1/twins", tags=["Digital Twins"])


def _serialize_twin_status(twin: DigitalTwinInstance) -> TwinStatusResponseDTO:
    """Helper transforming a DigitalTwinInstance into a status DTO."""
    curr_soc = None
    curr_v = None
    curr_t = None
    if twin.is_initialized:
        curr_soc = twin.current_model_state.soc_fraction
        curr_t = twin.current_model_state.temperature_c
    if twin.latest_sync_output is not None:
        curr_v = twin.latest_sync_output.model_output.terminal_voltage_v

    return TwinStatusResponseDTO(
        system_id=twin.system_id,
        pack_id=twin.battery_pack.pack_id,
        is_initialized=twin.is_initialized,
        total_steps=twin.total_steps,
        total_anomalies=twin.total_anomalies,
        current_soc=curr_soc,
        current_voltage_v=curr_v,
        current_temperature_c=curr_t,
        model_name=getattr(twin.battery_model, "name", "BatteryModel"),
    )


def _serialize_sync_output(out: TwinSyncOutput) -> TwinSyncOutputResponseDTO:
    """Helper transforming a TwinSyncOutput into a response DTO."""
    est_soc = (
        out.estimation_output.state.soc_fraction
        if out.estimation_output is not None
        else None
    )
    v_res = out.residuals.get("voltage_residual_v") if out.residuals else None
    t_res = out.residuals.get("temperature_residual_c") if out.residuals else None

    return TwinSyncOutputResponseDTO(
        step_index=out.step_index,
        timestamp_ns=out.timestamp_ns,
        dt_s=out.dt_s,
        terminal_voltage_v=out.model_output.terminal_voltage_v,
        simulated_soc=out.model_output.state.soc_fraction,
        estimated_soc=est_soc,
        temperature_c=out.model_output.state.temperature_c,
        voltage_residual_v=v_res,
        temperature_residual_c=t_res,
        anomalies_count=out.diagnostics.get("anomalies_count", 0),
        diagnostics=dict(out.diagnostics),
    )


def _serialize_state_record(rec: TwinStateRecord) -> TwinStateRecordResponseDTO:
    """Helper transforming a TwinStateRecord into a response DTO."""
    est_soc = (
        rec.estimation_state.soc_fraction
        if rec.estimation_state is not None
        else None
    )
    v_term = getattr(rec.model_state, "terminal_voltage_v", None)
    return TwinStateRecordResponseDTO(
        record_id=rec.record_id,
        system_id=rec.system_id,
        timestamp_ns=rec.timestamp_ns,
        terminal_voltage_v=v_term,
        soc_fraction=rec.model_state.soc_fraction,
        temperature_c=rec.model_state.temperature_c,
        estimated_soc=est_soc,
        residuals=dict(rec.residuals),
    )


@router.post(
    "",
    response_model=TwinStatusResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Assemble and Register a Digital Twin Instance",
)
async def create_twin(
    payload: TwinCreateDTO,
    pack_service: PackManagementService = Depends(get_pack_service),
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> TwinStatusResponseDTO:
    """Assembles constituent battery pack, simulation model, and state estimator into an active digital twin."""
    pack = pack_service.get_pack(payload.pack_id)

    # 1. Model Assembly
    v_min = pack.configuration.electrical_ratings.min_voltage_v
    v_max = pack.configuration.electrical_ratings.max_voltage_v
    nom_v = pack.configuration.electrical_ratings.nominal_voltage_v
    nom_cap = pack.configuration.electrical_ratings.nominal_capacity_ah

    ocv = LinearOCVModel(v_min_v=v_min, v_max_v=v_max)
    r0 = payload.series_resistance_r0_ohm if payload.series_resistance_r0_ohm is not None else 0.02

    rc_branches = ()
    if payload.r1_ohm is not None and payload.c1_farad is not None:
        rc_branches = (RCBranchParameters(resistance_r_ohm=payload.r1_ohm, capacitance_c_farad=payload.c1_farad),)

    params = GenericECMParameters(
        nominal_capacity_ah=nom_cap,
        nominal_voltage_v=nom_v,
        series_resistance_r0_ohm=r0,
        rc_branches=rc_branches,
    )
    meta = ModelMetadata(
        model_id=f"ecm_{payload.system_id}",
        name=f"ECM Twin ({payload.system_id})",
        paradigm="EQUIVALENT_CIRCUIT",
    )
    model = GenericECMModel(metadata=meta, parameters=params, ocv_model=ocv)

    # 2. State Estimator Assembly
    estimator = None
    if payload.estimator_type == "EKF":
        estimator = ExtendedKalmanFilter(
            estimator_id=f"ekf_{payload.system_id}",
            parameters=params,
            ocv_model=ocv,
        )
    elif payload.estimator_type == "COULOMB_COUNTER":
        estimator = CoulombCounter(
            estimator_id=f"cc_{payload.system_id}",
            nominal_capacity_ah=nom_cap,
            ocv_model=ocv,
        )

    # 3. Create and Register Twin
    cfg = RuntimeConfig(system_id=payload.system_id, default_dt_s=payload.default_dt_s)
    twin = twin_service.create_twin(
        system_id=payload.system_id,
        battery_pack=pack,
        battery_model=model,
        state_estimator=estimator,
        config=cfg,
    )

    if payload.auto_initialize:
        twin_service.initialize_twin(
            system_id=payload.system_id,
            initial_soc=payload.initial_soc,
            initial_soh=payload.initial_soh,
            temperature_c=payload.initial_temperature_c,
        )

    return _serialize_twin_status(twin)


@router.get(
    "",
    summary="List All Active Digital Twin Identifiers",
)
async def list_twins(
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> dict[str, list[str]]:
    """Returns a list of all active digital twin system identifiers."""
    return {"twins": list(twin_service.list_active_twins())}


@router.get(
    "/{system_id}",
    response_model=TwinStatusResponseDTO,
    summary="Get Digital Twin Status",
)
async def get_twin(
    system_id: str,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> TwinStatusResponseDTO:
    """Retrieves the current operational status of an active digital twin."""
    twin = twin_service.get_twin(system_id)
    return _serialize_twin_status(twin)


@router.post(
    "/{system_id}/initialize",
    response_model=TwinStatusResponseDTO,
    summary="Initialize Digital Twin",
)
async def initialize_twin(
    system_id: str,
    payload: TwinInitializeDTO,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> TwinStatusResponseDTO:
    """Initializes constituent models and state estimators with initial conditions."""
    twin = twin_service.initialize_twin(
        system_id=system_id,
        initial_soc=payload.initial_soc,
        initial_soh=payload.initial_soh,
        temperature_c=payload.temperature_c,
    )
    return _serialize_twin_status(twin)


@router.post(
    "/{system_id}/step",
    response_model=TwinSyncOutputResponseDTO,
    summary="Execute Synchronized Step with Canonical Telemetry",
)
async def step_twin(
    system_id: str,
    payload: TwinStepSnapshotDTO,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> TwinSyncOutputResponseDTO:
    """Executes a discrete synchronized co-simulation step for the digital twin."""
    snap = TelemetrySnapshot(
        snapshot_id=f"snap_{system_id}_{payload.sequence_number or 0}",
        system_id=system_id,
        timestamp_ns=payload.timestamp_ns,
        sequence_number=payload.sequence_number,
        pack_voltage_v=payload.pack_voltage_v,
        pack_current_a=payload.pack_current_a,
        pack_power_w=payload.pack_power_w,
        ambient_temperature_c=payload.ambient_temperature_c,
        avg_cell_temperature_c=payload.avg_cell_temperature_c,
        max_cell_temperature_c=payload.max_cell_temperature_c,
        soc_fraction=payload.soc_fraction,
    )
    sync_out = twin_service.step_twin(system_id, snap)
    return _serialize_sync_output(sync_out)


@router.post(
    "/{system_id}/step/raw",
    response_model=TwinSyncOutputResponseDTO,
    summary="Execute Synchronized Step with Raw External Telemetry",
)
async def step_raw_twin(
    system_id: str,
    payload: TwinStepRawDTO,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> TwinSyncOutputResponseDTO:
    """Parses raw CSV or JSON data and executes a synchronized step."""
    sync_out = twin_service.step_raw_twin(
        system_id=system_id,
        raw_payload=payload.raw_data,
        format_identifier=payload.format_identifier,
        headers=payload.headers,
    )
    return _serialize_sync_output(sync_out)


@router.get(
    "/{system_id}/state",
    response_model=TwinStateRecordResponseDTO,
    summary="Get Latest Digital Twin State Record",
)
async def get_latest_state(
    system_id: str,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> TwinStateRecordResponseDTO:
    """Retrieves the most recent persisted digital twin state record."""
    record = twin_service.get_latest_state(system_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No state records found for twin '{system_id}'.",
        )
    return _serialize_state_record(record)


@router.get(
    "/{system_id}/state/history",
    response_model=list[TwinStateRecordResponseDTO],
    summary="Query Digital Twin State History",
)
async def get_state_history(
    system_id: str,
    start_time_ns: Optional[int] = Query(None),
    end_time_ns: Optional[int] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=10000),
    descending: bool = Query(False),
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> list[TwinStateRecordResponseDTO]:
    """Queries time-range filtered digital twin state history records."""
    records = twin_service.get_state_history(
        system_id=system_id,
        start_time_ns=start_time_ns,
        end_time_ns=end_time_ns,
        limit=limit,
        descending=descending,
    )
    return [_serialize_state_record(r) for r in records]


@router.get(
    "/{system_id}/telemetry/history",
    response_model=list[TelemetrySnapshotDTO],
    summary="Query Telemetry History",
)
async def get_telemetry_history(
    system_id: str,
    start_time_ns: Optional[int] = Query(None),
    end_time_ns: Optional[int] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=10000),
    descending: bool = Query(False),
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> list[TelemetrySnapshotDTO]:
    """Queries time-range filtered telemetry observation snapshots."""
    snaps = twin_service.get_telemetry_history(
        system_id=system_id,
        start_time_ns=start_time_ns,
        end_time_ns=end_time_ns,
        limit=limit,
        descending=descending,
    )
    return [
        TelemetrySnapshotDTO(
            system_id=s.system_id,
            snapshot_id=s.snapshot_id,
            timestamp_ns=s.timestamp_ns,
            pack_voltage_v=s.pack_voltage_v,
            pack_current_a=s.pack_current_a,
            pack_power_w=s.pack_power_w,
            ambient_temperature_c=s.ambient_temperature_c,
            avg_cell_temperature_c=s.avg_cell_temperature_c,
            max_cell_temperature_c=s.max_cell_temperature_c,
            soc_fraction=s.soc_fraction,
            soh_fraction=s.soh_fraction,
        )
        for s in snaps
    ]


@router.post(
    "/{system_id}/reset",
    summary="Reset Digital Twin State",
)
async def reset_twin(
    system_id: str,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> dict[str, str]:
    """Resets internal state, estimator covariance, and diagnostics of an active digital twin."""
    twin_service.reset_twin(system_id)
    return {"status": "RESET", "system_id": system_id}


@router.delete(
    "/{system_id}",
    summary="Delete Digital Twin",
)
async def delete_twin(
    system_id: str,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> dict[str, Any]:
    """Unregisters and removes an active digital twin instance."""
    deleted = twin_service.delete_twin(system_id)
    return {"deleted": deleted, "system_id": system_id}


@router.get(
    "/{system_id}/health",
    summary="Query Battery State of Health (SOH) and Degradation Metrics",
)
async def get_twin_health(
    system_id: str,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> dict[str, Any]:
    """Returns detailed State of Health (SOH), capacity fade, and cumulative throughput metrics."""
    twin = twin_service.get_twin(system_id)
    health = twin_service.get_twin_health(system_id)

    if health is not None:
        return health.to_dict()

    # Default initial uncalibrated health state if not yet stepped
    nom_cap = twin.battery_pack.nominal_capacity_ah
    return {
        "timestamp_ns": 0,
        "system_id": system_id,
        "soh_capacity_fraction": 1.0,
        "soh_resistance_fraction": 1.0,
        "soh_unified_fraction": 1.0,
        "cumulative_throughput_ah": 0.0,
        "cumulative_energy_throughput_wh": 0.0,
        "equivalent_full_cycles": 0.0,
        "estimated_capacity_ah": nom_cap,
        "estimated_series_resistance_ohm": None,
        "capacity_fade_fraction": 0.0,
        "resistance_growth_fraction": 0.0,
        "calibration_status": "UNCALIBRATED_PARAMETRIC_MODEL",
        "metadata": {"status": "INITIAL_UNSTEPPED"},
    }


@router.get(
    "/{system_id}/calibration",
    summary="Query Online Identified Model Parameters and Calibration Status",
)
async def get_twin_calibration(
    system_id: str,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> dict[str, Any]:
    """Returns online identified parameters (R0, R1, C1, tau1), covariance metrics, and gating status."""
    twin = twin_service.get_twin(system_id)
    cal = twin_service.get_twin_calibration(system_id)

    if cal is not None:
        return cal.to_dict()

    # Default initial state from model parameters if not yet stepped
    nom_r0 = 0.025
    nom_r1 = None
    nom_c1 = None
    nom_tau1 = None

    if hasattr(twin.battery_model, "ecm_parameters"):
        ecm_p = twin.battery_model.ecm_parameters
        nom_r0 = ecm_p.series_resistance_r0_ohm
        if ecm_p.rc_branches:
            b0 = ecm_p.rc_branches[0]
            nom_r1 = b0.resistance_r_ohm
            nom_c1 = b0.capacitance_c_farad
            nom_tau1 = b0.time_constant_tau_s

    return {
        "timestamp_ns": 0,
        "system_id": system_id,
        "r0_ohm": round(nom_r0, 6),
        "r1_ohm": round(nom_r1, 6) if nom_r1 is not None else None,
        "c1_farad": round(nom_c1, 4) if nom_c1 is not None else None,
        "tau1_s": round(nom_tau1, 4) if nom_tau1 is not None else None,
        "r0_covariance": 0.0,
        "coefficient_covariance_diagonal": [0.0, 0.0, 0.0],
        "sample_count": 0,
        "classification": "CONFIGURED_NOMINAL",
        "gating_status": "UNSTEPPED",
        "metadata": {"status": "INITIAL_NOMINAL"},
    }


@router.get(
    "/{system_id}/validation",
    summary="Query Battery Behavioral Validation and Model Residual Status",
)
async def get_twin_validation(
    system_id: str,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> dict[str, Any]:
    """Returns active validation window status, running residual metrics, and latest completed window."""
    twin = twin_service.get_twin(system_id)
    report = twin_service.get_twin_validation(system_id)

    if report is not None:
        return report.to_dict()

    # Default initial unstepped validation state
    return {
        "system_id": system_id,
        "timestamp_ns": 0,
        "active_window": {
            "window_id": f"win_{system_id}_0",
            "system_id": system_id,
            "start_timestamp_ns": 0,
            "end_timestamp_ns": 0,
            "duration_s": 0.0,
            "sample_count": 0,
            "state": "INSUFFICIENT_DATA",
            "voltage_metrics": None,
            "temperature_metrics": None,
            "soc_discrepancy_metrics": None,
            "current_consistency_max_a": None,
            "power_consistency_max_w": None,
            "parameter_evidence": None,
            "data_quality_flags": [],
            "diagnostics": {"status": "INITIAL_UNSTEPPED"},
        },
        "latest_completed_window": None,
        "parameter_evidence": None,
    }


@router.get(
    "/{system_id}/validation/history",
    summary="Query Completed Battery Validation Window Reports History",
)
async def get_twin_validation_history(
    system_id: str,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> list[dict[str, Any]]:
    """Returns historical completed validation window reports from the in-memory ring buffer."""
    twin = twin_service.get_twin(system_id)
    history = twin_service.get_twin_validation_history(system_id)
    return [w.to_dict() for w in history]


@router.get(
    "/{system_id}/validation/parameters",
    summary="Query Multi-Dimensional Parameter Validation Evidence",
)
async def get_twin_parameter_validation(
    system_id: str,
    twin_service: TwinApplicationService = Depends(get_twin_service),
) -> dict[str, Any]:
    """Returns latest multi-dimensional parameter validation evidence evaluating identified parameters."""
    twin = twin_service.get_twin(system_id)
    evidence = twin_service.get_twin_parameter_validation(system_id)

    if evidence is not None:
        return evidence.to_dict()

    return {
        "timestamp_ns": 0,
        "system_id": system_id,
        "tier": "EVIDENCE_REJECTED",
        "bounds_satisfied": False,
        "excitation_sufficient": False,
        "covariance_acceptable": False,
        "cross_window_drift_fraction": None,
        "prospective_rmse_v": None,
        "nominal_rmse_v": None,
        "delta_rmse_v": None,
        "evaluated_sample_count": 0,
        "diagnostics": {"status": "NO_PARAMETER_EVIDENCE_AVAILABLE"},
    }
