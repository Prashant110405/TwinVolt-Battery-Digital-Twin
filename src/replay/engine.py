"""Deterministic Drive Cycle Replay Engine.

Executes sequential time-series and benchmark drive cycles through the DigitalTwinInstance runtime,
collecting co-simulation outputs, state records, and evaluating tracking accuracy metrics.
"""

from dataclasses import dataclass, field
import time
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from src.ingestion.adapters.csv_adapter import CSVTelemetryAdapter
from src.ingestion.pipeline import IngestionPipeline
from src.replay.evaluator import (
    TrackingMetricsEvaluator,
    TrackingMetricsReport,
)
from src.replay.exceptions import (
    InvalidProfileError,
    ReplayError,
    ReplayExecutionError,
)
from src.replay.profiles import DriveCycleProfile
from src.runtime.instance import DigitalTwinInstance
from src.runtime.synchronizer import TwinSyncOutput
from src.storage.base import TelemetryRepository, TwinStateRecord
from src.telemetry.snapshots import TelemetrySnapshot


@dataclass(frozen=True)
class ReplayConfig:
    """Configuration options governing a drive cycle replay execution."""

    evaluate_metrics: bool = True
    target_voltage_rmse_v: Optional[float] = None
    target_temp_rmse_c: Optional[float] = None
    target_soc_rmse: Optional[float] = None
    raise_on_error: bool = True
    auto_reset_instance: bool = True
    progress_callback: Optional[Callable[[int, int, TwinSyncOutput], None]] = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes replay config to dictionary."""
        return {
            "evaluate_metrics": self.evaluate_metrics,
            "target_voltage_rmse_v": self.target_voltage_rmse_v,
            "target_temp_rmse_c": self.target_temp_rmse_c,
            "target_soc_rmse": self.target_soc_rmse,
            "raise_on_error": self.raise_on_error,
            "auto_reset_instance": self.auto_reset_instance,
        }


@dataclass(frozen=True)
class ReplayResult:
    """Comprehensive result container summarizing a completed drive cycle replay run."""

    system_id: str
    profile_name: str
    total_samples: int
    executed_steps: int
    skipped_samples: int
    duration_seconds: float
    start_timestamp_ns: int
    end_timestamp_ns: int
    sync_outputs: tuple[TwinSyncOutput, ...] = field(default_factory=tuple)
    state_records: tuple[TwinStateRecord, ...] = field(default_factory=tuple)
    anomalies_detected: int = 0
    metrics_report: Optional[TrackingMetricsReport] = None
    is_passing: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serializes replay result to dictionary."""
        return {
            "system_id": self.system_id,
            "profile_name": self.profile_name,
            "total_samples": self.total_samples,
            "executed_steps": self.executed_steps,
            "skipped_samples": self.skipped_samples,
            "duration_seconds": self.duration_seconds,
            "start_timestamp_ns": self.start_timestamp_ns,
            "end_timestamp_ns": self.end_timestamp_ns,
            "anomalies_detected": self.anomalies_detected,
            "is_passing": self.is_passing,
            "metrics_report": self.metrics_report.to_dict() if self.metrics_report else None,
        }


