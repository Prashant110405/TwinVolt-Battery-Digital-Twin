"""WebSocket Route Handlers for Real-Time Streaming Telemetry and Twin State."""

import json
from typing import Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from src.api.websocket.dependencies import get_websocket_manager
from src.api.websocket.manager import WebSocketConnectionManager
from src.api.websocket.schemas import (
    WSErrorMessage,
    WSPingMessage,
    WSPongMessage,
    WSSubscribeMessage,
    WSTelemetryAckMessage,
    WSTelemetryIngestMessage,
    WSTwinStateMessage,
    WSUnsubscribeMessage,
)
from src.domain.exceptions import TwinVoltDomainError
from src.runtime.synchronizer import TwinSyncOutput
from src.services.exceptions import (
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidServiceOperationError,
    PackNotFoundError,
    ServiceError,
    TwinNotFoundError,
)
from src.services.telemetry_service import TelemetryIngestService
from src.services.twin_service import TwinApplicationService
from src.telemetry.snapshots import TelemetrySnapshot

router = APIRouter(tags=["WebSocket Real-Time Streaming"])


def _serialize_twin_sync_to_ws_state(system_id: str, out: TwinSyncOutput) -> WSTwinStateMessage:
    """Helper transforming a TwinSyncOutput into a WebSocket state broadcast message."""
    est_soc = (
        out.estimation_output.state.soc_fraction
        if out.estimation_output is not None
        else None
    )
    v_res = out.residuals.get("voltage_residual_v") if out.residuals else None
    t_res = out.residuals.get("temperature_residual_c") if out.residuals else None

    soh = None
    if out.telemetry and out.telemetry.soh_fraction is not None:
        soh = out.telemetry.soh_fraction
    elif "soh_unified_fraction" in out.diagnostics:
        soh = out.diagnostics["soh_unified_fraction"]

    source = None
    if out.telemetry and out.telemetry.metadata:
        source = out.telemetry.metadata.get("source")

    # Keep the physical measurements available to the existing dashboard UI.
    diagnostics = dict(out.diagnostics)
    if out.telemetry is not None:
        diagnostics["telemetry_voltage_v"] = out.telemetry.pack_voltage_v
        diagnostics["telemetry_current_a"] = out.telemetry.pack_current_a
        diagnostics["telemetry_temperature_c"] = (
            out.telemetry.avg_cell_temperature_c
            if out.telemetry.avg_cell_temperature_c is not None
            else out.telemetry.ambient_temperature_c
        )
        if out.telemetry.soc_fraction is not None:
            diagnostics["telemetry_soc_fraction"] = out.telemetry.soc_fraction
        if out.telemetry.soh_fraction is not None:
            diagnostics["telemetry_soh_fraction"] = out.telemetry.soh_fraction
        if out.telemetry.metadata:
            diagnostics["battery_status"] = out.telemetry.metadata.get("battery_status")

    return WSTwinStateMessage(
        system_id=system_id,
        step_index=out.step_index,
        timestamp_ns=out.timestamp_ns,
        dt_s=out.dt_s,
        terminal_voltage_v=out.model_output.terminal_voltage_v,
        simulated_soc=out.model_output.state.soc_fraction,
        estimated_soc=est_soc,
        soh_unified_fraction=soh,
        source=source,
        temperature_c=out.model_output.state.temperature_c,
        voltage_residual_v=v_res,
        temperature_residual_c=t_res,
        anomalies_count=out.diagnostics.get("anomalies_count", 0),
        diagnostics=diagnostics,
    )


