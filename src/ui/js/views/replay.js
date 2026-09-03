/**
 * Drive-Cycle Replay & Tracking Evaluation View Component
 * Coordinates benchmark simulation runs and displays backend-generated statistical error reports.
 */

import { api } from '../api.js';
import { store } from '../state.js';

export class ReplayView {
  constructor(container) {
    this.container = container;
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="grid-12">
        <!-- Replay Execution Controls -->
        <div class="col-4">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Benchmark Schedule Runner</span>
              <span class="badge badge-cyan">SIMULATION</span>
            </div>
            <form id="form-run-replay">
              <div class="form-group">
                <label class="form-label" for="replay-profile-select">Standard Profile</label>
                <select id="replay-profile-select" class="form-select" style="width: 100%;">
                  <option value="WLTP">WLTP Class 3 Cycle (1800s)</option>
                  <option value="US06">US06 Supplemental Cycle (600s)</option>
                  <option value="DST">Dynamic Stress Test (DST)</option>
                  <option value="PULSE">Pulse Discharge Schedule</option>
                  <option value="CONSTANT_CURRENT">Constant Current Discharge</option>
                </select>
              </div>

              <div class="form-group">
                <label class="form-label" for="replay-peak-current">Peak Current (A)</label>
                <input id="replay-peak-current" class="form-input" type="number" step="0.5" value="10.0" />
              </div>

              <div class="form-group">
                <label class="form-label" for="replay-duration">Duration (s, optional)</label>
                <input id="replay-duration" class="form-input" type="number" step="10" placeholder="Default schedule duration" />
              </div>

              <div class="form-group">
                <label class="form-label" for="replay-dt">Simulation dt (s)</label>
                <input id="replay-dt" class="form-input" type="number" step="0.1" value="1.0" />
              </div>

              <button type="submit" id="btn-execute-replay" class="btn btn-primary" style="width: 100%; margin-top: var(--space-2);">
                Execute Drive-Cycle Replay
              </button>
            </form>

            <div id="replay-status-indicator" style="margin-top: var(--space-3); font-size: var(--text-xs); font-family: var(--font-mono);"></div>
          </div>
        </div>

        <!-- Statistical Scorecard & Tracking Accuracy -->
        <div class="col-8">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Tracking Accuracy & Error Metrics Scorecard</span>
              <span id="replay-pass-badge" class="badge badge-cyan">Status: Ready</span>
            </div>
            <p class="card-subtitle" style="margin-bottom: var(--space-3);">
              Statistical tracking residuals calculated by the backend TrackingMetricsEvaluator engine.
            </p>

            <div class="grid-12" style="margin-bottom: var(--space-4);">
              <div class="col-4">
                <div class="metric-widget">
                  <span class="metric-label">Root Mean Square Error</span>
                  <div class="metric-value-row">
                    <span id="score-rmse" class="metric-value">--</span>
                    <span class="metric-unit">mV</span>
                  </div>
                </div>
              </div>

              <div class="col-4">
                <div class="metric-widget">
                  <span class="metric-label">Mean Absolute Error (MAE)</span>
                  <div class="metric-value-row">
                    <span id="score-mae" class="metric-value">--</span>
                    <span class="metric-unit">mV</span>
                  </div>
                </div>
              </div>

              <div class="col-4">
                <div class="metric-widget">
                  <span class="metric-label">Coefficient of Determination (R²)</span>
                  <div class="metric-value-row">
                    <span id="score-r2" class="metric-value">--</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Signal Tracked</th>
                    <th>Samples</th>
                    <th>RMSE (V)</th>
                    <th>MAE (V)</th>
                    <th>Max Error (V)</th>
                    <th>Mean Bias Error</th>
                    <th>NRMSE</th>
                  </tr>
                </thead>
                <tbody id="replay-metrics-tbody">
                  <tr>
                    <td colspan="7" class="unavailable-text" style="text-align: center; padding: var(--space-4);">
                      Execute a drive-cycle replay to generate statistical metrics.
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
  }

  _bindEvents() {
    const form = document.getElementById('form-run-replay');
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const ptype = document.getElementById('replay-profile-select').value;
        const peakI = parseFloat(document.getElementById('replay-peak-current').value);
        const durStr = document.getElementById('replay-duration').value;
        const dt = parseFloat(document.getElementById('replay-dt').value) || 1.0;
        const statusEl = document.getElementById('replay-status-indicator');
        const btn = document.getElementById('btn-execute-replay');

        if (!store.activeTwinId) {
          if (statusEl) {
            statusEl.textContent = 'Error: No active digital twin selected.';
            statusEl.style.color = 'var(--color-danger)';
          }
          return;
        }

        const payload = {
          profile_type: ptype,
          peak_current_a: isNaN(peakI) ? undefined : peakI,
          duration_s: durStr ? parseFloat(durStr) : undefined,
          dt_s: dt,
          evaluate_metrics: true,
        };

        try {
          if (btn) btn.disabled = true;
          if (statusEl) {
            statusEl.textContent = `Running ${ptype} simulation...`;
            statusEl.style.color = 'var(--color-primary)';
          }

          const result = await api.replayProfile(store.activeTwinId, payload);
          store.setReplayResult(result);

          if (statusEl) {
            statusEl.textContent = `Completed ${result.executed_steps} steps in ${result.duration_seconds.toFixed(2)}s.`;
            statusEl.style.color = 'var(--color-success)';
          }
        } catch (err) {
          if (statusEl) {
            statusEl.textContent = `Replay failed: ${err.message}`;
            statusEl.style.color = 'var(--color-danger)';
          }
        } finally {
          if (btn) btn.disabled = false;
        }
      });
    }
  }

  update(changeType, appState) {
    if (changeType === 'REPLAY_RESULT' && appState.lastReplayResult) {
      const res = appState.lastReplayResult;
      const passBadge = document.getElementById('replay-pass-badge');
      const rmseEl = document.getElementById('score-rmse');
      const maeEl = document.getElementById('score-mae');
      const r2El = document.getElementById('score-r2');
      const tbody = document.getElementById('replay-metrics-tbody');

      if (passBadge) {
        passBadge.textContent = res.is_passing ? 'PASS' : 'DEGRADED';
        passBadge.className = res.is_passing ? 'badge badge-cyan' : 'badge badge-amber';
      }

      if (res.signals && tbody) {
        let rowsHtml = '';
        for (const [name, sig] of Object.entries(res.signals)) {
          rowsHtml += `
            <tr>
              <td class="cell-mono">${sig.signal_name}</td>
              <td class="cell-mono">${sig.sample_count}</td>
              <td class="cell-mono">${sig.rmse.toFixed(4)}</td>
              <td class="cell-mono">${sig.mae.toFixed(4)}</td>
              <td class="cell-mono">${sig.max_error.toFixed(4)}</td>
              <td class="cell-mono">${sig.mean_bias_error.toFixed(4)}</td>
              <td class="cell-mono">${(sig.nrmse * 100).toFixed(2)}%</td>
            </tr>
          `;

          if (sig.signal_name.toLowerCase().includes('voltage')) {
            if (rmseEl) rmseEl.textContent = (sig.rmse * 1000).toFixed(1);
            if (maeEl) maeEl.textContent = (sig.mae * 1000).toFixed(1);
            if (r2El) r2El.textContent = sig.r_squared.toFixed(4);
          }
        }
        tbody.innerHTML = rowsHtml;
      }
    }
  }

  destroy() {}
}
