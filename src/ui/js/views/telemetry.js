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
                    <td><span class="badge badge-gray">PERSISTED OBSERVATION</span></td>
                  </tr>
                  <tr>
                    <td>Pack Load Current</td>
                    <td id="tel-i" class="cell-mono">--</td>
                    <td class="cell-mono">A</td>
                    <td><span class="badge badge-gray">PERSISTED OBSERVATION</span></td>
                  </tr>
                  <tr>
                    <td>Reported Pack Power</td>
                    <td id="tel-p" class="cell-mono">--</td>
                    <td class="cell-mono">W</td>
                    <td><span class="badge badge-gray">PERSISTED OBSERVATION</span></td>
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
    }
  }

  async loadLatestObservation(systemId) {
    const status = document.getElementById('tel-stream-status');
    for (const id of ['tel-v', 'tel-i', 'tel-p', 'tel-ts']) {
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
      const fields = {
        'tel-v': [sample.pack_voltage_v, 3],
        'tel-i': [sample.pack_current_a, 3],
        'tel-p': [sample.pack_power_w, 2],
      };
      Object.entries(fields).forEach(([id, [value, digits]]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = Number.isFinite(value) ? Number(value).toFixed(digits) : '—';
      });
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