async def _handle_incoming_message(
    data: dict[str, Any],
    client_id: str,
    default_system_id: Optional[str],
    manager: WebSocketConnectionManager,
    telemetry_service: TelemetryIngestService,
    twin_service: TwinApplicationService,
) -> None:
    """Processes a single validated WebSocket client message."""
    msg_type = str(data.get("type", "")).lower()

    # 1. Heartbeat Ping
    if msg_type == "ping":
        await manager.send_personal_message(client_id, WSPongMessage())
        return

    # 2. Subscribe Command
    if msg_type == "subscribe":
        sub_msg = WSSubscribeMessage(**data)
        if not twin_service.exists(sub_msg.system_id):
            await manager.send_personal_message(
                client_id,
                WSErrorMessage(
                    code="TWIN_NOT_FOUND",
                    message=f"Digital twin '{sub_msg.system_id}' does not exist.",
                    details={"system_id": sub_msg.system_id},
                ),
            )
            return

        await manager.subscribe(client_id, sub_msg.system_id)
        await manager.send_personal_message(
            client_id,
            {"type": "subscribed", "system_id": sub_msg.system_id},
        )
        if twin_service.exists(sub_msg.system_id):
            twin = twin_service.get_twin(sub_msg.system_id)
            if twin.latest_sync_output is not None:
                state_broadcast = _serialize_twin_sync_to_ws_state(sub_msg.system_id, twin.latest_sync_output)
                await manager.send_personal_message(client_id, state_broadcast)
        return

    # 3. Unsubscribe Command
    if msg_type == "unsubscribe":
        unsub_msg = WSUnsubscribeMessage(**data)
        await manager.unsubscribe(client_id, unsub_msg.system_id)
        await manager.send_personal_message(
            client_id,
            {"type": "unsubscribed", "system_id": unsub_msg.system_id},
        )
        return

    # 4. Telemetry Ingestion Command
    if msg_type == "telemetry_ingest":
        target_sys_id = data.get("system_id") or default_system_id
        if not target_sys_id:
            await manager.send_personal_message(
                client_id,
                WSErrorMessage(
                    code="INVALID_PAYLOAD",
                    message="Missing 'system_id' for telemetry ingestion.",
                ),
            )
            return

        payload_dict = dict(data)
        payload_dict["system_id"] = target_sys_id
        ingest_msg = WSTelemetryIngestMessage(**payload_dict)

        sync_out: Optional[TwinSyncOutput] = None
        if ingest_msg.raw_data is not None:
            sync_out = telemetry_service.ingest_raw(
                system_id=ingest_msg.system_id,
                raw_payload=ingest_msg.raw_data,
                format_identifier=ingest_msg.format_identifier,
                headers=ingest_msg.headers,
            )
        else:
            import time
            meta = dict(ingest_msg.metadata or {})
            if ingest_msg.source and "source" not in meta:
                meta["source"] = ingest_msg.source

            snap = TelemetrySnapshot(
                snapshot_id=f"ws_snap_{ingest_msg.system_id}_{ingest_msg.sequence_number or 0}",
                system_id=ingest_msg.system_id,
                timestamp_ns=ingest_msg.timestamp_ns or time.time_ns(),
                sequence_number=ingest_msg.sequence_number,
                pack_voltage_v=ingest_msg.pack_voltage_v,
                pack_current_a=ingest_msg.pack_current_a,
                pack_power_w=ingest_msg.pack_power_w,
                ambient_temperature_c=ingest_msg.ambient_temperature_c,
                avg_cell_temperature_c=ingest_msg.avg_cell_temperature_c,
                max_cell_temperature_c=ingest_msg.max_cell_temperature_c,
                soc_fraction=ingest_msg.soc_fraction,
                soh_fraction=ingest_msg.soh_fraction,
                metadata=meta,
            )
            sync_out = telemetry_service.ingest_snapshot(snap)

        # Send ACK to the sending client
        ack = WSTelemetryAckMessage(
            system_id=ingest_msg.system_id,
            status="ACK",
            stepped_twin=sync_out is not None,
            step_index=sync_out.step_index if sync_out is not None else None,
        )
        await manager.send_personal_message(client_id, ack)

        # Broadcast state update to all twin subscribers
        if sync_out is not None:
            state_broadcast = _serialize_twin_sync_to_ws_state(ingest_msg.system_id, sync_out)
            await manager.broadcast_to_twin(ingest_msg.system_id, state_broadcast)
        return

    # 5. Unsupported message type
    await manager.send_personal_message(
        client_id,
        WSErrorMessage(
            code="UNSUPPORTED_MESSAGE_TYPE",
            message=f"Unsupported message type '{msg_type}'.",
            details={"supported_types": ["ping", "subscribe", "unsubscribe", "telemetry_ingest"]},
        ),
    )


