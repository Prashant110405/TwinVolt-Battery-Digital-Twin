/**
 * Digital Twin View Component
 * Inspects digital twin model configuration, initialization state, and pack assembly properties.
 */

import { api } from '../api.js';
import { store } from '../state.js';

export class TwinView {
  constructor(container) {
    this.container = container;
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="grid-12">
        <!-- Digital Twin Lifecycle Controls -->
        <div class="col-6">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Digital Twin Runtime Lifecycle</span>
              <span id="twin-init-badge" class="badge badge-purple">Status: Uninitialized</span>
            </div>
            <div class="data-table-container">
              <table class="data-table">
                <tbody>
                  <tr>
                    <td>Active System Identifier</td>
                    <td id="twin-info-id" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Bound Pack Identifier</td>
                    <td id="twin-info-pack-id" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Simulation Model Paradigm</td>
                    <td id="twin-info-model" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Initialization State</td>
                    <td id="twin-info-init" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Executed Simulation Cycles</td>
                    <td id="twin-info-steps" class="cell-mono">0</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="twin-init-fields">
              <label class="form-label" for="twin-initial-soc">Initial SOC (%)</label>
              <input id="twin-initial-soc" class="form-input" type="number" min="0" max="100" step="0.1" placeholder="Required" />
              <label class="form-label" for="twin-initial-temp">Initial model temperature (°C)</label>
              <input id="twin-initial-temp" class="form-input" type="number" step="0.1" placeholder="Required" />
            </div>
            <div style="display: flex; gap: var(--space-3); margin-top: var(--space-4);">
              <button id="btn-init-twin" class="btn btn-primary btn-sm">Initialize model</button>
              <button id="btn-reset-twin" class="btn btn-secondary btn-sm">Reset State</button>
            </div>
          </div>
        </div>

        <!-- Bound Battery Pack Specification -->
        <div class="col-6">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Constituent Battery Pack Domain Assembly</span>
              <span id="pack-chem-badge" class="badge badge-cyan">Chemistry: --</span>
            </div>
            <div class="data-table-container">
              <table class="data-table">
                <tbody>
                  <tr>
                    <td>Display Name / Model</td>
                    <td id="pack-spec-name" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Manufacturer</td>
                    <td id="pack-spec-mfg" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Topology Architecture</td>
                    <td id="pack-spec-topo" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Total Cell Count</td>
                    <td id="pack-spec-cells" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Nominal Ratings</td>
                    <td id="pack-spec-ratings" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Voltage Operating Limits</td>
                    <td id="pack-spec-limits" class="cell-mono">--</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Detailed Model Parameter Status -->
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Model State & Parameters</span>
              <span class="badge badge-amber">INSPECTION</span>
            </div>
            <div class="grid-12">
              <div class="col-4">
                <div class="metric-widget">
                  <span class="metric-label">Current Model Voltage</span>
                  <div class="metric-value-row">
                    <span id="twin-v-readout" class="metric-value">--</span>
                    <span class="metric-unit">V</span>
                  </div>
                </div>
              </div>
              <div class="col-4">
                <div class="metric-widget">
                  <span class="metric-label">Current Simulated SOC</span>
                  <div class="metric-value-row">
                    <span id="twin-soc-readout" class="metric-value">--</span>
                    <span class="metric-unit">%</span>
                  </div>
                </div>
              </div>
              <div class="col-4">
                <div class="metric-widget">
                  <span class="metric-label">Internal ECM RC Parameters</span>
                  <p class="unavailable-text" style="margin-top: var(--space-2);">
                    Not exposed by current API contract
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
  }

  _bindEvents() {
    const btnInit = document.getElementById('btn-init-twin');
    if (btnInit) {
      btnInit.addEventListener('click', async () => {
        if (!store.activeTwinId) return;
        const soc = Number(document.getElementById('twin-initial-soc')?.value);
        const temperature = Number(document.getElementById('twin-initial-temp')?.value);
        if (!Number.isFinite(soc) || soc < 0 || soc > 100 || !Number.isFinite(temperature)) {
          this.showActionError('Enter a valid initial SOC (0–100%) and model temperature.');
          return;
        }
        this.setPending(true);
        try {
          await api.initializeTwin(store.activeTwinId, { initial_soc: soc / 100, temperature_c: temperature });
          const status = await api.getTwin(store.activeTwinId);
          store.setActiveTwin(store.activeTwinId, status);
        } catch (err) {
          this.showActionError(`Failed to initialize twin: ${err.message}`);
        } finally {
          this.setPending(false);
        }
      });
    }

    const btnReset = document.getElementById('btn-reset-twin');
    if (btnReset) {
      btnReset.addEventListener('click', async () => {
        if (!store.activeTwinId) return;
        if (!window.confirm(`Reset model and estimator state for twin “${store.activeTwinId}”?`)) return;
        this.setPending(true);
        try {
          await api.resetTwin(store.activeTwinId);
          const status = await api.getTwin(store.activeTwinId);
          store.setActiveTwin(store.activeTwinId, status);
        } catch (err) {
          this.showActionError(`Failed to reset twin: ${err.message}`);
        } finally {
          this.setPending(false);
        }
      });
    }
  }

