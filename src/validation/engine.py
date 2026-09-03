"""Digital Twin Behavioral Validation and Residual Analysis Engine.

Coordinates signal alignment auditing, streaming statistical error accumulation,
isolated prospective parameter simulation, windowed state classification, and
multi-dimensional parameter evidence evaluation.
"""

from collections import deque
from typing import Any, Mapping, Optional

from src.calibration.types import IdentifiedParameterSet
from src.runtime.synchronizer import TwinSyncOutput
from src.telemetry.snapshots import TelemetrySnapshot
from src.validation.auditor import SignalAlignmentAuditor
from src.validation.parameter_validator import ParameterValidationEvaluator
from src.validation.residuals import ResidualStatisticsAccumulator
from src.validation.shadow import ProspectiveECMBranchSimulator
from src.validation.types import (
    ModelValidationReport,
    ModelValidationState,
    ParameterValidationEvidence,
    SignalProvenance,
    ValidationConfig,
    ValidationWindowReport,
)


class ModelValidationEngine:
    """Real-Time Digital Twin Behavioral Validation and Residual Tracking Engine."""

    def __init__(
        self,
        system_id: str,
        config: Optional[ValidationConfig] = None,
        history_capacity: int = 50,
    ) -> None:
        self._system_id = system_id
        self._config = config or ValidationConfig()
        self._auditor = SignalAlignmentAuditor(config=self._config)
        self._shadow_sim = ProspectiveECMBranchSimulator()
        self._param_validator = ParameterValidationEvaluator(config=self._config)

        # Streaming Residual Accumulators
        self._nominal_voltage_acc = ResidualStatisticsAccumulator()
        self._prospective_voltage_acc = ResidualStatisticsAccumulator()
        self._temp_acc = ResidualStatisticsAccumulator()
        self._soc_discrepancy_acc = ResidualStatisticsAccumulator()

        # Electrical Consistency Trackers
        self._max_current_consistency_a: Optional[float] = None
        self._max_power_consistency_w: Optional[float] = None

        # Current variance tracking over window
        self._current_mean: float = 0.0
        self._current_m2: float = 0.0

        # Window Lifecycle
        self._window_index: int = 1
        self._window_start_ts_ns: Optional[int] = None
        self._window_last_ts_ns: Optional[int] = None
        self._window_sample_count: int = 0
        self._window_flags: set[str] = set()

        # History & Latest Report
        self._history: deque[ValidationWindowReport] = deque(maxlen=history_capacity)
        self._latest_report: Optional[ModelValidationReport] = None

    @property
    def system_id(self) -> str:
        """System identifier."""
        return self._system_id

    @property
    def config(self) -> ValidationConfig:
        """Attached validation configuration."""
        return self._config

    @property
    def latest_report(self) -> Optional[ModelValidationReport]:
        """Most recent ModelValidationReport."""
        return self._latest_report

    @property
    def validation_history(self) -> tuple[ValidationWindowReport, ...]:
        """Immutable sequence of completed validation window reports."""
        return tuple(self._history)

    def update(
        self,
        snapshot: TelemetrySnapshot,
        sync_output: TwinSyncOutput,
        latest_identified_params: Optional[IdentifiedParameterSet] = None,
        dt_s: Optional[float] = None,
    ) -> ModelValidationReport:
        """Executes a single validation step across incoming observations and model outputs.

        Args:
            snapshot: Incoming TelemetrySnapshot.
            sync_output: Co-simulation sync output containing nominal model predictions.
            latest_identified_params: Optional candidate identified parameter set from Level 5.2.
            dt_s: Effective discrete step interval in seconds.

        Returns:
            Updated ModelValidationReport.
        """
        # 1. Audit Signal Alignment & Timestamps
        audit = self._auditor.audit_step(snapshot=snapshot, dt_s=dt_s)
        effective_dt = audit.effective_dt_s

        # Handle Telemetry Gap Interruption
        if audit.is_gap:
            self._seal_window(state_override=ModelValidationState.DATA_QUALITY_FAILED, reason="INTERRUPTED_BY_GAP")
            self._reset_accumulators()
            self._shadow_sim.reset()

        if audit.data_quality_flags:
            self._window_flags.update(audit.data_quality_flags)

        # If step is invalid (duplicate or retrograde timestamp, invalid sensor), do not ingest
        if not audit.is_valid_step:
            return self._build_active_report(latest_identified_params)

        # 2. Initialize Window Start
        if self._window_start_ts_ns is None:
            self._window_start_ts_ns = snapshot.timestamp_ns
        self._window_last_ts_ns = snapshot.timestamp_ns
        self._window_sample_count += 1

        v_meas = snapshot.pack_voltage_v
        i_meas = snapshot.pack_current_a
        v_sim = sync_output.model_output.terminal_voltage_v
        v_oc = sync_output.model_output.open_circuit_voltage_v

        # 3. Ingest Nominal Terminal Voltage Residual
        if v_meas is not None and v_sim is not None:
            self._nominal_voltage_acc.update(measured=v_meas, simulated=v_sim)

        # 4. Ingest Prospective Shadow ECM Simulation
        if (
            latest_identified_params is not None
            and v_meas is not None
            and i_meas is not None
            and v_oc is not None
        ):
            nom_pols = sync_output.model_output.state.polarization_voltages_v
            init_v = nom_pols[0] if nom_pols else 0.0
            v_prosp = self._shadow_sim.step(
                v_oc=v_oc,
                current_a=i_meas,
                dt_s=effective_dt,
                r0_ohm=latest_identified_params.r0_ohm,
                r1_ohm=latest_identified_params.r1_ohm,
                c1_farad=latest_identified_params.c1_farad,
                initial_polarization_v=init_v,
            )
            self._prospective_voltage_acc.update(measured=v_meas, simulated=v_prosp)

        # 5. Ingest Temperature Residual (if thermal model is active)
        t_meas = (
            snapshot.avg_cell_temperature_c
            if snapshot.avg_cell_temperature_c is not None
            else snapshot.max_cell_temperature_c
        )
        t_sim = sync_output.model_output.state.temperature_c
        if t_meas is not None and t_sim is not None:
            self._temp_acc.update(measured=t_meas, simulated=t_sim)

        # 6. Ingest SOC Discrepancy (Model-Predicted vs Estimator)
        if sync_output.estimation_output is not None:
            soc_sim = sync_output.model_output.state.soc_fraction
            soc_est = sync_output.estimation_output.state.soc_fraction
            self._soc_discrepancy_acc.update(measured=soc_sim, simulated=soc_est)

        # 7. Electrical Consistency Audits
        if i_meas is not None:
            i_model_in = sync_output.telemetry.pack_current_a
            if i_model_in is not None:
                err_i = abs(i_meas - i_model_in)
                self._max_current_consistency_a = (
                    max(self._max_current_consistency_a or 0.0, err_i)
                )

        if snapshot.pack_power_w is not None and v_meas is not None and i_meas is not None:
            calc_p = v_meas * i_meas
            err_p = abs(snapshot.pack_power_w - calc_p)
            self._max_power_consistency_w = (
                max(self._max_power_consistency_w or 0.0, err_p)
            )

        # 8. Track Window Current Variance
        if i_meas is not None:
            n_curr = self._window_sample_count
            delta_i = i_meas - self._current_mean
            self._current_mean += delta_i / n_curr
            delta_i_2 = i_meas - self._current_mean
            self._current_m2 += delta_i * delta_i_2

        # 9. Window Completion Evaluation
        duration_s = (
            (self._window_last_ts_ns - self._window_start_ts_ns) / 1.0e9
            if (self._window_last_ts_ns is not None and self._window_start_ts_ns is not None)
            else 0.0
        )

        if (
            duration_s >= self._config.window_duration_s
            or self._window_sample_count >= self._config.max_samples_per_window
        ):
            self._seal_window(latest_identified_params=latest_identified_params)
            self._reset_accumulators()

        return self._build_active_report(latest_identified_params)

    def _seal_window(
        self,
        state_override: Optional[ModelValidationState] = None,
        reason: Optional[str] = None,
        latest_identified_params: Optional[IdentifiedParameterSet] = None,
    ) -> ValidationWindowReport:
        """Seals the active validation window, evaluates its final state, and commits it to history."""
        start_ts = self._window_start_ts_ns if self._window_start_ts_ns is not None else 0
        end_ts = self._window_last_ts_ns if self._window_last_ts_ns is not None else start_ts
        duration_s = (end_ts - start_ts) / 1.0e9 if (end_ts > start_ts) else 0.0
        sample_count = self._window_sample_count

        v_metrics = self._nominal_voltage_acc.compute_metrics(
            signal_name="terminal_voltage_v",
            provenance_a=SignalProvenance.MEASURED,
            provenance_b=SignalProvenance.MODEL_PREDICTED,
        )
        prosp_v_metrics = self._prospective_voltage_acc.compute_metrics(
            signal_name="prospective_terminal_voltage_v",
            provenance_a=SignalProvenance.MEASURED,
            provenance_b=SignalProvenance.MODEL_PREDICTED,
        )
        t_metrics = self._temp_acc.compute_metrics(
            signal_name="temperature_c",
            provenance_a=SignalProvenance.MEASURED,
            provenance_b=SignalProvenance.MODEL_PREDICTED,
        ) if self._temp_acc.sample_count > 0 else None

        soc_metrics = self._soc_discrepancy_acc.compute_metrics(
            signal_name="soc_discrepancy",
            provenance_a=SignalProvenance.MODEL_PREDICTED,
            provenance_b=SignalProvenance.ESTIMATED,
        ) if self._soc_discrepancy_acc.sample_count > 0 else None

        # Evaluate Parameter Evidence
        param_evidence: Optional[ParameterValidationEvidence] = None
        if latest_identified_params is not None:
            param_evidence = self._param_validator.evaluate(
                timestamp_ns=end_ts,
                system_id=self._system_id,
                identified_params=latest_identified_params,
                nominal_rmse_v=v_metrics.rmse if sample_count > 0 else None,
                prospective_rmse_v=prosp_v_metrics.rmse if prosp_v_metrics.sample_count > 0 else None,
                sample_count=sample_count,
            )

        # Determine Final State
        if state_override is not None:
            final_state = state_override
        elif self._window_flags:
            final_state = ModelValidationState.DATA_QUALITY_FAILED
        elif sample_count < self._config.min_samples_per_window:
            final_state = ModelValidationState.INSUFFICIENT_DATA
        else:
            # Check excitation
            curr_var = (
                self._current_m2 / (sample_count - 1) if sample_count > 1 else 0.0
            )
            if curr_var < self._config.min_current_variance:
                final_state = ModelValidationState.EXCITATION_STEADY_STATE_ONLY
            elif (
                v_metrics.rmse <= self._config.voltage_rmse_threshold_v
                and v_metrics.max_error <= self._config.voltage_max_error_threshold_v
            ):
                final_state = ModelValidationState.VALIDATED
            else:
                final_state = ModelValidationState.DEGRADED

        diag: dict[str, Any] = {
            "current_variance": self._current_m2 / (sample_count - 1) if sample_count > 1 else 0.0,
        }
        if reason:
            diag["seal_reason"] = reason

        window_report = ValidationWindowReport(
            window_id=f"win_{self._system_id}_{self._window_index}",
            system_id=self._system_id,
            start_timestamp_ns=start_ts,
            end_timestamp_ns=end_ts,
            duration_s=duration_s,
            sample_count=sample_count,
            state=final_state,
            voltage_metrics=v_metrics if sample_count > 0 else None,
            temperature_metrics=t_metrics,
            soc_discrepancy_metrics=soc_metrics,
            current_consistency_max_a=self._max_current_consistency_a,
            power_consistency_max_w=self._max_power_consistency_w,
            parameter_evidence=param_evidence,
            data_quality_flags=tuple(self._window_flags),
            diagnostics=diag,
        )

        self._history.append(window_report)
        self._window_index += 1
        return window_report

    def _reset_accumulators(self) -> None:
        """Resets streaming accumulators for the next window."""
        self._nominal_voltage_acc.reset()
        self._prospective_voltage_acc.reset()
        self._temp_acc.reset()
        self._soc_discrepancy_acc.reset()
        self._max_current_consistency_a = None
        self._max_power_consistency_w = None
        self._current_mean = 0.0
        self._current_m2 = 0.0
        self._window_start_ts_ns = None
        self._window_last_ts_ns = None
        self._window_sample_count = 0
        self._window_flags.clear()

    def _build_active_report(
        self,
        latest_identified_params: Optional[IdentifiedParameterSet] = None,
    ) -> ModelValidationReport:
        """Builds snapshot of active window state and history."""
        start_ts = self._window_start_ts_ns or 0
        end_ts = self._window_last_ts_ns or start_ts
        duration_s = (end_ts - start_ts) / 1.0e9 if (end_ts > start_ts) else 0.0
        sample_count = self._window_sample_count

        v_metrics = self._nominal_voltage_acc.compute_metrics(
            signal_name="terminal_voltage_v",
            provenance_a=SignalProvenance.MEASURED,
            provenance_b=SignalProvenance.MODEL_PREDICTED,
        ) if sample_count > 0 else None

        active_window = ValidationWindowReport(
            window_id=f"win_{self._system_id}_{self._window_index}",
            system_id=self._system_id,
            start_timestamp_ns=start_ts,
            end_timestamp_ns=end_ts,
            duration_s=duration_s,
            sample_count=sample_count,
            state=ModelValidationState.VALIDATING if sample_count > 0 else ModelValidationState.INSUFFICIENT_DATA,
            voltage_metrics=v_metrics,
            temperature_metrics=self._temp_acc.compute_metrics("temperature_c") if self._temp_acc.sample_count > 0 else None,
            soc_discrepancy_metrics=self._soc_discrepancy_acc.compute_metrics("soc_discrepancy") if self._soc_discrepancy_acc.sample_count > 0 else None,
            current_consistency_max_a=self._max_current_consistency_a,
            power_consistency_max_w=self._max_power_consistency_w,
            data_quality_flags=tuple(self._window_flags),
        )

        completed = self._history[-1] if self._history else None
        latest_evidence = completed.parameter_evidence if (completed and completed.parameter_evidence) else None

        report = ModelValidationReport(
            system_id=self._system_id,
            timestamp_ns=end_ts,
            active_window=active_window,
            latest_completed_window=completed,
            parameter_evidence=latest_evidence,
        )
        self._latest_report = report
        return report

    def reset(self) -> None:
        """Resets engine state, history buffer, and all accumulators."""
        self._auditor.reset()
        self._shadow_sim.reset()
        self._param_validator.reset()
        self._reset_accumulators()
        self._history.clear()
        self._latest_report = None
        self._window_index = 1