async def _run_websocket_session(
    websocket: WebSocket,
    default_system_id: Optional[str] = None,
) -> None:
    """Coordinates a persistent WebSocket session lifecycle with exception safety."""
    manager = get_websocket_manager(websocket)
    services = getattr(websocket.app.state, "services", None)
    telemetry_service = services.telemetry_service if services else TelemetryIngestService()
    twin_service = services.twin_service if services else TwinApplicationService()

    client_id = await manager.connect(websocket, system_id=default_system_id)
    if default_system_id and twin_service.exists(default_system_id):
        twin = twin_service.get_twin(default_system_id)
        if twin.latest_sync_output is not None:
            initial_state = _serialize_twin_sync_to_ws_state(default_system_id, twin.latest_sync_output)
            await manager.send_personal_message(client_id, initial_state)

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                data = json.loads(raw_text)
                if not isinstance(data, dict):
                    await manager.send_personal_message(
                        client_id,
                        WSErrorMessage(
                            code="MALFORMED_JSON",
                            message="WebSocket message must be a JSON object.",
                        ),
                    )
                    continue

                await _handle_incoming_message(
                    data=data,
                    client_id=client_id,
                    default_system_id=default_system_id,
                    manager=manager,
                    telemetry_service=telemetry_service,
                    twin_service=twin_service,
                )

            except json.JSONDecodeError as exc:
                await manager.send_personal_message(
                    client_id,
                    WSErrorMessage(
                        code="MALFORMED_JSON",
                        message=f"Failed to parse JSON message: {exc}",
                    ),
                )
            except ValidationError as exc:
                await manager.send_personal_message(
                    client_id,
                    WSErrorMessage(
                        code="VALIDATION_ERROR",
                        message="Invalid schema payload.",
                        details={"errors": exc.errors()},
                    ),
                )
            except TwinNotFoundError as exc:
                await manager.send_personal_message(
                    client_id,
                    WSErrorMessage(
                        code="TWIN_NOT_FOUND",
                        message=str(exc),
                        details=exc.details,
                    ),
                )
            except PackNotFoundError as exc:
                await manager.send_personal_message(
                    client_id,
                    WSErrorMessage(
                        code="PACK_NOT_FOUND",
                        message=str(exc),
                        details=exc.details,
                    ),
                )
            except DuplicateEntityError as exc:
                await manager.send_personal_message(
                    client_id,
                    WSErrorMessage(
                        code="DUPLICATE_ENTITY",
                        message=str(exc),
                        details=exc.details,
                    ),
                )
            except InvalidServiceOperationError as exc:
                await manager.send_personal_message(
                    client_id,
                    WSErrorMessage(
                        code="INVALID_OPERATION",
                        message=str(exc),
                        details=exc.details,
                    ),
                )
            except ServiceError as exc:
                await manager.send_personal_message(
                    client_id,
                    WSErrorMessage(
                        code=exc.__class__.__name__,
                        message=str(exc),
                        details=exc.details,
                    ),
                )
            except TwinVoltDomainError as exc:
                await manager.send_personal_message(
                    client_id,
                    WSErrorMessage(
                        code=exc.__class__.__name__,
                        message=str(exc),
                        details=getattr(exc, "details", {}),
                    ),
                )

    except WebSocketDisconnect:
        await manager.disconnect(client_id)
    except Exception:
        await manager.disconnect(client_id)


@router.websocket("/api/v1/ws/twins/{system_id}")
async def websocket_twin_endpoint(
    websocket: WebSocket,
    system_id: str,
) -> None:
    """Dedicated WebSocket streaming endpoint for a specific digital twin instance."""
    await _run_websocket_session(websocket, default_system_id=system_id)


@router.websocket("/api/v1/ws")
async def websocket_gateway_endpoint(
    websocket: WebSocket,
) -> None:
    """Multiplexed WebSocket streaming gateway endpoint."""
    await _run_websocket_session(websocket, default_system_id=None)