  update(changeType, appState) {
    if (changeType === 'TWIN_CHANGED' && !appState.activePack) {
      for (const id of ['pack-spec-name', 'pack-spec-mfg', 'pack-spec-topo', 'pack-spec-cells', 'pack-spec-ratings', 'pack-spec-limits']) {
        const el = document.getElementById(id);
        if (el) el.textContent = '—';
      }
      const chemistry = document.getElementById('pack-chem-badge');
      if (chemistry) chemistry.textContent = 'Chemistry: —';
    }
    if (appState.activeTwinStatus) {
      const st = appState.activeTwinStatus;
      const elId = document.getElementById('twin-info-id');
      const elPack = document.getElementById('twin-info-pack-id');
      const elMod = document.getElementById('twin-info-model');
      const elInit = document.getElementById('twin-info-init');
      const elBadge = document.getElementById('twin-init-badge');
      const elSteps = document.getElementById('twin-info-steps');

      if (elId) elId.textContent = st.system_id || '--';
      if (elPack) elPack.textContent = st.pack_id || '--';
      if (elMod) elMod.textContent = st.model_name || '—';
      if (elInit) elInit.textContent = st.is_initialized ? 'Initialized' : 'Uninitialized';
      if (elBadge) {
        elBadge.textContent = st.is_initialized ? 'ACTIVE / INITIALIZED' : 'UNINITIALIZED';
        elBadge.className = st.is_initialized ? 'badge badge-cyan' : 'badge badge-amber';
      }
      if (elSteps) elSteps.textContent = Number.isFinite(st.total_steps) ? st.total_steps : '—';
    }

    if (appState.activePack) {
      const p = appState.activePack;
      const elChem = document.getElementById('pack-chem-badge');
      const elName = document.getElementById('pack-spec-name');
      const elMfg = document.getElementById('pack-spec-mfg');
      const elTopo = document.getElementById('pack-spec-topo');
      const elCells = document.getElementById('pack-spec-cells');
      const elRatings = document.getElementById('pack-spec-ratings');
      const elLimits = document.getElementById('pack-spec-limits');

      if (elChem) elChem.textContent = `Chemistry: ${p.chemistry || '--'}`;
      if (elName) elName.textContent = p.display_name || p.pack_id || '--';
      if (elMfg) elMfg.textContent = p.manufacturer || '—';
      if (elTopo) elTopo.textContent = Number.isFinite(p.series_count) && Number.isFinite(p.parallel_count)
        ? `${p.series_count}S ${p.parallel_count}P (${Number.isFinite(p.total_module_count) ? `${p.total_module_count} module(s)` : 'module count —'})` : '—';
      if (elCells) elCells.textContent = Number.isFinite(p.total_cell_count) ? `${p.total_cell_count} cells` : '—';
      if (elRatings) elRatings.textContent = Number.isFinite(p.nominal_voltage_v) && Number.isFinite(p.nominal_capacity_ah)
        ? `${p.nominal_voltage_v} V | ${p.nominal_capacity_ah} Ah${Number.isFinite(p.nominal_energy_wh) ? ` (${p.nominal_energy_wh} Wh)` : ''}` : '—';
      if (elLimits) elLimits.textContent = Number.isFinite(p.min_pack_voltage_v) && Number.isFinite(p.max_pack_voltage_v)
        ? `${p.min_pack_voltage_v} V – ${p.max_pack_voltage_v} V` : '—';
    }

    if (appState.latestState) {
      const s = appState.latestState;
      const elV = document.getElementById('twin-v-readout');
      const elSoc = document.getElementById('twin-soc-readout');
      if (elV && s.terminal_voltage_v !== undefined) elV.textContent = Number(s.terminal_voltage_v).toFixed(3);
      if (elSoc && s.simulated_soc !== undefined) elSoc.textContent = (s.simulated_soc * 100).toFixed(1);
    }
  }

  setPending(pending) {
    for (const id of ['btn-init-twin', 'btn-reset-twin']) {
      const button = document.getElementById(id);
      if (button) button.disabled = pending;
    }
  }

  showActionError(message) {
    let output = document.getElementById('twin-action-error');
    if (!output) {
      output = document.createElement('p');
      output.id = 'twin-action-error';
      output.className = 'action-message error';
      output.setAttribute('role', 'alert');
      document.querySelector('#view-twin .card')?.append(output);
    }
    output.textContent = message;
  }

  destroy() {}
}
