/**
 * Overview View Component
 * Primary engineering workstation overview displaying battery gauges, twin comparison, and streaming charts.
 */

import { api } from '../api.js';
import { StreamingChart } from '../charts.js';
import { store } from '../state.js';
import { canonicalPipeline } from '../telemetry_pipeline.js';

export class OverviewView {
  constructor(container) {
    this.container = container;
    this.charts = {};
    this.animationFrameId = null;
    this.benchStreamInterval = null;
    this.init();
  }

  mount() {
    if (this.charts) {
      for (const chart of Object.values(this.charts)) {
        chart.resize();
        if (store.timeSeries) chart.render(store.timeSeries);
      }
    }
    if (store.activeTwinId && (!store.timeSeries || store.timeSeries.timestamps.length === 0)) {
      this._loadTwinHistory(store.activeTwinId);
    }
    this._updateHardwareReadings(store);
  }

  init() {
    this.container.innerHTML = `
      <div class="grid-12">
        <div class="col-12">
          <div id="overview-stream-status" class="stream-freshness" role="status" aria-live="polite">Awaiting twin connection state…</div>
        </div>

        <!-- Section: Live Hardware Sensor Telemetry Strip -->
        <div class="col-12">
          <div class="hw-strip-card">
            <div class="hw-strip-meta">
              <div id="overview-hw-badge" class="status-pill disconnected">
                <span class="indicator-dot"></span>
                <span id="overview-hw-badge-text">HARDWARE IDLE</span>
              </div>
              <div>
                <div class="hw-strip-title">LIVE HARDWARE SENSORS</div>
                <div id="overview-hw-source-text" class="hw-strip-source">(ESP32 / Arduino Prototype)</div>
              </div>
            </div>
            <div class="hw-strip-metrics">
              <div class="hw-strip-item">
                <span class="hw-strip-item-label">Measured Voltage</span>
                <div class="hw-strip-item-value-row">
                  <span id="overview-meas-v" class="hw-strip-item-val">--</span>
                  <span class="hw-strip-item-unit">V</span>
                </div>
              </div>
              <div class="hw-strip-item">
                <span class="hw-strip-item-label">Measured Current</span>
                <div class="hw-strip-item-value-row">
                  <span id="overview-meas-i" class="hw-strip-item-val">--</span>
                  <span class="hw-strip-item-unit">A</span>
                </div>
              </div>
              <div class="hw-strip-item">
                <span class="hw-strip-item-label">Measured Power</span>
                <div class="hw-strip-item-value-row">
                  <span id="overview-meas-p" class="hw-strip-item-val">--</span>
                  <span class="hw-strip-item-unit">W</span>
                </div>
              </div>
              <div class="hw-strip-item">
                <span class="hw-strip-item-label">Sensor Temp</span>
                <div class="hw-strip-item-value-row">
                  <span id="overview-meas-t" class="hw-strip-item-val">--</span>
                  <span class="hw-strip-item-unit">°C</span>
                </div>
              </div>
              <div id="overview-hw-actions" style="display: flex; gap: var(--space-2); align-items: center;">
                <button id="overview-btn-test-sample" class="btn btn-secondary btn-sm" title="Inject a single test hardware telemetry observation">
                  ⚡ Test Sample
                </button>
                <button id="overview-btn-stream-bench" class="btn btn-primary btn-sm" title="Toggle continuous 1 Hz live telemetry stream">
                  ▶️ Live Stream (1 Hz)
                </button>
              </div>
            </div>
          </div>
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
    this._bindEvents();
    this._updateHardwareReadings(store);
    if (store.activeTwinId) {
      this._loadTwinHistory(store.activeTwinId);
    }
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
    // Always refresh hardware readings strip on any hardware/telemetry event
    if (['HARDWARE_TELEMETRY', 'HARDWARE_STATE', 'HARDWARE_STATUS', 'USB_STATUS', 'BLE_STATUS', 'HARDWARE_STALE'].includes(changeType)) {
      this._updateHardwareReadings(appState);
    }
    if (['WS_STATUS', 'TWIN_CHANGED', 'STATE_UPDATED'].includes(changeType)) this._refreshStreamStatus();
    if (changeType === 'TWIN_CHANGED' || changeType === 'TWIN_STATUS') {
      if (changeType === 'TWIN_CHANGED' && appState.activeTwinId) {
        this._loadTwinHistory(appState.activeTwinId);
      }
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
        const measV = Number.isFinite(s.diagnostics?.telemetry_voltage_v) ? s.diagnostics.telemetry_voltage_v.toFixed(3) + ' V' : null;
        const resText = (s.voltage_residual_v !== null && s.voltage_residual_v !== undefined)
          ? `${(s.voltage_residual_v * 1000).toFixed(1)} mV` : '--';
        if (measV) {
          elVRes.textContent = `Meas: ${measV} · Res: ${resText}`;
        } else {
          elVRes.textContent = `Residual: ${resText}`;
        }
      }

      const elTRes = document.getElementById('delta-temp-res');
      if (elTRes) {
        const measT = Number.isFinite(s.diagnostics?.telemetry_temperature_c) ? s.diagnostics.telemetry_temperature_c.toFixed(1) + ' °C' : null;
        const resText = (s.temperature_residual_c !== null && s.temperature_residual_c !== undefined)
          ? `${s.temperature_residual_c.toFixed(2)} °C` : '--';
        if (measT) {
          elTRes.textContent = `Meas: ${measT} · Res: ${resText}`;
        } else {
          elTRes.textContent = `Residual: ${resText}`;
        }
      }
    }

    // Always keep physical hardware strip updated on any status change
    this._updateHardwareReadings(appState);
  }

  _bindEvents() {
    const btnTest = document.getElementById('overview-btn-test-sample');
    if (btnTest) {
      btnTest.addEventListener('click', async () => {
        btnTest.disabled = true;
        btnTest.textContent = '⏳ Injecting...';
        try {
          const sysId = store.activeTwinId || 'twin_prototype_3s1p';
          await api.ingestTelemetry({
            system_id: sysId,
            pack_voltage_v: 12.35,
            pack_current_a: 1.25,
            pack_power_w: 15.44,
            ambient_temperature_c: 26.5,
            source: 'LIVE_HARDWARE',
          });
          btnTest.textContent = '✓ Sample Ingested';
          setTimeout(() => {
            btnTest.disabled = false;
            btnTest.textContent = '⚡ Test Sample';
          }, 1500);
        } catch (err) {
          console.warn('[Overview] Test sample injection failed:', err);
          btnTest.textContent = '✗ Error';
          setTimeout(() => {
            btnTest.disabled = false;
            btnTest.textContent = '⚡ Test Sample';
          }, 2000);
        }
      });
    }

    const btnStream = document.getElementById('overview-btn-stream-bench');
    if (btnStream) {
      btnStream.addEventListener('click', () => this.toggleBenchStream());
    }
  }

  toggleBenchStream() {
    const btn = document.getElementById('overview-btn-stream-bench');
    if (this.benchStreamInterval) {
      clearInterval(this.benchStreamInterval);
      this.benchStreamInterval = null;
      if (btn) {
        btn.textContent = '▶️ Live Stream (1 Hz)';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-primary');
      }
      return;
    }

    if (btn) {
      btn.textContent = '⏹️ Stop Stream (1 Hz)';
      btn.classList.remove('btn-primary');
      btn.classList.add('btn-danger');
    }

    let step = store.stepCount || 10;
    const sendFrame = () => {
      step++;
      const v = 12.38 + Math.sin(step * 0.15) * 0.12 + (Math.random() - 0.5) * 0.02;
      const i = 1.22 + Math.cos(step * 0.15) * 0.18 + (Math.random() - 0.5) * 0.03;
      const t = 26.2 + (Math.sin(step * 0.05) * 1.5);
      const sysId = store.activeTwinId || 'twin_prototype_3s1p';
      // Push through the canonical pipeline so store.latestHardwareReading is set
      // and the UI hardware strip updates immediately.
      const rec = canonicalPipeline.ingest({
        pack_voltage_v: Number(v.toFixed(3)),
        pack_current_a: Number(i.toFixed(3)),
        ambient_temperature_c: Number(t.toFixed(1)),
        system_id: sysId,
      }, 'BENCH');
      if (!rec) console.warn('[Overview] Bench stream frame rejected by pipeline.');
    };

    sendFrame();
    this.benchStreamInterval = setInterval(sendFrame, 1000);
  }

  async _loadTwinHistory(systemId) {
    if (!systemId) return;
    try {
      const [stateHist, telHist] = await Promise.allSettled([
        api.getStateHistory(systemId, 100),
        api.getTelemetryHistory(systemId, 100),
      ]);

      const states = stateHist.status === 'fulfilled' && Array.isArray(stateHist.value) ? stateHist.value : [];
      const telemetries = telHist.status === 'fulfilled' && Array.isArray(telHist.value) ? telHist.value : [];

      const telByTs = new Map();
      telemetries.forEach((t) => {
        if (t.timestamp_ns) telByTs.set(t.timestamp_ns, t);
      });

      if (states.length > 0) {
        store.timeSeries.clear();
        for (const s of states) {
          const t = s.timestamp_ns / 1e9;
          const tel = telByTs.get(s.timestamp_ns) || telemetries[0];
          const measV = tel && Number.isFinite(tel.pack_voltage_v) ? tel.pack_voltage_v : null;
          const measI = tel && Number.isFinite(tel.pack_current_a) ? tel.pack_current_a : null;
          const measP = (measV !== null && measI !== null) ? Number((measV * measI).toFixed(3)) : null;

          const modelV = Number.isFinite(s.terminal_voltage_v)
            ? s.terminal_voltage_v
            : (measV !== null && Number.isFinite(s.residuals?.voltage_residual_v)
              ? measV - s.residuals.voltage_residual_v
              : 12.309);

          store.timeSeries.push(t, {
            model_v: modelV,
            sim_soc: Number.isFinite(s.soc_fraction) ? s.soc_fraction * 100 : null,
            est_soc: Number.isFinite(s.estimated_soc) ? s.estimated_soc * 100 : null,
            temp_c: Number.isFinite(s.temperature_c) ? s.temperature_c : 25.0,
            v_res: Number.isFinite(s.residuals?.voltage_residual_v) ? s.residuals.voltage_residual_v : null,
            t_res: Number.isFinite(s.residuals?.temp_residual_c) ? s.residuals.temp_residual_c : null,
            meas_v: measV,
            meas_i: measI,
            meas_p: measP,
          });
        }

        const lastTel = telemetries[telemetries.length - 1];
        if (lastTel && (!store.latestHardwareReading || !store.latestHardwareReading.voltage_v)) {
          store.latestHardwareReading = {
            transport: 'STORED',
            voltage_v: lastTel.pack_voltage_v,
            current_a: lastTel.pack_current_a,
            power_w: (lastTel.pack_voltage_v && lastTel.pack_current_a) ? lastTel.pack_voltage_v * lastTel.pack_current_a : null,
            temperature_c: lastTel.ambient_temperature_c || lastTel.avg_cell_temperature_c,
            receivedAt: Date.now(),
          };
        }

        if (this.charts) {
          for (const chart of Object.values(this.charts)) {
            chart.render(store.timeSeries);
          }
        }

        this._updateHardwareReadings(store);
      }
    } catch (err) {
      console.warn('[Overview] Failed to load twin history:', err);
    }
  }

  _updateHardwareReadings(appState) {
    const elV = document.getElementById('overview-meas-v');
    const elI = document.getElementById('overview-meas-i');
    const elP = document.getElementById('overview-meas-p');
    const elT = document.getElementById('overview-meas-t');
    const elBadge = document.getElementById('overview-hw-badge');
    const elBadgeText = document.getElementById('overview-hw-badge-text');
    const elSource = document.getElementById('overview-hw-source-text');
    if (!elV) return;

    const s = appState?.latestState;
    const hw = appState?.latestHardwareReading;
    // Use pipeline state machine objects (populated by WebSerial/BLE managers)
    const usbSt = appState?.usbStatus || {};
    const bleSt = appState?.bleStatus || {};
    // Also allow legacy REST status as fallback
    const serial = appState?.hardwareStatus;

    const ACTIVE_STATES = ['STREAMING', 'CONNECTED_NO_DATA'];

    let v = null;
    let i = null;
    let p = null;
    let t = null;
    let transport = null;
    let isConnected = false;

    // Priority 1: live hardware reading from pipeline (USB or BLE)
    if (hw && Number.isFinite(hw.voltage_v)) {
      v = hw.voltage_v;
      i = Number.isFinite(hw.current_a) ? hw.current_a : null;
      p = Number.isFinite(hw.power_w) ? hw.power_w : ((v !== null && i !== null) ? v * i : null);
      t = Number.isFinite(hw.temperature_c) ? hw.temperature_c : null;
      transport = hw.transport || hw.sourceBadge;
      isConnected = true;
    // Priority 2: twin state diagnostics (set by backend co-simulation)
    } else if (s && s.diagnostics && Number.isFinite(s.diagnostics.telemetry_voltage_v)) {
      v = s.diagnostics.telemetry_voltage_v;
      i = Number.isFinite(s.diagnostics.telemetry_current_a) ? s.diagnostics.telemetry_current_a : null;
      p = (v !== null && i !== null) ? v * i : null;
      t = Number.isFinite(s.diagnostics.telemetry_temperature_c) ? s.diagnostics.telemetry_temperature_c : null;
      transport = s.source || appState.activeTransport;
      isConnected = true;
    }

    // Determine connection state even when no reading yet (port open, awaiting frames)
    if (!isConnected) {
      if (appState?.activeTransport === 'BLE') {
        isConnected = ACTIVE_STATES.includes(bleSt.state);
        transport = 'BLE';
      } else {
        // Check pipeline USB state first, then legacy REST
        isConnected = ACTIVE_STATES.includes(usbSt.state) ||
                      (serial && ACTIVE_STATES.includes(serial.state)) ||
                      (serial && serial.state === 'CONNECTED');
        transport = 'SERIAL';
      }
    }

    elV.textContent = v !== null ? v.toFixed(3) : '--';
    elI.textContent = i !== null ? i.toFixed(3) : '--';
    elP.textContent = p !== null ? p.toFixed(2) : '--';
    elT.textContent = t !== null ? t.toFixed(1) : '--';

    const toggleStreaming = (el, isStreaming) => {
      if (el) {
        if (isStreaming) el.classList.add('streaming');
        else el.classList.remove('streaming');
      }
    };
    toggleStreaming(elV, v !== null);
    toggleStreaming(elI, i !== null);
    toggleStreaming(elP, p !== null);
    toggleStreaming(elT, t !== null);

    if (elBadge && elBadgeText) {
      if (v !== null) {
        elBadge.className = 'status-pill streaming';
        const tLabel = typeof transport === 'string' ? transport.replace('_', ' ') : 'LIVE';
        elBadgeText.textContent = `STREAMING · ${tLabel}`;
      } else if (isConnected) {
        elBadge.className = 'status-pill connected_no_data';
        const portInfo = transport === 'SERIAL' && serial?.port ? ` · ${serial.port}` :
                         (usbSt.portName ? ` · ${usbSt.portName}` : '');
        elBadgeText.textContent = `PORT OPEN${portInfo} · AWAITING FRAMES`;
      } else {
        elBadge.className = 'status-pill disconnected';
        elBadgeText.textContent = 'HARDWARE DISCONNECTED';
      }
    }

    if (elSource) {
      const isBleTrans = transport === 'BLE' || transport === 'REAL HARDWARE — BLE';
      const isUsbTrans = transport === 'USB_SERIAL' || transport === 'REAL HARDWARE — USB' || transport === 'SERIAL';
      const isBench = transport === 'BENCH' || transport === 'SIMULATION';
      if (isBleTrans) {
        elSource.textContent = `(Web Bluetooth · ${bleSt.deviceName || 'Twin Volt'})`;
      } else if (isBench) {
        elSource.textContent = '(Bench Simulation — No hardware connected)';
      } else if (isUsbTrans) {
        const port = usbSt.portName || serial?.port;
        elSource.textContent = `(USB Serial${port ? ` · ${port}` : ''})`;
      } else if (isConnected) {
        elSource.textContent = '(ESP32 / Arduino — Live Connection)';
      } else {
        elSource.textContent = '(ESP32 / Arduino Prototype)';
      }
    }
  }

  destroy() {
    if (this.benchStreamInterval) {
      clearInterval(this.benchStreamInterval);
      this.benchStreamInterval = null;
    }
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
    if (this.freshnessTimer) clearInterval(this.freshnessTimer);
    for (const chart of Object.values(this.charts)) {
      chart.destroy();
    }
  }
}
