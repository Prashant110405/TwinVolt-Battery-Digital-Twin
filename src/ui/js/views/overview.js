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
        <!-- Section 1: Key Battery Metric Cards -->
        <div class="col-3">
          <div class="card metric-widget">
            <span class="metric-label">Model Voltage</span>
            <div class="metric-value-row">
              <span id="metric-model-v" class="metric-value">--</span>
              <span class="metric-unit">V</span>
            </div>
            <div class="metric-delta neutral" id="delta-voltage-res">Residual: -- V</div>
          </div>
        </div>

        <div class="col-3">
          <div class="card metric-widget">
            <span class="metric-label">Simulated SOC</span>
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
            <span class="metric-label">Core Temperature</span>
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
            <div class="metric-delta neutral" id="metric-anomalies">Anomalies: 0</div>
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
              <div class="chart-legend">
                <div class="legend-item">
                  <div class="legend-color-dot" style="background: #ef4444;"></div>
                  <span>Voltage Residual (V)</span>
                </div>
                <div class="legend-item">
                  <div class="legend-color-dot" style="background: #6366f1;"></div>
                  <span>Temp Residual (°C)</span>
                </div>
              </div>
            </div>
            <div class="chart-canvas-wrapper">
              <canvas id="chart-residuals" class="chart-canvas"></canvas>
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
          { key: 'model_v', label: 'Model V', color: '#38bdf8', lineWidth: 2 },
          { key: 'meas_v', label: 'Measured V', color: '#10b981', lineWidth: 1.5, dashed: true },
        ],
      });
    }

    const cvsSoc = document.getElementById('chart-soc');
    if (cvsSoc) {
      this.charts.soc = new StreamingChart(cvsSoc, {
        minY: 0,
        maxY: 100,
        series: [
          { key: 'sim_soc', label: 'Simulated SOC', color: '#06b6d4', lineWidth: 2 },
          { key: 'est_soc', label: 'Estimated SOC', color: '#8b5cf6', lineWidth: 1.5, dashed: true },
        ],
      });
    }

    const cvsT = document.getElementById('chart-temperature');
    if (cvsT) {
      this.charts.temperature = new StreamingChart(cvsT, {
        series: [
          { key: 'temp_c', label: 'Core Temp', color: '#f59e0b', lineWidth: 2 },
        ],
      });
    }

    const cvsRes = document.getElementById('chart-residuals');
    if (cvsRes) {
      this.charts.residuals = new StreamingChart(cvsRes, {
        series: [
          { key: 'v_res', label: 'Voltage Res', color: '#ef4444', lineWidth: 1.5 },
          { key: 't_res', label: 'Temp Res', color: '#6366f1', lineWidth: 1.5 },
        ],
      });
    }
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
  }

  update(changeType, appState) {
    if (changeType === 'STATE_UPDATED' && appState.latestState) {
      const s = appState.latestState;

      const elV = document.getElementById('metric-model-v');
      if (elV) elV.textContent = s.terminal_voltage_v !== undefined ? s.terminal_voltage_v.toFixed(3) : '--';

      const elSoc = document.getElementById('metric-soc');
      const prgSoc = document.getElementById('progress-soc');
      if (elSoc && s.simulated_soc !== undefined) {
        const pct = (s.simulated_soc * 100).toFixed(1);
        elSoc.textContent = pct;
        if (prgSoc) prgSoc.style.width = `${Math.min(100, Math.max(0, s.simulated_soc * 100))}%`;
      }

      const elT = document.getElementById('metric-temp');
      if (elT) elT.textContent = s.temperature_c !== undefined ? s.temperature_c.toFixed(1) : '--';

      const elSteps = document.getElementById('metric-steps');
      if (elSteps) elSteps.textContent = s.step_index || appState.stepCount;

      const elAnom = document.getElementById('metric-anomalies');
      if (elAnom) {
        elAnom.textContent = `Anomalies: ${s.anomalies_count || 0}`;
        if (s.anomalies_count > 0) {
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
    for (const chart of Object.values(this.charts)) {
      chart.destroy();
    }
  }
}
