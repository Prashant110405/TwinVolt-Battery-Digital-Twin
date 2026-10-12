/**
 * Overview View Component
 * Primary engineering workstation overview displaying battery gauges, twin comparison, and streaming charts.
 */

import { StreamingChart } from '../charts.js';
import { store } from '../state.js';

export class OverviewView {
  constructor(container) {
    this.container = container;
    this.charts = {};
    this.animationFrameId = null;
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="grid-12">
        <div class="col-12">
          <div id="overview-stream-status" class="stream-freshness" role="status" aria-live="polite">Awaiting twin connection state…</div>
        </div>
        <!-- Section 1: Key Battery Metric Cards -->
        <div class="col-3">
          <div class="card metric-widget">
            <span class="metric-label">Model Voltage · simulated</span>
            <div class="metric-value-row">
              <span id="metric-model-v" class="metric-value">--</span>
              <span class="metric-unit">V</span>
            </div>
            <div class="metric-delta neutral" id="delta-voltage-res">Modeled output · awaiting data</div>
          </div>
        </div>

        <div class="col-3">
          <div class="card metric-widget">
            <span class="metric-label">State of Charge · simulated</span>
            <div class="metric-value-row">
              <span id="metric-soc" class="metric-value">--</span>
              <span class="metric-unit">%</span>
            </div>
            <div class="progress-bar-container">
              <div id="progress-soc" class="progress-bar-fill" style="width: 0%;"></div>
            </div>
          </div>
        </div>

        <div class="col-3">
          <div class="card metric-widget">
            <span class="metric-label">Core Temperature · modeled</span>
            <div class="metric-value-row">
              <span id="metric-temp" class="metric-value">--</span>
              <span class="metric-unit">°C</span>
            </div>
            <div class="metric-delta neutral" id="delta-temp-res">Residual: -- °C</div>
          </div>
        </div>

        <div class="col-3">
          <div class="card metric-widget">
            <span class="metric-label">Simulation Steps</span>
            <div class="metric-value-row">
              <span id="metric-steps" class="metric-value">0</span>
              <span class="metric-unit">cycles</span>
            </div>
            <div class="metric-delta neutral" id="metric-anomalies">Anomalies: —</div>
          </div>
        </div>

        <!-- Section 2: Real-Time Charts -->
        <div class="col-6">
          <div class="card chart-card">
            <div class="chart-header">
              <span class="card-title">Voltage Tracking (V)</span>
              <div class="chart-legend">
                <div class="legend-item">
                  <div class="legend-color-dot" style="background: #38bdf8;"></div>
                  <span>Model V</span>
                </div>
                <div class="legend-item">
                  <div class="legend-color-dot" style="background: #10b981;"></div>
                  <span>Measured V</span>
                </div>
              </div>
            </div>
            <div class="chart-canvas-wrapper">
              <canvas id="chart-voltage" class="chart-canvas"></canvas>
            </div>
          </div>
        </div>

        <div class="col-6">
          <div class="card chart-card">
            <div class="chart-header">
              <span class="card-title">State of Charge (%)</span>
              <div class="chart-legend">
                <div class="legend-item">
                  <div class="legend-color-dot" style="background: #06b6d4;"></div>
                  <span>Simulated SOC</span>
                </div>
                <div class="legend-item">
                  <div class="legend-color-dot" style="background: #8b5cf6;"></div>
                  <span>Estimated SOC</span>
                </div>
              </div>
            </div>
            <div class="chart-canvas-wrapper">
              <canvas id="chart-soc" class="chart-canvas"></canvas>
            </div>
          </div>
        </div>

        <div class="col-6">
          <div class="card chart-card">
            <div class="chart-header">
              <span class="card-title">Thermal Dynamics (°C)</span>
              <div class="chart-legend">
                <div class="legend-item">
                  <div class="legend-color-dot" style="background: #f59e0b;"></div>
                  <span>Core Temp</span>
                </div>
              </div>
            </div>
            <div class="chart-canvas-wrapper">
              <canvas id="chart-temperature" class="chart-canvas"></canvas>
            </div>
          </div>
        </div>

        <div class="col-6">
          <div class="card chart-card">
            <div class="chart-header">
              <span class="card-title">Tracking Residuals</span>
            </div>
            <div class="residual-grid">
              <section aria-label="Voltage residual in volts">
                <h3 class="residual-title">Voltage residual · V</h3>
                <div class="chart-canvas-wrapper"><canvas id="chart-residual-v" class="chart-canvas"></canvas></div>
              </section>
              <section aria-label="Temperature residual in degrees Celsius">
                <h3 class="residual-title">Temperature residual · °C</h3>
                <div class="chart-canvas-wrapper"><canvas id="chart-residual-t" class="chart-canvas"></canvas></div>
              </section>
            </div>
          </div>
        </div>
      </div>
    `;

    this._initCharts();
    this._startRenderLoop();
  }

  _initCharts() {
    const cvsV = document.getElementById('chart-voltage');
    if (cvsV) {
      this.charts.voltage = new StreamingChart(cvsV, {
        series: [
          { key: 'model_v', label: 'Model V', color: '#2563eb', lineWidth: 2 },
          { key: 'meas_v', label: 'Measured V', color: '#16865c', lineWidth: 1.5, dashed: true },
        ],
      });
    }

    const cvsSoc = document.getElementById('chart-soc');
    if (cvsSoc) {
      this.charts.soc = new StreamingChart(cvsSoc, {
        minY: 0,
        maxY: 100,
        autoScale: false,
        series: [
          { key: 'sim_soc', label: 'Simulated SOC', color: '#0f8f9a', lineWidth: 2 },
          { key: 'est_soc', label: 'Estimated SOC', color: '#7653c6', lineWidth: 1.5, dashed: true },
        ],
      });
    }

    const cvsT = document.getElementById('chart-temperature');
    if (cvsT) {
      this.charts.temperature = new StreamingChart(cvsT, {
        series: [
          { key: 'temp_c', label: 'Core Temp', color: '#bd6b13', lineWidth: 2 },
        ],
      });
    }

    const cvsVRes = document.getElementById('chart-residual-v');
    if (cvsVRes) this.charts.voltageResidual = new StreamingChart(cvsVRes, {
      series: [{ key: 'v_res', label: 'Voltage residual (V)', color: '#c43f48', lineWidth: 1.5 }],
    });
    const cvsTRes = document.getElementById('chart-residual-t');
    if (cvsTRes) this.charts.temperatureResidual = new StreamingChart(cvsTRes, {
      series: [{ key: 't_res', label: 'Temperature residual (°C)', color: '#5546c7', lineWidth: 1.5 }],
    });
  }

  _startRenderLoop() {
    const render = () => {
      if (store.timeSeries && this.charts) {
        for (const chart of Object.values(this.charts)) {
          chart.render(store.timeSeries);
        }
      }
      this.animationFrameId = requestAnimationFrame(render);
    };
    this.animationFrameId = requestAnimationFrame(render);
    this.freshnessTimer = setInterval(() => this._refreshStreamStatus(), 1000);
    this._refreshStreamStatus();
  }

  _refreshStreamStatus() {
    const el = document.getElementById('overview-stream-status');
    if (!el) return;
    if (store.twinLoadError) {
      el.textContent = `Twin data unavailable: ${store.twinLoadError}`;
      el.dataset.connection = 'error';
      return;
    }
    if (!store.activeTwinId) {
      el.textContent = 'No twin selected · no live twin state';
      el.dataset.connection = 'disconnected';
      return;
    }
    const age = store.lastStateReceivedAtMs === null
      ? null : Math.max(0, Math.floor((Date.now() - store.lastStateReceivedAtMs) / 1000));
    const ageText = age === null ? 'no state received in this session' : `last state received ${age < 2 ? 'just now' : `${age}s ago`}`;
    const connected = store.wsStatus === 'CONNECTED';
    const connectionLabel = connected ? 'WebSocket connected' : `WebSocket ${store.wsStatus.toLowerCase().replace('_', ' ')}`;
    el.textContent = `${connectionLabel} · ${ageText}`;
    el.dataset.connection = connected ? 'connected' : 'disconnected';
  }

  update(changeType, appState) {
    if (['WS_STATUS', 'TWIN_CHANGED', 'STATE_UPDATED'].includes(changeType)) this._refreshStreamStatus();
    if (changeType === 'TWIN_CHANGED' || changeType === 'TWIN_STATUS') {
      const twin = appState.activeTwinStatus;
      const setMetric = (id, value, digits) => {
        const el = document.getElementById(id);
        if (el) el.textContent = Number.isFinite(value) ? Number(value).toFixed(digits) : '—';
      };
      if (twin) {
        setMetric('metric-model-v', twin.current_voltage_v, 3);
        setMetric('metric-soc', Number.isFinite(twin.current_soc) ? twin.current_soc * 100 : null, 1);
        setMetric('metric-temp', twin.current_temperature_c, 1);
        const steps = document.getElementById('metric-steps');
        if (steps) steps.textContent = Number.isFinite(twin.total_steps) ? twin.total_steps : '—';
        const anomaly = document.getElementById('metric-anomalies');
        if (anomaly) anomaly.textContent = `Anomalies: ${Number.isFinite(twin.total_anomalies) ? twin.total_anomalies : '—'}`;
        const progress = document.getElementById('progress-soc');
        if (progress) progress.style.width = Number.isFinite(twin.current_soc) ? `${Math.min(100, Math.max(0, twin.current_soc * 100))}%` : '0%';
      }
    }
    if (changeType === 'TWIN_CHANGED' && !appState.latestState) {
      for (const id of ['metric-model-v', 'metric-soc', 'metric-temp']) {
        const el = document.getElementById(id);
        if (el) el.textContent = '—';
      }
      const steps = document.getElementById('metric-steps');
      if (steps) steps.textContent = appState.activeTwinId ? appState.stepCount : '—';
      const anomalies = document.getElementById('metric-anomalies');
      if (anomalies) anomalies.textContent = `Anomalies: ${Number.isFinite(appState.anomaliesCount) ? appState.anomaliesCount : '—'}`;
      const soc = document.getElementById('progress-soc');
      if (soc) soc.style.width = '0%';
      for (const id of ['delta-voltage-res', 'delta-temp-res']) {
        const el = document.getElementById(id);
        if (el) el.textContent = 'Residual: —';
      }
    }
    if (changeType === 'STATE_UPDATED' && appState.latestState) {
      const s = appState.latestState;

      const elV = document.getElementById('metric-model-v');
      if (elV) elV.textContent = Number.isFinite(s.terminal_voltage_v) ? s.terminal_voltage_v.toFixed(3) : '—';

      const elSoc = document.getElementById('metric-soc');
      const prgSoc = document.getElementById('progress-soc');
      if (elSoc && s.simulated_soc !== undefined) {
        const pct = (s.simulated_soc * 100).toFixed(1);
        elSoc.textContent = pct;
        if (prgSoc) prgSoc.style.width = `${Math.min(100, Math.max(0, s.simulated_soc * 100))}%`;
      }

      const elT = document.getElementById('metric-temp');
      if (elT) elT.textContent = Number.isFinite(s.temperature_c) ? s.temperature_c.toFixed(1) : '—';

      const elSteps = document.getElementById('metric-steps');
      if (elSteps) elSteps.textContent = Number.isFinite(s.step_index) ? s.step_index : '—';

      const elAnom = document.getElementById('metric-anomalies');
      if (elAnom) {
        elAnom.textContent = `Anomalies: ${Number.isFinite(s.anomalies_count) ? s.anomalies_count : '—'}`;
        if (Number.isFinite(s.anomalies_count) && s.anomalies_count > 0) {
          elAnom.className = 'metric-delta negative';
        } else {
          elAnom.className = 'metric-delta neutral';
        }
      }

      const elVRes = document.getElementById('delta-voltage-res');
      if (elVRes) {
        if (s.voltage_residual_v !== null && s.voltage_residual_v !== undefined) {
          elVRes.textContent = `Residual: ${(s.voltage_residual_v * 1000).toFixed(1)} mV`;
        } else {
          elVRes.textContent = 'Residual: --';
        }
      }

      const elTRes = document.getElementById('delta-temp-res');
      if (elTRes) {
        if (s.temperature_residual_c !== null && s.temperature_residual_c !== undefined) {
          elTRes.textContent = `Residual: ${s.temperature_residual_c.toFixed(2)} °C`;
        } else {
          elTRes.textContent = 'Residual: --';
        }
      }
    }
  }

  destroy() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
    if (this.freshnessTimer) clearInterval(this.freshnessTimer);
    for (const chart of Object.values(this.charts)) {
      chart.destroy();
    }
  }
}
