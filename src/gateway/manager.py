"""Gateway Daemon Manager and Ingestion Dispatcher.

Orchestrates multiple external telemetry transport sources, applies bounded backpressure
queuing, publishes lifecycle events, and passes frames to TelemetryIngestService.
"""

import asyncio
import time
from typing import Any, Mapping, Optional
from src.events.base import EventBus, TwinEvent
from src.gateway.base import (
    BaseTelemetrySource,
    GatewayConfig,
    GatewayOverflowPolicy,
    GatewaySourceState,
    GatewaySourceStatus,
    RawTelemetryFrame,
)
from src.services.exceptions import ServiceError
from src.services.telemetry_service import TelemetryIngestService


class GatewayDaemonManager:
    """Edge Telemetry Gateway Daemon Manager.

    Coordinates asynchronous telemetry sources (Serial, CAN, TCP, UDP), manages bounded
    buffering with explicit overflow policies, publishes operational events to the event bus,
    and feeds validated raw observations into the TelemetryIngestService.
    """

    def __init__(
        self,
        config: Optional[GatewayConfig] = None,
        telemetry_service: Optional[TelemetryIngestService] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.config = config or GatewayConfig()
        self.telemetry_service = telemetry_service
        self.event_bus = event_bus

        self._sources: dict[str, BaseTelemetrySource] = {}
        self._queue: asyncio.Queue[RawTelemetryFrame] = asyncio.Queue(maxsize=self.config.max_queue_size)
        self._running = False
        self._listener_tasks: list[asyncio.Task[None]] = []
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._total_frames_enqueued = 0
        self._total_frames_dropped = 0
        self._total_frames_processed = 0

    @property
    def is_running(self) -> bool:
        """True if gateway manager daemon is active."""
        return self._running

    @property
    def queue_depth(self) -> int:
        """Current number of pending frames in the queue."""
        return self._queue.qsize()

    def register_source(self, source: BaseTelemetrySource) -> None:
        """Registers a telemetry source with the gateway manager."""
        if source.source_id in self._sources:
            raise ValueError(f"Source with id '{source.source_id}' is already registered.")
        self._sources[source.source_id] = source

    def unregister_source(self, source_id: str) -> Optional[BaseTelemetrySource]:
        """Removes a registered telemetry source."""
        return self._sources.pop(source_id, None)

    def get_source(self, source_id: str) -> Optional[BaseTelemetrySource]:
        """Retrieves a source by its identifier."""
        return self._sources.get(source_id)

    async def start(self) -> None:
        """Starts all registered sources and daemon ingestion workers."""
        if self._running:
            return

        self._running = True

        # Publish Gateway Started Event
        self._publish_event(
            event_type="gateway.started",
            payload={"sources_count": len(self._sources), "max_queue_size": self.config.max_queue_size},
        )

        # 1. Start all sources and spawn per-source listener tasks
        for source in self._sources.values():
            await source.start()
            task = asyncio.create_task(self._run_source_listener(source), name=f"gw_listener_{source.source_id}")
            self._listener_tasks.append(task)

        # 2. Spawn consumer worker tasks
        for i in range(self.config.worker_concurrency):
            task = asyncio.create_task(self._run_ingestion_worker(), name=f"gw_worker_{i}")
            self._worker_tasks.append(task)

    async def stop(self) -> None:
        """Gracefully shuts down all sources and workers."""
        if not self._running:
            return

        self._running = False

        # Cancel listener tasks
        for task in self._listener_tasks:
            task.cancel()
        if self._listener_tasks:
            await asyncio.gather(*self._listener_tasks, return_exceptions=True)
        self._listener_tasks.clear()

        # Stop all sources
        for source in self._sources.values():
            try:
                await source.stop()
            except Exception:
                pass

        # Cancel worker tasks
        for task in self._worker_tasks:
            task.cancel()
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()

        # Publish Gateway Stopped Event
        self._publish_event(
            event_type="gateway.stopped",
            payload={
                "frames_processed": self._total_frames_processed,
                "frames_dropped": self._total_frames_dropped,
            },
        )

    async def enqueue_frame(self, frame: RawTelemetryFrame) -> bool:
        """Pushes a raw frame to the bounded queue respecting the overflow policy."""
        if not self._running:
            return False

        if self._queue.full():
            if self.config.overflow_policy == GatewayOverflowPolicy.DROP_OLDEST:
                try:
                    dropped = self._queue.get_nowait()
                    self._total_frames_dropped += 1
                    self._publish_event(
                        event_type="gateway.frame_dropped",
                        source_id=dropped.source_id,
                        payload={"reason": "queue_full_drop_oldest", "dropped_seq": dropped.sequence_number},
                    )
                except asyncio.QueueEmpty:
                    pass
                await self._queue.put(frame)
                self._total_frames_enqueued += 1
                return True

            elif self.config.overflow_policy == GatewayOverflowPolicy.DROP_NEWEST:
                self._total_frames_dropped += 1
                self._publish_event(
                    event_type="gateway.frame_dropped",
                    source_id=frame.source_id,
                    payload={"reason": "queue_full_drop_newest", "dropped_seq": frame.sequence_number},
                )
                return False

            elif self.config.overflow_policy == GatewayOverflowPolicy.BLOCK:
                await self._queue.put(frame)
                self._total_frames_enqueued += 1
                return True

        await self._queue.put(frame)
        self._total_frames_enqueued += 1
        return True

    async def _run_source_listener(self, source: BaseTelemetrySource) -> None:
        """Listener loop retrieving frames from a specific source."""
        prev_state = source.state

        while self._running:
            try:
                current_state = source.state
                if current_state != prev_state:
                    if current_state == GatewaySourceState.CONNECTED:
                        self._publish_event(
                            event_type="gateway.source_connected",
                            source_id=source.source_id,
                            payload={"transport": source.transport_type},
                        )
                    elif current_state in (GatewaySourceState.DISCONNECTED, GatewaySourceState.ERROR):
                        self._publish_event(
                            event_type="gateway.source_disconnected",
                            source_id=source.source_id,
                            payload={"transport": source.transport_type, "last_error": source.get_status().last_error},
                        )
                    prev_state = current_state

                frame = await source.read_frame()
                if frame is not None:
                    self._publish_event(
                        event_type="gateway.frame_received",
                        source_id=frame.source_id,
                        payload={
                            "seq": frame.sequence_number,
                            "transport": frame.transport_type,
                            "received_ns": frame.received_timestamp_ns,
                        },
                    )
                    await self.enqueue_frame(frame)
                else:
                    await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._publish_event(
                    event_type="gateway.transport_error",
                    source_id=source.source_id,
                    payload={"error": str(exc)},
                )
                await asyncio.sleep(0.5)

    async def _run_ingestion_worker(self) -> None:
        """Consumer worker loop processing frames from the bounded queue."""
        while self._running:
            try:
                frame = await self._queue.get()
                try:
                    if self.telemetry_service is not None:
                        # Feed raw payload into locked TelemetryIngestService
                        self.telemetry_service.ingest_raw(
                            system_id=frame.source_id,
                            raw_payload=frame.payload,
                            format_identifier=frame.format_identifier or "JSON",
                            headers={
                                "transport_type": frame.transport_type,
                                "device_id": frame.device_id or "",
                                "sequence_number": str(frame.sequence_number or ""),
                                "received_timestamp_ns": str(frame.received_timestamp_ns),
                            },
                        )
                    self._total_frames_processed += 1
                except ServiceError as exc:
                    self._publish_event(
                        event_type="gateway.ingest_error",
                        source_id=frame.source_id,
                        payload={"error": str(exc), "details": getattr(exc, "details", {})},
                    )
                except Exception as exc:
                    self._publish_event(
                        event_type="gateway.ingest_error",
                        source_id=frame.source_id,
                        payload={"error": str(exc)},
                    )
                finally:
                    self._queue.task_done()

            except asyncio.CancelledError:
                break

    def _publish_event(
        self,
        event_type: str,
        source_id: str = "gateway",
        payload: Optional[dict[str, Any]] = None,
    ) -> None:
        """Publishes operational lifecycle and telemetry events to DigitalTwinEventBus."""
        if self.event_bus is None:
            return
        try:
            event = TwinEvent(
                event_type=event_type,
                source_id=source_id,
                payload=payload or {},
            )
            self.event_bus.publish(event)
        except Exception:
            pass

    def get_status(self) -> dict[str, Any]:
        """Returns overall gateway manager operational status and all source metrics."""
        source_statuses = {
            sid: src.get_status().to_dict()
            for sid, src in self._sources.items()
        }
        return {
            "is_running": self._running,
            "sources_count": len(self._sources),
            "queue_depth": self.queue_depth,
            "max_queue_size": self.config.max_queue_size,
            "overflow_policy": self.config.overflow_policy.value,
            "total_enqueued": self._total_frames_enqueued,
            "total_processed": self._total_frames_processed,
            "total_dropped": self._total_frames_dropped,
            "sources": source_statuses,
        }
