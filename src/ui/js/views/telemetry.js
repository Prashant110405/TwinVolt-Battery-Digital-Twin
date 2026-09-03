/**
 * Live Telemetry View Component
 * Observes raw and canonical incoming observations with developer test ingestion controls.
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
              <span class="card-title">Live Telemetry Observation Stream</span>
              <span id="tel-stream-status" class="badge badge-cyan">Listening</span>
            </div>
            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Observation Metric</th>
                    <th>Current Value</th>
                    <th>Unit</th>
                    <th>Source & Quality</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Pack Terminal Voltage</td>
                    <td id="tel-v" class="cell-mono">--</td>
                    <td class="cell-mono">V</td>
                    <td><span class="badge badge-cyan">TELEMETRY</span></td>
                  </tr>
                  <tr>
                    <td>Pack Load Current</td>
                    <td id="tel-i" class="cell-mono">--</td>
                    <td class="cell-mono">A</td>
                    <td><span class="badge badge-cyan">TELEMETRY</span></td>
                  </tr>
                  <tr>
                    <td>Calculated Load Power</td>
                    <td id="tel-p" class="cell-mono">--</td>
                    <td class="cell-mono">W</td>
                    <td><span class="badge badge-blue">CLIENT-DERIVED (V×I)</span></td>
                  </tr>
                  <tr>
                    <td>Ambient / Surface Temperature</td>
                    <td id="tel-temp" class="cell-mono">--</td>
                    <td class="cell-mono">°C</td>
                    <td><span class="badge badge-cyan">TELEMETRY</span></td>
                  </tr>
                  <tr>
                    <td>Observation Epoch Timestamp</td>
                    <td id="tel-ts" class="cell-mono">--</td>
                    <td class="cell-mono">ns</td>
                    <td><span class="badge badge-cyan">HEADER</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="col-4">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Manual Telemetry Injector</span>
              <span class="badge badge-amber">TEST MODE</span>
            </div>
            <p class="card-subtitle" style="margin-bottom: var(--space-3);">
              Inject test observations directly into the active twin through the existing TelemetryIngestService.
            </p>
            <form id="form-inject-telemetry">
              <div class="form-group">
                <label class="form-label" for="input-inject-v">Pack Voltage (V)</label>
                <input id="input-inject-v" class="form-input" type="number" step="0.01" value="3.60" required />
              </div>
              <div class="form-group">
                <label class="form-label" for="input-inject-i">Pack Current (A)</label>
                <input id="input-inject-i" class="form-input" type="number" step="0.01" value="1.50" required />
              </div>
              <div class="form-group">
                <label class="form-label" for="input-inject-temp">Temperature (°C)</label>
                <input id="input-inject-temp" class="form-input" type="number" step="0.1" value="25.0" />
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
  }

  _bindEvents() {
    const form = document.getElementById('form-inject-telemetry');
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const v = parseFloat(document.getElementById('input-inject-v').value);
        const i = parseFloat(document.getElementById('input-inject-i').value);
        const temp = parseFloat(document.getElementById('input-inject-temp').value);
        const statusEl = document.getElementById('inject-status-msg');

        if (!store.activeTwinId) {
          if (statusEl) {
            statusEl.textContent = 'Error: No active digital twin selected.';
            statusEl.style.color = 'var(--color-danger)';
          }
          return;
        }

        try {
          if (wsClient.ws && wsClient.ws.readyState === WebSocket.OPEN) {
            wsClient.sendTelemetry({
              pack_voltage_v: v,
              pack_current_a: i,
              ambient_temperature_c: temp,
              timestamp_ns: Date.now() * 1_000_000,
            });
            if (statusEl) {
              statusEl.textContent = `Injected via WebSocket for ${store.activeTwinId}.`;
              statusEl.style.color = 'var(--color-success)';
            }
          } else {
            await api.ingestTelemetry({
              system_id: store.activeTwinId,
              pack_voltage_v: v,
              pack_current_a: i,
              ambient_temperature_c: temp,
              timestamp_ns: Date.now() * 1_000_000,
            });
            if (statusEl) {
              statusEl.textContent = `Injected via REST for ${store.activeTwinId}.`;
              statusEl.style.color = 'var(--color-success)';
            }
          }
        } catch (err) {
          if (statusEl) {
            statusEl.textContent = `Injection failed: ${err.message}`;
            statusEl.style.color = 'var(--color-danger)';
          }
        }
      });
    }
  }

  update(changeType, appState) {
    if (changeType === 'STATE_UPDATED' && appState.latestState) {
      const s = appState.latestState;
      const vEl = document.getElementById('tel-v');
      const iEl = document.getElementById('tel-i');
      const pEl = document.getElementById('tel-p');
      const tEl = document.getElementById('tel-temp');
      const tsEl = document.getElementById('tel-ts');

      const v = s.diagnostics?.telemetry_voltage_v ?? s.terminal_voltage_v;
      const i = s.diagnostics?.telemetry_current_a ?? null;

      if (vEl && v !== null && v !== undefined) vEl.textContent = Number(v).toFixed(3);
      if (iEl && i !== null && i !== undefined) iEl.textContent = Number(i).toFixed(3);
      if (pEl && v !== null && i !== null && v !== undefined && i !== undefined) {
        pEl.textContent = (Number(v) * Number(i)).toFixed(2);
      }
      if (tEl && s.temperature_c !== undefined) tEl.textContent = Number(s.temperature_c).toFixed(1);
      if (tsEl && s.timestamp_ns) tsEl.textContent = s.timestamp_ns;
    }
  }

  destroy() {}
}