class DriveCycleReplayEngine:
    """Deterministic Drive Cycle and Dataset Replay Execution Engine.

    Feeds time-series telemetry observations sequentially into the DigitalTwinInstance,
    collecting state histories and evaluating analytical tracking metrics.
    """

    def __init__(
        self,
        evaluator: Optional[TrackingMetricsEvaluator] = None,
    ) -> None:
        self._evaluator = evaluator or TrackingMetricsEvaluator()

    @property
    def evaluator(self) -> TrackingMetricsEvaluator:
        """Attached tracking metrics evaluator."""
        return self._evaluator

    def replay_snapshots(
        self,
        instance: DigitalTwinInstance,
        snapshots: Sequence[TelemetrySnapshot],
        config: Optional[ReplayConfig] = None,
        profile_name: str = "custom_snapshots",
    ) -> ReplayResult:
        """Replays an ordered sequence of TelemetrySnapshot instances through the DigitalTwinInstance.

        Args:
            instance: Active DigitalTwinInstance to execute replay against.
            snapshots: Ordered sequence of TelemetrySnapshot records.
            config: Replay configuration options.
            profile_name: Name of the replay profile or dataset.

        Returns:
            ReplayResult containing outputs, state history, and tracking metrics.

        Raises:
            ReplayExecutionError: If runtime step fails and config.raise_on_error is True.
        """
        if not isinstance(instance, DigitalTwinInstance):
            raise TypeError(f"Expected DigitalTwinInstance, got {type(instance).__name__}.")
        if not snapshots:
            raise InvalidProfileError(f"Cannot replay empty snapshot sequence for profile '{profile_name}'.")

        replay_cfg = config or ReplayConfig()

        if replay_cfg.auto_reset_instance:
            instance.reset()
            first_snap = snapshots[0]
            instance.initialize(
                initial_soc=first_snap.soc_fraction if first_snap.soc_fraction is not None else 1.0,
                initial_soh=first_snap.soh_fraction if first_snap.soh_fraction is not None else 1.0,
                temperature_c=(
                    first_snap.avg_cell_temperature_c
                    if first_snap.avg_cell_temperature_c is not None
                    else (first_snap.max_cell_temperature_c or 25.0)
                ),
            )

        sync_outputs: list[TwinSyncOutput] = []
        state_records: list[TwinStateRecord] = []
        total_samples = len(snapshots)
        executed_steps = 0
        skipped_samples = 0
        anomalies_detected = 0

        t_start_perf = time.perf_counter()
        start_ts_ns = snapshots[0].timestamp_ns
        end_ts_ns = snapshots[-1].timestamp_ns

        for idx, snap in enumerate(snapshots):
            try:
                sync_out = instance.step(snap)
                sync_outputs.append(sync_out)
                if instance.latest_state_record is not None:
                    state_records.append(instance.latest_state_record)

                executed_steps += 1

                # Check if anomalies were recorded in this step
                if sync_out.diagnostics.get("anomalies_count", 0) > 0:
                    anomalies_detected += sync_out.diagnostics["anomalies_count"]

                # Progress callback
                if replay_cfg.progress_callback is not None:
                    replay_cfg.progress_callback(idx + 1, total_samples, sync_out)

            except Exception as exc:
                if replay_cfg.raise_on_error:
                    raise ReplayExecutionError(
                        f"Replay failed at step {idx + 1}/{total_samples} (snap_id='{snap.snapshot_id}'): {exc}",
                        profile_name=profile_name,
                        details={"step_index": idx + 1, "snapshot_id": snap.snapshot_id},
                    ) from exc
                skipped_samples += 1

        duration_sec = time.perf_counter() - t_start_perf

        # Evaluate Tracking Accuracy Metrics
        metrics_report: Optional[TrackingMetricsReport] = None
        is_passing = True

        if replay_cfg.evaluate_metrics and sync_outputs:
            metrics_report = self._evaluator.evaluate_from_sync_outputs(
                sync_outputs=sync_outputs,
                system_id=instance.system_id,
                profile_name=profile_name,
                target_voltage_rmse_v=replay_cfg.target_voltage_rmse_v,
                target_temp_rmse_c=replay_cfg.target_temp_rmse_c,
                target_soc_rmse=replay_cfg.target_soc_rmse,
            )
            is_passing = metrics_report.is_passing

        return ReplayResult(
            system_id=instance.system_id,
            profile_name=profile_name,
            total_samples=total_samples,
            executed_steps=executed_steps,
            skipped_samples=skipped_samples,
            duration_seconds=duration_sec,
            start_timestamp_ns=start_ts_ns,
            end_timestamp_ns=end_ts_ns,
            sync_outputs=tuple(sync_outputs),
            state_records=tuple(state_records),
            anomalies_detected=instance.total_anomalies,
            metrics_report=metrics_report,
            is_passing=is_passing,
        )

    def replay_profile(
        self,
        instance: DigitalTwinInstance,
        profile: DriveCycleProfile,
        config: Optional[ReplayConfig] = None,
        sample_interval_s: Optional[float] = None,
    ) -> ReplayResult:
        """Materializes snapshots from a DriveCycleProfile and executes deterministic replay.

        Args:
            instance: Active DigitalTwinInstance.
            profile: DriveCycleProfile instance (WLTP, US06, Pulse, CC, DST).
            config: Replay configuration options.
            sample_interval_s: Optional resampling interval in seconds.

        Returns:
            ReplayResult.
        """
        if not isinstance(profile, DriveCycleProfile):
            raise TypeError(f"Expected DriveCycleProfile, got {type(profile).__name__}.")

        snapshots = profile.to_snapshots(
            system_id=instance.system_id,
            sample_interval_s=sample_interval_s,
        )

        return self.replay_snapshots(
            instance=instance,
            snapshots=snapshots,
            config=config,
            profile_name=profile.name,
        )

    def replay_from_repository(
        self,
        instance: DigitalTwinInstance,
        repository: TelemetryRepository,
        system_id: str,
        start_time_ns: Optional[int] = None,
        end_time_ns: Optional[int] = None,
        config: Optional[ReplayConfig] = None,
    ) -> ReplayResult:
        """Queries telemetry snapshots from a repository and executes deterministic replay.

        Args:
            instance: Active DigitalTwinInstance.
            repository: TelemetryRepository instance.
            system_id: Target battery system identifier.
            start_time_ns: Optional starting timestamp filter.
            end_time_ns: Optional ending timestamp filter.
            config: Replay configuration options.

        Returns:
            ReplayResult.
        """
        snapshots = repository.query_by_time_range(
            system_id=system_id,
            start_time_ns=start_time_ns,
            end_time_ns=end_time_ns,
            descending=False,
        )

        if not snapshots:
            raise InvalidProfileError(
                f"No telemetry snapshots found in repository for system '{system_id}'."
            )

        return self.replay_snapshots(
            instance=instance,
            snapshots=snapshots,
            config=config,
            profile_name=f"repo_replay_{system_id}",
        )

    def replay_from_csv(
        self,
        instance: DigitalTwinInstance,
        csv_content_or_path: str,
        config: Optional[ReplayConfig] = None,
        system_id: Optional[str] = None,
        profile_name: str = "csv_dataset",
    ) -> ReplayResult:
        """Parses CSV time-series telemetry data and executes deterministic replay.

        Args:
            instance: Active DigitalTwinInstance.
            csv_content_or_path: Raw CSV text or path to CSV file.
            config: Replay configuration options.
            system_id: Optional system identifier override.
            profile_name: Dataset display name.

        Returns:
            ReplayResult.
        """
        target_sys = system_id or instance.system_id
        adapter = CSVTelemetryAdapter()

        lines = [line for line in csv_content_or_path.strip().splitlines() if line.strip()]
        if len(lines) <= 1:
            raise InvalidProfileError(f"CSV data for '{profile_name}' must contain headers and at least one data row.")

        # Check if first line is header
        header_line = lines[0]
        data_lines = lines[1:]

        snapshots: list[TelemetrySnapshot] = []
        for idx, line in enumerate(data_lines):
            csv_row = f"{header_line}\n{line}\n"
            snap = adapter.parse(csv_row)
            # Ensure consistent system_id
            if snap.system_id == "unknown_system":
                snap = TelemetrySnapshot(
                    snapshot_id=f"snap_csv_{idx:06d}",
                    system_id=target_sys,
                    timestamp_ns=snap.timestamp_ns,
                    pack_voltage_v=snap.pack_voltage_v,
                    pack_current_a=snap.pack_current_a,
                    pack_power_w=snap.pack_power_w,
                    ambient_temperature_c=snap.ambient_temperature_c,
                    avg_cell_temperature_c=snap.avg_cell_temperature_c,
                    soc_fraction=snap.soc_fraction,
                    soh_fraction=snap.soh_fraction,
                    quality=snap.quality,
                    metadata={"source": profile_name},
                )
            snapshots.append(snap)

        return self.replay_snapshots(
            instance=instance,
            snapshots=snapshots,
            config=config,
            profile_name=profile_name,
        )
