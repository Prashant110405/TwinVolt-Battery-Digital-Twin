/**
 * Battery Benchmarking & Experimental Evidence View Component (Level 5.5 Phase 4)
 * Visualizes deterministic quantitative tracking metrics, diagnostic ground-truth evaluations,
 * and metrological provenance without performing browser-side scientific calculations.
 */

import { api } from '../api.js';
import { store } from '../state.js';
import { escapeHTML } from '../html.js';

export class BenchmarkingView {
  constructor(container) {
    this.container = container;
    this.datasets = [];
    this.activeResult = null;
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="grid-12">
        <!-- Benchmarking Control Card -->
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <div>
                <span class="card-title">Experimental Benchmarking & Ground-Truth Validation</span>
                <span class="card-subtitle">Level 5.5 isolated co-simulation evaluation against reference datasets</span>
              </div>
              <div style="display: flex; gap: var(--space-2); align-items: center;">
                <span id="bench-gating-badge" class="badge badge-gray">IDLE</span>
                <button id="btn-reset-benchmarks" class="btn btn-secondary btn-sm">Reset Benchmark History</button>
              </div>
            </div>

            <div class="grid-12" style="margin-top: var(--space-3); gap: var(--space-3);">
              <div class="col-4">
                <label class="metric-label" for="bench-dataset-select">Reference Dataset</label>
                <select id="bench-dataset-select" class="twin-select" style="width: 100%; margin-top: var(--space-1);">
                  <option value="">Loading datasets...</option>
                </select>
              </div>
              <div class="col-2">
                <label class="metric-label" for="bench-align-mode">Alignment Mode</label>
                <select id="bench-align-mode" class="twin-select" style="width: 100%; margin-top: var(--space-1);">
                  <option value="CAUSAL_STREAMING">Causal Streaming</option>
                  <option value="NON_CAUSAL_BATCH">Non-Causal Batch</option>
                </select>
              </div>
              <div class="col-2">
                <label class="metric-label" for="bench-target-v-rmse">Target V RMSE (V)</label>
                <input id="bench-target-v-rmse" type="number" step="0.005" placeholder="e.g. 0.020" class="twin-select" style="width: 100%; margin-top: var(--space-1);" />
              </div>
              <div class="col-2">
                <label class="metric-label" for="bench-target-t-rmse">Target T RMSE (°C)</label>
                <input id="bench-target-t-rmse" type="number" step="0.1" placeholder="e.g. 1.0" class="twin-select" style="width: 100%; margin-top: var(--space-1);" />
              </div>
              <div class="col-2" style="display: flex; align-items: flex-end;">
                <button id="btn-run-benchmark" class="btn btn-primary" style="width: 100%; height: 38px;">Run Benchmark</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Benchmark Execution Summary -->
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Execution Overview</span>
              <div style="display: flex; gap: var(--space-2);">
                <span id="bench-semantic-badge" class="badge badge-purple">EVALUATION: IDLE</span>
                <span id="bench-evidence-badge" class="badge badge-blue">EVIDENCE: --</span>
              </div>
            </div>
            <div class="grid-12" style="margin-top: var(--space-3);">
              <div class="col-3">
                <div class="metric-card">
                  <div class="metric-label">Benchmark Run ID</div>
                  <div id="bench-run-id" class="metric-value cell-mono" style="font-size: var(--text-sm);">--</div>
                </div>
              </div>
              <div class="col-3">
                <div class="metric-card">
                  <div class="metric-label">Evaluated Frames</div>
                  <div id="bench-frames-count" class="metric-value">--</div>
                </div>
              </div>
              <div class="col-3">
                <div class="metric-card">
                  <div class="metric-label">Execution Duration</div>
                  <div id="bench-duration-sec" class="metric-value">-- s</div>
                </div>
              </div>
              <div class="col-3">
                <div class="metric-card">
                  <div class="metric-label">Acceptance Gating</div>
                  <div id="bench-gating-status" class="metric-value" style="font-size: var(--text-base);">NOT_EVALUABLE</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Quantitative Signal Metrology Card -->
        <div class="col-6">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Quantitative Signal Metrology</span>
              <span class="badge badge-blue">Deterministic Metrics</span>
            </div>
            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Signal</th>
                    <th>MAE</th>
                    <th>RMSE</th>
                    <th>Max Error</th>
                    <th>R²</th>
                    <th>Pairs</th>
                  </tr>
                </thead>
                <tbody id="bench-signals-table-body">
                  <tr>
                    <td colspan="6" style="text-align: center; color: var(--text-muted);">No benchmark metrics evaluated.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Diagnostic Ground-Truth & Confusion Matrix Card -->
        <div class="col-6">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Diagnostic Evaluation & Latency</span>
              <span class="badge badge-purple">Sample Confusion</span>
            </div>
            <div class="grid-12">
              <div class="col-3">
                <div class="metric-card">
                  <div class="metric-label">Precision</div>
                  <div id="bench-diag-prec" class="metric-value">--</div>
                </div>
              </div>
              <div class="col-3">
                <div class="metric-card">
                  <div class="metric-label">Recall</div>
                  <div id="bench-diag-rec" class="metric-value">--</div>
                </div>
              </div>
              <div class="col-3">
                <div class="metric-card">
                  <div class="metric-label">F1-Score</div>
                  <div id="bench-diag-f1" class="metric-value">--</div>
                </div>
              </div>
              <div class="col-3">
                <div class="metric-card">
                  <div class="metric-label">Mean Latency</div>
                  <div id="bench-diag-lat" class="metric-value">-- s</div>
                </div>
              </div>
            </div>

            <div class="data-table-container" style="margin-top: var(--space-3);">
              <table class="data-table">
                <tbody>
                  <tr>
                    <td>True Positives (TP)</td>
                    <td id="bench-tp" class="cell-mono">--</td>
                    <td>False Positives (FP)</td>
                    <td id="bench-fp" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>True Negatives (TN)</td>
                    <td id="bench-tn" class="cell-mono">--</td>
                    <td>False Negatives (FN)</td>
                    <td id="bench-fn" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Unobservable / Unknown Samples</td>
                    <td id="bench-unknown" class="cell-mono" colspan="3">--</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Ground Truth Event Matching Breakdown Table -->
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Ground-Truth Event Matching Log</span>
              <span class="badge badge-gray">Phase 3 Matching Semantics</span>
            </div>
            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Event ID</th>
                    <th>Event Type</th>
                    <th>Expected Hypothesis</th>
                    <th>Match Status</th>
                    <th>Latency (s)</th>
                    <th>Severity</th>
                    <th>Corroborating Channels</th>
                  </tr>
                </thead>
                <tbody id="bench-events-table-body">
                  <tr>
                    <td colspan="7" style="text-align: center; color: var(--text-muted);">No ground-truth events evaluated in current dataset.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    `;

    this._setupEventListeners();
    this.refreshDatasets();
  }

  _setupEventListeners() {
    const runBtn = document.getElementById('btn-run-benchmark');
    if (runBtn) {
      runBtn.addEventListener('click', () => this.handleRunBenchmark());
    }

    const resetBtn = document.getElementById('btn-reset-benchmarks');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => this.handleResetBenchmarks());
    }
  }

  async refreshDatasets() {
    try {
      this.datasets = await api.getBenchmarkDatasets();
      const select = document.getElementById('bench-dataset-select');
      if (select) {
        if (this.datasets.length === 0) {
          select.innerHTML = '<option value="">No registered datasets</option>';
        } else {
          select.innerHTML = this.datasets
            .map((d) => `<option value="${escapeHTML(d.dataset_id)}">${escapeHTML(d.dataset_name)} (${escapeHTML(d.total_frames)} frames, v${escapeHTML(d.version)})</option>`)
            .join('');
        }
      }
    } catch (err) {
      console.warn('[BenchmarkingView] Failed to fetch registered datasets:', err.message);
    }
  }

  async handleRunBenchmark() {
    const systemId = store.activeTwinId;
    if (!systemId) {
      alert('Please select or create an active Digital Twin before running a benchmark.');
      return;
    }

    const datasetSelect = document.getElementById('bench-dataset-select');
    const datasetId = datasetSelect ? datasetSelect.value : '';
    if (!datasetId) {
      alert('Please select a registered reference dataset.');
      return;
    }

    const alignMode = document.getElementById('bench-align-mode')?.value || 'CAUSAL_STREAMING';
    const targetVRmseStr = document.getElementById('bench-target-v-rmse')?.value;
    const targetTRmseStr = document.getElementById('bench-target-t-rmse')?.value;

    const payload = {
      dataset_id: datasetId,
      alignment_mode: alignMode,
      evaluate_signals: true,
      evaluate_diagnostics: true,
      target_voltage_rmse_v: targetVRmseStr ? parseFloat(targetVRmseStr) : null,
      target_temp_rmse_c: targetTRmseStr ? parseFloat(targetTRmseStr) : null,
    };

    const runBtn = document.getElementById('btn-run-benchmark');
    if (runBtn) {
      runBtn.disabled = true;
      runBtn.textContent = 'Running...';
    }

    try {
      const result = await api.runBenchmark(systemId, payload);
      this.renderResult(result);
    } catch (err) {
      alert(`Benchmark execution failed: ${err.message}`);
    } finally {
      if (runBtn) {
        runBtn.disabled = false;
        runBtn.textContent = 'Run Benchmark';
      }
    }
  }

  async handleResetBenchmarks() {
    const systemId = store.activeTwinId;
    if (!systemId) return;

    if (confirm(`Reset benchmark execution history for twin '${systemId}'? (Live twin state will remain unaffected)`)) {
      try {
        await api.resetBenchmark(systemId);
        this.activeResult = null;
        this.clearRenderedResults();
      } catch (err) {
        alert(`Failed to reset benchmarks: ${err.message}`);
      }
    }
  }

  clearRenderedResults() {
    const gatingBadge = document.getElementById('bench-gating-badge');
    if (gatingBadge) {
      gatingBadge.textContent = 'IDLE';
      gatingBadge.className = 'badge badge-gray';
    }

    const runId = document.getElementById('bench-run-id');
    if (runId) runId.textContent = '--';
    const framesCount = document.getElementById('bench-frames-count');
    if (framesCount) framesCount.textContent = '--';
    const durSec = document.getElementById('bench-duration-sec');
    if (durSec) durSec.textContent = '-- s';
    const gatingStatus = document.getElementById('bench-gating-status');
    if (gatingStatus) gatingStatus.textContent = 'NOT_EVALUABLE';

    const signalsTable = document.getElementById('bench-signals-table-body');
    if (signalsTable) {
      signalsTable.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No benchmark metrics evaluated.</td></tr>';
    }

    const eventsTable = document.getElementById('bench-events-table-body');
    if (eventsTable) {
      eventsTable.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No ground-truth events evaluated in current dataset.</td></tr>';
    }

    const elPrec = document.getElementById('bench-diag-prec');
    if (elPrec) elPrec.textContent = '--';
    const elRec = document.getElementById('bench-diag-rec');
    if (elRec) elRec.textContent = '--';
    const elF1 = document.getElementById('bench-diag-f1');
    if (elF1) elF1.textContent = '--';
    const elLat = document.getElementById('bench-diag-lat');
    if (elLat) elLat.textContent = '-- s';

    const tp = document.getElementById('bench-tp');
    if (tp) tp.textContent = '--';
    const fp = document.getElementById('bench-fp');
    if (fp) fp.textContent = '--';
    const tn = document.getElementById('bench-tn');
    if (tn) tn.textContent = '--';
    const fn = document.getElementById('bench-fn');
    if (fn) fn.textContent = '--';
    const unk = document.getElementById('bench-unknown');
    if (unk) unk.textContent = '--';
  }

  renderResult(res) {
    this.activeResult = res;

    // 1. Gating & Overview
    const gatingBadge = document.getElementById('bench-gating-badge');
    const gatingStatus = document.getElementById('bench-gating-status');
    const isPass = res.is_passing;
    const gStatus = res.gating_status || (isPass ? 'PASS' : 'FAIL');

    if (gatingBadge) {
      gatingBadge.textContent = gStatus;
      gatingBadge.className = `badge ${gStatus === 'PASS' ? 'badge-green' : gStatus === 'FAIL' ? 'badge-red' : 'badge-gray'}`;
    }
    if (gatingStatus) {
      gatingStatus.textContent = gStatus;
      gatingStatus.style.color = gStatus === 'PASS' ? 'var(--color-success)' : gStatus === 'FAIL' ? 'var(--color-danger)' : 'var(--text-muted)';
    }

    const runId = document.getElementById('bench-run-id');
    if (runId) runId.textContent = res.benchmark_id || '--';
    const framesCount = document.getElementById('bench-frames-count');
    if (framesCount) framesCount.textContent = res.total_frames_evaluated ?? '--';
    const durSec = document.getElementById('bench-duration-sec');
    if (durSec) durSec.textContent = res.duration_seconds !== undefined ? `${res.duration_seconds.toFixed(3)} s` : '-- s';

    // 2. Signals Table
    const signalsTable = document.getElementById('bench-signals-table-body');
    if (signalsTable && res.signals) {
      const rows = Object.values(res.signals);
      if (rows.length === 0) {
        signalsTable.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No signal metrics available.</td></tr>';
      } else {
        signalsTable.innerHTML = rows
          .map((s) => `
            <tr>
              <td><strong>${escapeHTML(s.signal_name)}</strong> (${escapeHTML(s.unit)})</td>
              <td class="cell-mono">${s.mae !== null && s.mae !== undefined ? s.mae.toFixed(4) : '--'}</td>
              <td class="cell-mono">${s.rmse !== null && s.rmse !== undefined ? s.rmse.toFixed(4) : '--'}</td>
              <td class="cell-mono">${s.max_error !== null && s.max_error !== undefined ? s.max_error.toFixed(4) : '--'}</td>
              <td class="cell-mono">${s.r_squared !== null && s.r_squared !== undefined ? s.r_squared.toFixed(4) : '--'}</td>
              <td class="cell-mono">${s.valid_paired_samples}</td>
            </tr>
          `)
          .join('');
      }
    }

    // 3. Diagnostic Confusion & Latency
    if (res.diagnostics) {
      const d = res.diagnostics;
      const m = d.sample_confusion_matrix;
      const l = d.latency_summary;

      const semBadge = document.getElementById('bench-semantic-badge');
      if (semBadge) semBadge.textContent = d.semantic_class || 'EVALUATION';
      const evBadge = document.getElementById('bench-evidence-badge');
      if (evBadge) evBadge.textContent = `EVIDENCE: ${d.evidence_role || '--'}`;

      const elPrec = document.getElementById('bench-diag-prec');
      if (elPrec) elPrec.textContent = m.precision !== null && m.precision !== undefined ? m.precision.toFixed(3) : '--';
      const elRec = document.getElementById('bench-diag-rec');
      if (elRec) elRec.textContent = m.recall !== null && m.recall !== undefined ? m.recall.toFixed(3) : '--';
      const elF1 = document.getElementById('bench-diag-f1');
      if (elF1) elF1.textContent = m.f1_score !== null && m.f1_score !== undefined ? m.f1_score.toFixed(3) : '--';
      const elLat = document.getElementById('bench-diag-lat');
      if (elLat) elLat.textContent = l.mean_latency_s !== null && l.mean_latency_s !== undefined ? `${l.mean_latency_s.toFixed(3)} s` : '-- s';

      const tp = document.getElementById('bench-tp');
      if (tp) tp.textContent = m.true_positives;
      const fp = document.getElementById('bench-fp');
      if (fp) fp.textContent = m.false_positives;
      const tn = document.getElementById('bench-tn');
      if (tn) tn.textContent = m.true_negatives;
      const fn = document.getElementById('bench-fn');
      if (fn) fn.textContent = m.false_negatives;
      const unk = document.getElementById('bench-unknown');
      if (unk) unk.textContent = m.unknown_samples;

      // 4. Events Log Table
      const eventsTable = document.getElementById('bench-events-table-body');
      if (eventsTable && d.event_evaluations) {
        if (d.event_evaluations.length === 0) {
          eventsTable.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No ground-truth events evaluated in current dataset.</td></tr>';
        } else {
          eventsTable.innerHTML = d.event_evaluations
            .map((ev) => {
              const statusBadgeClass =
                ev.match_status === 'DETECTED_MATCH'
                  ? 'badge-green'
                  : ev.match_status === 'DETECTED_EARLY'
                  ? 'badge-yellow'
                  : ev.match_status === 'MISSED_EVENT'
                  ? 'badge-red'
                  : 'badge-gray';

              const channels = ev.corroborating_channels && ev.corroborating_channels.length > 0
                ? ev.corroborating_channels.join(', ')
                : '--';

              return `
                <tr>
                  <td class="cell-mono"><strong>${escapeHTML(ev.event_id)}</strong></td>
                  <td>${escapeHTML(ev.event_type)}</td>
                  <td class="cell-mono">${escapeHTML(ev.expected_hypothesis_id || '--')}</td>
                  <td><span class="badge ${statusBadgeClass}">${escapeHTML(ev.match_status)}</span></td>
                  <td class="cell-mono">${ev.latency_seconds !== null && ev.latency_seconds !== undefined ? `${ev.latency_seconds.toFixed(3)} s` : '--'}</td>
                  <td>${escapeHTML(ev.severity_at_detection || '--')}</td>
                  <td style="font-size: var(--text-xs);">${escapeHTML(channels)}</td>
                </tr>
              `;
            })
            .join('');
        }
      }
    }
  }

  async update(changeType, appState) {
    if (changeType === 'TWIN_CHANGED') {
      if (appState.activeTwinId) {
        try {
          const latest = await api.getLatestBenchmark(appState.activeTwinId);
          this.renderResult(latest);
        } catch (_) {
          this.clearRenderedResults();
        }
      } else {
        this.clearRenderedResults();
      }
    }
  }
}
