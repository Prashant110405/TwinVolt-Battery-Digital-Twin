/**
 * Live Telemetry View Component
 * Displays the latest persisted observation snapshot and explicit connection freshness.
 */

import { api } from '../api.js';
import { store } from '../state.js';
import { wsClient } from '../websocket.js';

export class TelemetryView {
  constructor(container) {
    this.container = container;
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="grid-12">
        <div class="col-8">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Latest Persisted Telemetry Observation</span>
              <span id="tel-stream-status" class="badge badge-gray">Awaiting twin selection</span>
            </div>
            <p class="card-subtitle telemetry-source-note">Read-only snapshot from telemetry history. The current WebSocket state contract does not push raw observation fields.</p>
            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Observation Metric</th>
                    <th>Current Value</th>
                    <th>Unit</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Pack Terminal Voltage</td>
                    <td id="tel-v" class="cell-mono">--</td>
                    <td class="cell-mono">V</td>
                    <td><span class="badge badge-gray">OBSERVED</span></td>
                  </tr>
                  <tr>
                    <td>Pack Load Current</td>
                    <td id="tel-i" class="cell-mono">--</td>
                    <td class="cell-mono">A</td>
                    <td><span class="badge badge-gray">OBSERVED</span></td>
                  </tr>
                  <tr>
                    <td>Calculated Pack Power (P = V × I)</td>
                    <td id="tel-p" class="cell-mono">--</td>
                    <td class="cell-mono">W</td>
                    <td><span class="badge badge-cyan">CALCULATED</span></td>
                  </tr>
                  <tr>
                    <td>Pack Core Temperature</td>
                    <td id="tel-temp" class="cell-mono">--</td>
                    <td class="cell-mono">°C</td>
                    <td><span class="badge badge-gray">OBSERVED</span></td>
                  </tr>
                  <tr>
                    <td>State of Charge (SoC)</td>
                    <td id="tel-soc" class="cell-mono">--</td>
                    <td class="cell-mono">%</td>
                    <td><span class="badge badge-blue">ESTIMATED</span></td>
                  </tr>
                  <tr>
                    <td>State of Health (SoH)</td>
                    <td id="tel-soh" class="cell-mono">--</td>
                    <td class="cell-mono">%</td>
                    <td><span class="badge badge-blue">ESTIMATED</span></td>
                  </tr>
                  <tr>
                    <td>Telemetry Freshness / Quality</td>
                    <td id="tel-quality" class="cell-mono">--</td>
                    <td class="cell-mono">status</td>
                    <td><span id="tel-source-mode-badge" class="badge badge-gray">AWAITING DATA</span></td>
                  </tr>
                  <tr>
                    <td>Observation Timestamp</td>
                    <td id="tel-ts" class="cell-mono">--</td>
                    <td class="cell-mono">local time</td>
                    <td><span class="badge badge-cyan">OBSERVATION TIME</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div style="display: flex; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-3);">
              <button id="btn-export-telemetry-json" class="btn btn-secondary btn-sm">Export Telemetry (JSON)</button>
              <button id="btn-export-telemetry-csv" class="btn btn-secondary btn-sm">Export Telemetry (CSV)</button>
            </div>
          </div>
          <div class="card source-card">
            <div class="card-header">
              <span class="card-title">Gateway sources</span>
              <span id="gateway-state" class="badge badge-gray">Loading</span>
            </div>
            <div id="gateway-sources" class="source-list" aria-live="polite">Loading configured sources…</div>
          </div>
        </div>

        <div class="col-4">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Manual Telemetry Injector</span>
              <span class="badge badge-amber">TEST MODE</span>
            </div>
            <p class="card-subtitle" style="margin-bottom: var(--space-3);">
              Test mode sends user-entered observations through the existing ingestion service. This is not physical BMS control.
            </p>
            <form id="form-inject-telemetry">
              <div class="form-group">
                <label class="form-label" for="input-inject-v">Pack Voltage (V)</label>
                <input id="input-inject-v" class="form-input" type="number" min="0.001" step="0.01" required />
              </div>
              <div class="form-group">
                <label class="form-label" for="input-inject-i">Pack Current (A)</label>
                <input id="input-inject-i" class="form-input" type="number" step="0.01" required />
              </div>
              <div class="form-group">
                <label class="form-label" for="input-inject-temp">Temperature (°C)</label>
                <input id="input-inject-temp" class="form-input" type="number" step="0.1" />
              </div>
              <button type="submit" class="btn btn-primary" style="width: 100%;">
                Inject Telemetry Sample
              </button>
            </form>
            <div id="inject-status-msg" style="margin-top: var(--space-2); font-size: var(--text-xs); font-family: var(--font-mono);"></div>
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
    this.loadGatewayStatus();
  }

