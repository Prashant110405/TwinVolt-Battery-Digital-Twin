"""Drive-Cycle Replay and Tracking Evaluation API Routes."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.dependencies import get_replay_service
from src.api.schemas.replay import (
    ReplayCSVRequestDTO,
    ReplayProfileRequestDTO,
    ReplayResponseDTO,
    SignalMetricsDTO,
)
from src.replay.engine import ReplayConfig, ReplayResult
from src.replay.profiles import (
    create_constant_current_profile,
    create_dst_profile,
    create_pulse_discharge_profile,
    create_us06_profile,
    create_wltp_class3_profile,
)
from src.services.exceptions import InvalidServiceOperationError
from src.services.replay_service import ReplayService

router = APIRouter(prefix="/api/v1/replay", tags=["Drive-Cycle Replay"])


def _serialize_replay_result(res: ReplayResult) -> ReplayResponseDTO:
    """Helper transforming a ReplayResult into a response DTO."""
    signals_map: dict[str, SignalMetricsDTO] = {}
    if res.metrics_report is not None:
        for name, sig in res.metrics_report.signals.items():
            signals_map[name] = SignalMetricsDTO(
                signal_name=sig.signal_name,
                sample_count=sig.sample_count,
                rmse=sig.rmse,
                mae=sig.mae,
                max_error=sig.max_error,
                mean_bias_error=sig.mean_bias_error,
                r_squared=sig.r_squared,
                nrmse=sig.nrmse,
            )

    return ReplayResponseDTO(
        system_id=res.system_id,
        profile_name=res.profile_name,
        total_samples=res.total_samples,
        executed_steps=res.executed_steps,
        skipped_samples=res.skipped_samples,
        duration_seconds=res.duration_seconds,
        is_passing=res.is_passing,
        anomalies_detected=res.anomalies_detected,
        signals=signals_map,
    )


@router.post(
    "/{system_id}/profile",
    response_model=ReplayResponseDTO,
    summary="Execute Benchmark Drive-Cycle Profile Replay",
)
async def replay_profile(
    system_id: str,
    payload: ReplayProfileRequestDTO,
    replay_service: ReplayService = Depends(get_replay_service),
) -> ReplayResponseDTO:
    """Executes a standard driving schedule (WLTP, US06, DST, Pulse, CC) against a digital twin."""
    ptype = payload.profile_type.upper()

    if ptype == "WLTP":
        profile = create_wltp_class3_profile(
            peak_current_a=payload.peak_current_a or 50.0,
            time_scale_s=payload.duration_s or 1800.0,
            dt_s=payload.dt_s,
        )
    elif ptype == "US06":
        profile = create_us06_profile(
            peak_current_a=payload.peak_current_a or 80.0,
            time_scale_s=payload.duration_s or 600.0,
            dt_s=payload.dt_s,
        )
    elif ptype == "DST":
        profile = create_dst_profile(
            peak_discharge_a=payload.peak_current_a or 40.0,
            cycles=payload.cycles or 3,
            dt_s=payload.dt_s,
        )
    elif ptype == "PULSE":
        profile = create_pulse_discharge_profile(
            pulse_current_a=payload.peak_current_a or 10.0,
            cycles=payload.cycles or 5,
            dt_s=payload.dt_s,
        )
    elif ptype in ("CONSTANT_CURRENT", "CC"):
        profile = create_constant_current_profile(
            duration_s=payload.duration_s or 100.0,
            current_a=payload.peak_current_a or 5.0,
            dt_s=payload.dt_s,
        )
    else:
        raise InvalidServiceOperationError(
            f"Unsupported profile_type '{payload.profile_type}'. Supported: WLTP, US06, DST, PULSE, CONSTANT_CURRENT.",
            service_name="ReplayService",
        )

    cfg = ReplayConfig(
        evaluate_metrics=payload.evaluate_metrics,
        target_voltage_rmse_v=payload.target_voltage_rmse_v,
    )
    result = replay_service.replay_profile(system_id=system_id, profile=profile, config=cfg)
    return _serialize_replay_result(result)


@router.post(
    "/{system_id}/csv",
    response_model=ReplayResponseDTO,
    summary="Execute Drive-Cycle Replay from CSV Dataset",
)
async def replay_csv(
    system_id: str,
    payload: ReplayCSVRequestDTO,
    replay_service: ReplayService = Depends(get_replay_service),
) -> ReplayResponseDTO:
    """Replays raw CSV time-series telemetry data through an active digital twin."""
    cfg = ReplayConfig(
        evaluate_metrics=payload.evaluate_metrics,
        target_voltage_rmse_v=payload.target_voltage_rmse_v,
    )
    result = replay_service.replay_csv(
        system_id=system_id,
        csv_data=payload.csv_data,
        config=cfg,
        profile_name=payload.profile_name,
    )
    return _serialize_replay_result(result)


@router.post(
    "/{system_id}/repository",
    response_model=ReplayResponseDTO,
    summary="Execute Replay from Repository Snapshots",
)
async def replay_repository(
    system_id: str,
    start_time_ns: Optional[int] = Query(None),
    end_time_ns: Optional[int] = Query(None),
    evaluate_metrics: bool = Query(True),
    target_voltage_rmse_v: Optional[float] = Query(None),
    replay_service: ReplayService = Depends(get_replay_service),
) -> ReplayResponseDTO:
    """Replays stored telemetry snapshots from the repository against the digital twin."""
    cfg = ReplayConfig(
        evaluate_metrics=evaluate_metrics,
        target_voltage_rmse_v=target_voltage_rmse_v,
    )
    result = replay_service.replay_repository_data(
        system_id=system_id,
        start_time_ns=start_time_ns,
        end_time_ns=end_time_ns,
        config=cfg,
    )
    return _serialize_replay_result(result)


@router.get(
    "/{system_id}/latest",
    response_model=ReplayResponseDTO,
    summary="Get Latest Replay Result and Tracking Accuracy",
)
async def get_latest_replay(
    system_id: str,
    replay_service: ReplayService = Depends(get_replay_service),
) -> ReplayResponseDTO:
    """Retrieves the most recent replay result and tracking error evaluation report."""
    result = replay_service.get_last_replay_result(system_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No replay results found for system '{system_id}'.",
        )
    return _serialize_replay_result(result)