  async loadGatewayStatus() {
    const state = document.getElementById('gateway-state');
    const list = document.getElementById('gateway-sources');
    try {
      const result = await api.getGatewayStatus();
      if (!list) return;
      const sources = Object.values(result.sources || {});
      if (state) {
        state.textContent = result.is_running ? 'Running' : 'Standby';
        state.className = `badge ${result.is_running ? 'badge-green' : 'badge-gray'}`;
      }
      if (sources.length === 0) {
        list.textContent = 'No gateway sources are configured.';
        return;
      }
      const rows = sources.map((source) => {
        const row = document.createElement('div');
        row.className = 'source-row';
        const name = document.createElement('strong');
        name.textContent = `${source.source_id} · ${source.transport_type}`;
        const detail = document.createElement('span');
        detail.textContent = `${source.state} · ${source.frames_received} frames received · ${source.frames_dropped} dropped`;
        row.append(name, detail);
        return row;
      });
      list.replaceChildren(...rows);
    } catch (error) {
      if (state) { state.textContent = 'Unavailable'; state.className = 'badge badge-red'; }
      if (list) list.textContent = `Gateway status unavailable: ${error.message}`;
    }
  }

  _bindEvents() {
    const form = document.getElementById('form-inject-telemetry');
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const v = parseFloat(document.getElementById('input-inject-v').value);
        const i = parseFloat(document.getElementById('input-inject-i').value);
        const tempInput = document.getElementById('input-inject-temp').value;
        const temp = tempInput === '' ? null : Number(tempInput);
        const statusEl = document.getElementById('inject-status-msg');
        const submitButton = form.querySelector('button[type="submit"]');

        if (!store.activeTwinId) {
          if (statusEl) {
            statusEl.textContent = 'Error: No active digital twin selected.';
            statusEl.style.color = 'var(--color-danger)';
          }
          return;
        }

        if (!Number.isFinite(v) || v <= 0 || !Number.isFinite(i) || (temp !== null && !Number.isFinite(temp))) {
          if (statusEl) {
            statusEl.textContent = 'Enter a positive voltage and valid current and temperature values.';
            statusEl.style.color = 'var(--color-danger)';
          }
          return;
        }

        if (submitButton) submitButton.disabled = true;
        try {
          if (wsClient.ws && wsClient.ws.readyState === WebSocket.OPEN) {
            const sent = wsClient.sendTelemetry({
              pack_voltage_v: v,
              pack_current_a: i,
              ...(temp !== null ? { ambient_temperature_c: temp } : {}),
              timestamp_ns: Date.now() * 1_000_000,
              source: 'manual',
              metadata: { source: 'manual' },
            });
            if (!sent) throw new Error('WebSocket is no longer connected.');
            if (statusEl) {
              statusEl.textContent = `Sent to ${store.activeTwinId}; awaiting server acknowledgement.`;
              statusEl.style.color = 'var(--color-muted)';
            }
          } else {
            await api.ingestTelemetry({
              system_id: store.activeTwinId,
              pack_voltage_v: v,
              pack_current_a: i,
              ...(temp !== null ? { ambient_temperature_c: temp } : {}),
              timestamp_ns: Date.now() * 1_000_000,
              source: 'manual',
              metadata: { source: 'manual' },
            });
            if (statusEl) {
              statusEl.textContent = `Injected via REST for ${store.activeTwinId}.`;
              statusEl.style.color = 'var(--color-success)';
            }
            this.loadLatestObservation(store.activeTwinId);
          }
        } catch (err) {
          if (statusEl) {
            statusEl.textContent = `Injection failed: ${err.message}`;
            statusEl.style.color = 'var(--color-danger)';
          }
        } finally {
          if (submitButton) submitButton.disabled = false;
        }
      });
    }

    // Export Telemetry Buttons
    this.container.querySelector('#btn-export-telemetry-json')?.addEventListener('click', async () => {
      if (!store.activeTwinId) return alert('Select a twin first.');
      try {
        const history = await api.getTelemetryHistory(store.activeTwinId, 300, false);
        const blob = new Blob([JSON.stringify(history, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `telemetry_${store.activeTwinId}_${Date.now()}.json`;
        a.click();
      } catch (err) {
        alert(`Export failed: ${err.message}`);
      }
    });

    this.container.querySelector('#btn-export-telemetry-csv')?.addEventListener('click', async () => {
      if (!store.activeTwinId) return alert('Select a twin first.');
      try {
        const history = await api.getTelemetryHistory(store.activeTwinId, 300, false);
        if (!Array.isArray(history) || history.length === 0) return alert('No telemetry records to export.');
        const keys = ['timestamp_ns', 'pack_voltage_v', 'pack_current_a', 'pack_power_w', 'ambient_temperature_c'];
        const csvRows = [keys.join(',')];
        for (const row of history) {
          csvRows.push(keys.map(k => row[k] !== undefined && row[k] !== null ? row[k] : '').join(','));
        }
        const blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `telemetry_${store.activeTwinId}_${Date.now()}.csv`;
        a.click();
      } catch (err) {
        alert(`Export failed: ${err.message}`);
      }
    });
  }

  update(changeType, appState, payload = {}) {
    if (changeType === 'TWIN_CHANGED') {
      this.loadLatestObservation(appState.activeTwinId);
    } else if (changeType === 'TELEMETRY_ACK') {
      const statusEl = document.getElementById('inject-status-msg');
      const ack = payload.message;
      if (statusEl && ack?.status === 'ACK') {
        statusEl.textContent = `Ingest acknowledged for ${ack.system_id}${ack.stepped_twin ? ' and applied to the twin' : ''}.`;
        statusEl.style.color = 'var(--color-success)';
      } else if (statusEl && ack) {
        statusEl.textContent = `Telemetry ingest status: ${ack.status || 'unknown'}.`;
        statusEl.style.color = 'var(--color-muted)';
      }
      this.loadLatestObservation(appState.activeTwinId);
    } else if (changeType === 'STATE_UPDATED' && appState.latestState) {
      this._renderLiveState(appState);
    }
  }

  _renderLiveState(appState) {
    const s = appState.latestState;
    if (!s) return;

    const v = Number.isFinite(s.diagnostics?.telemetry_voltage_v) ? s.diagnostics.telemetry_voltage_v : s.terminal_voltage_v;
    const i = Number.isFinite(s.diagnostics?.telemetry_current_a) ? s.diagnostics.telemetry_current_a : null;
    const p = (v !== null && i !== null) ? (v * i) : null;
    const temp = Number.isFinite(s.temperature_c) ? s.temperature_c : null;
    const soc = Number.isFinite(s.estimated_soc) ? s.estimated_soc * 100 : (Number.isFinite(s.simulated_soc) ? s.simulated_soc * 100 : null);

    const elV = document.getElementById('tel-v');
    const elI = document.getElementById('tel-i');
    const elP = document.getElementById('tel-p');
    const elTemp = document.getElementById('tel-temp');
    const elSoc = document.getElementById('tel-soc');
    const elSoh = document.getElementById('tel-soh');
    const elTs = document.getElementById('tel-ts');
    const elQuality = document.getElementById('tel-quality');
    const elModeBadge = document.getElementById('tel-source-mode-badge');
    const streamStatus = document.getElementById('tel-stream-status');

    const soh = Number.isFinite(s.soh_unified_fraction)
      ? s.soh_unified_fraction * 100
      : (Number.isFinite(s.soh_fraction) ? s.soh_fraction * 100 : null);

    if (elV) elV.textContent = v !== null ? v.toFixed(3) : '—';
    if (elI) elI.textContent = i !== null ? i.toFixed(3) : '—';
    if (elP) elP.textContent = p !== null ? p.toFixed(2) : '—';
    if (elTemp) elTemp.textContent = temp !== null ? temp.toFixed(1) : '—';
    if (elSoc) elSoc.textContent = soc !== null ? `${soc.toFixed(1)}%` : '—';
    if (elSoh) elSoh.textContent = soh !== null ? `${soh.toFixed(1)}%` : 'Unavailable';
    if (elTs) elTs.textContent = new Date(s.timestamp_ns / 1e6).toLocaleTimeString();

    const isStale = (Date.now() - (appState.lastStateReceivedAtMs || Date.now())) > 5000;
    if (elQuality) {
      elQuality.textContent = isStale ? 'STALE' : 'VALID';
      elQuality.style.color = isStale ? 'var(--color-warning)' : 'var(--color-success)';
    }

    if (elModeBadge) {
      const mode = (appState.activeMode || 'IDLE').toUpperCase();
      elModeBadge.textContent = mode;
      elModeBadge.className = `badge ${mode === 'MOCK' ? 'badge-amber' : (mode === 'REPLAY' ? 'badge-blue' : (mode === 'LIVE' ? 'badge-green' : 'badge-gray'))}`;
    }

    if (streamStatus) {
      streamStatus.textContent = `Streaming (${appState.wsStatus})`;
      streamStatus.className = `badge ${appState.wsStatus === 'CONNECTED' ? 'badge-green' : 'badge-amber'}`;
    }
  }

  async loadLatestObservation(systemId) {
    const status = document.getElementById('tel-stream-status');
    for (const id of ['tel-v', 'tel-i', 'tel-p', 'tel-temp', 'tel-soc', 'tel-soh', 'tel-ts']) {
      const el = document.getElementById(id);
      if (el) el.textContent = '—';
    }
    if (!systemId) {
      if (status) { status.textContent = 'Select a twin to load observations'; status.className = 'badge badge-gray'; }
      return;
    }
    if (status) { status.textContent = 'Loading latest observation…'; status.className = 'badge badge-blue'; }
    try {
      const history = await api.getTelemetryHistory(systemId, 1, true);
      const sample = Array.isArray(history) ? history[history.length - 1] : null;
      if (store.activeTwinId !== systemId) return;
      if (!sample) {
        if (status) { status.textContent = 'No telemetry observations recorded'; status.className = 'badge badge-gray'; }
        return;
      }
      const p = (Number.isFinite(sample.pack_voltage_v) && Number.isFinite(sample.pack_current_a))
        ? (sample.pack_voltage_v * sample.pack_current_a)
        : sample.pack_power_w;

      const soc = Number.isFinite(sample.soc_fraction) ? (sample.soc_fraction * 100).toFixed(1) + '%' : '—';
      const soh = Number.isFinite(sample.soh_fraction) ? (sample.soh_fraction * 100).toFixed(1) + '%' : 'Unavailable';

      const fields = {
        'tel-v': [sample.pack_voltage_v, 3],
        'tel-i': [sample.pack_current_a, 3],
        'tel-p': [p, 2],
        'tel-temp': [sample.ambient_temperature_c, 1],
      };
      Object.entries(fields).forEach(([id, [value, digits]]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = Number.isFinite(value) ? Number(value).toFixed(digits) : '—';
      });
      const elSoc = document.getElementById('tel-soc');
      const elSoh = document.getElementById('tel-soh');
      if (elSoc) elSoc.textContent = soc;
      if (elSoh) elSoh.textContent = soh;

      const timestamp = document.getElementById('tel-ts');
      if (timestamp) timestamp.textContent = Number.isFinite(sample.timestamp_ns)
        ? new Date(sample.timestamp_ns / 1e6).toLocaleString() : '—';
      if (status) { status.textContent = 'Persisted snapshot · source time below'; status.className = 'badge badge-gray'; }
    } catch (err) {
      if (status) { status.textContent = `History unavailable: ${err.message}`; status.className = 'badge badge-red'; }
    }
  }


  destroy() {}
}
