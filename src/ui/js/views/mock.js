/**
 * Isolated Mock Telemetry Generator View
 *
 * Provides controls for running synthetic battery telemetry, adjusting simulation
 * parameters, injecting test faults, and verifying UI responses without hardware.
 */

import { api } from '../api.js';
import { store } from '../state.js';

export class MockView {
  constructor(container) {
    this.container = container;
    this.status = null;
    this.pollTimer = null;
    this._initDom();
    this._bindEvents();
  }

  _initDom() {
    this.container.innerHTML = `
      <div class="hw-header-bar">
        <div>
          <div class="eyebrow">SYNTHETIC LAB & TESTING MODE</div>
          <h1 style="font-size: var(--text-2xl); font-weight: 700; margin: 0;">Mock Data Generator</h1>
        </div>
        <div style="display: flex; gap: var(--space-2); align-items: center;">
          <div id="mock-state-badge" class="mode-pill mode-mock">
            <span class="mode-dot"></span>
            MOCK IDLE
          </div>
          <button id="mock-btn-start" class="btn btn-primary btn-sm">▶ Start Generator</button>
          <button id="mock-btn-stop" class="btn btn-secondary btn-sm" disabled>⏹ Stop</button>
        </div>
      </div>

      <div style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: var(--radius-md); padding: var(--space-3); margin-bottom: var(--space-4); font-size: var(--text-xs); color: var(--text-secondary); line-height: 1.5;">
        <strong style="color: #f59e0b;">🛡️ Isolation Guarantee:</strong>
        Mock data is strictly stamped with <code>source_mode="MOCK"</code> and processed on an isolated telemetry channel. It will never overwrite physical battery models or contaminate real hardware telemetry recordings.
      </div>

      <!-- Real-time Generator Metrics -->
      <div class="hw-metrics-row">
        <div class="hw-metric-cell">
          <span class="label">Generator State</span>
          <span class="value" id="mock-stat-running">STOPPED</span>
        </div>
        <div class="hw-metric-cell">
          <span class="label">Sample Rate</span>
          <span class="value" id="mock-stat-hz">0.0 Hz</span>
        </div>
        <div class="hw-metric-cell">
          <span class="label">Generated Samples</span>
          <span class="value" id="mock-stat-samples">0</span>
        </div>
        <div class="hw-metric-cell">
          <span class="label">Faults Injected</span>
          <span class="value" id="mock-stat-errors" style="color: var(--color-warning);">0</span>
        </div>
        <div class="hw-metric-cell">
          <span class="label">Voltage</span>
          <span class="value" id="mock-stat-voltage" style="color: var(--color-cyan);">— V</span>
        </div>
        <div class="hw-metric-cell">
          <span class="label">Power (V × I)</span>
          <span class="value" id="mock-stat-power" style="color: var(--color-success);">— W</span>
        </div>
      </div>

      <div class="hw-grid">
        <!-- Generator Configuration -->
        <div class="hw-card">
          <div class="hw-card-title">
            <span>⚙️ Simulation Parameters</span>
            <button id="mock-btn-apply" class="btn btn-secondary btn-sm">Apply Settings</button>
          </div>

          <div class="mock-control-grid">
            <div class="mock-slider-group">
              <label>
                <span>Sample Period</span>
                <span id="mock-val-interval">500 ms</span>
              </label>
              <input type="range" id="mock-input-interval" min="100" max="2000" step="50" value="500" class="form-range" />
            </div>

            <div class="mock-slider-group">
              <label>
                <span>Current Amplitude</span>
                <span id="mock-val-current">2.5 A</span>
              </label>
              <input type="range" id="mock-input-current" min="0" max="10" step="0.5" value="2.5" class="form-range" />
            </div>

            <div class="mock-slider-group">
              <label>
                <span>Min Voltage</span>
                <span id="mock-val-vmin">3.0 V</span>
              </label>
              <input type="number" id="mock-input-vmin" class="form-input" value="3.0" step="0.1" min="1.0" max="5.0" />
            </div>

            <div class="mock-slider-group">
              <label>
                <span>Max Voltage</span>
                <span id="mock-val-vmax">4.2 V</span>
              </label>
              <input type="number" id="mock-input-vmax" class="form-input" value="4.2" step="0.1" min="1.0" max="5.0" />
            </div>

            <div class="mock-slider-group">
              <label>
                <span>Cell Count</span>
                <span id="mock-val-cells">3 Cells</span>
              </label>
              <input type="number" id="mock-input-cells" class="form-input" value="3" min="1" max="16" />
            </div>

            <div class="mock-slider-group">
              <label>
                <span>Random Seed (optional)</span>
              </label>
              <input type="number" id="mock-input-seed" class="form-input" placeholder="Random" />
            </div>
          </div>

          <!-- Fault Injection for QA Testing -->
          <div style="border-top: 1px solid var(--border-subtle); padding-top: var(--space-4); margin-top: var(--space-3);">
            <div style="font-size: var(--text-sm); font-weight: 600; margin-bottom: var(--space-2); color: var(--text-secondary);">
              🧪 Fault & Anomaly Injection (QA Testing)
            </div>
            <div class="mock-actions-row">
              <button id="mock-btn-inject-malformed" class="btn btn-secondary btn-sm">
                ⚠️ Inject Malformed Frame
              </button>
              <button id="mock-btn-inject-overvoltage" class="btn btn-secondary btn-sm">
                ⚡ Inject Voltage Spike
              </button>
              <button id="mock-btn-reset-stats" class="btn btn-secondary btn-sm">
                🔄 Reset Counters
              </button>
            </div>
          </div>
        </div>

        <!-- Sample Inspector & Event Feed -->
        <div class="hw-card">
          <div class="hw-card-title">
            <span>🔬 Live Synthetic Frame Inspector</span>
            <span style="font-size: var(--text-xs); color: var(--text-muted); font-family: var(--font-mono);">
              Tag: [source_mode=MOCK]
            </span>
          </div>

          <div id="mock-stream-console" class="terminal-console" style="height: 380px;">
Waiting for mock telemetry generator start...
          </div>
        </div>
      </div>
    `;
  }

  _bindEvents() {
    this.container.querySelector('#mock-btn-start')?.addEventListener('click', () => this.startGenerator());
    this.container.querySelector('#mock-btn-stop')?.addEventListener('click', () => this.stopGenerator());
    this.container.querySelector('#mock-btn-apply')?.addEventListener('click', () => this.applyConfig());
    this.container.querySelector('#mock-btn-reset-stats')?.addEventListener('click', () => this.resetGenerator());

    this.container.querySelector('#mock-btn-inject-malformed')?.addEventListener('click', () => this.injectError('malformed_frame'));
    this.container.querySelector('#mock-btn-inject-overvoltage')?.addEventListener('click', () => this.injectError('overvoltage_spike'));

    // Dynamic slider labels
    const intervalSlider = this.container.querySelector('#mock-input-interval');
    const intervalLabel = this.container.querySelector('#mock-val-interval');
    intervalSlider?.addEventListener('input', (e) => {
      if (intervalLabel) intervalLabel.textContent = `${e.target.value} ms`;
    });

    const currentSlider = this.container.querySelector('#mock-input-current');
    const currentLabel = this.container.querySelector('#mock-val-current');
    currentSlider?.addEventListener('input', (e) => {
      if (currentLabel) currentLabel.textContent = `${e.target.value} A`;
    });
  }

  async mount() {
    await this.pollStatus();
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(() => this.pollStatus(), 1500);
  }

  unmount() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  async startGenerator() {
    try {
      const res = await api.startMock();
      this.updateStatus(res);
      store.setMockStatus(res);
    } catch (err) {
      alert(`Failed to start mock generator: ${err.message}`);
    }
  }

  async stopGenerator() {
    try {
      const res = await api.stopMock();
      this.updateStatus(res);
      store.setMockStatus(res);
    } catch (err) {
      alert(`Failed to stop mock generator: ${err.message}`);
    }
  }

  async applyConfig() {
    const interval = parseInt(this.container.querySelector('#mock-input-interval')?.value || '500', 10);
    const current = parseFloat(this.container.querySelector('#mock-input-current')?.value || '2.5');
    const vmin = parseFloat(this.container.querySelector('#mock-input-vmin')?.value || '3.0');
    const vmax = parseFloat(this.container.querySelector('#mock-input-vmax')?.value || '4.2');
    const cells = parseInt(this.container.querySelector('#mock-input-cells')?.value || '3', 10);
    const seedVal = this.container.querySelector('#mock-input-seed')?.value;
    const seed = seedVal ? parseInt(seedVal, 10) : null;

    try {
      const res = await api.configureMock({
        sample_interval_ms: interval,
        current_amplitude_a: current,
        min_voltage_v: vmin,
        max_voltage_v: vmax,
        cell_count: cells,
        random_seed: seed,
      });
      this.updateStatus(res);
      alert('Mock generator settings updated.');
    } catch (err) {
      alert(`Failed to configure mock generator: ${err.message}`);
    }
  }

  async resetGenerator() {
    try {
      const res = await api.resetMock();
      this.updateStatus(res);
      const consoleEl = this.container.querySelector('#mock-stream-console');
      if (consoleEl) consoleEl.textContent = 'Generator reset.\n';
    } catch (err) {
      alert(`Error resetting: ${err.message}`);
    }
  }

  async injectError(errorType) {
    try {
      await api.injectMockError(errorType);
      await this.pollStatus();
    } catch (err) {
      alert(`Error injecting fault: ${err.message}`);
    }
  }

  async pollStatus() {
    try {
      const status = await api.getMockStatus();
      this.updateStatus(status);
      store.setMockStatus(status);

      if (status.is_running) {
        const recordsRes = await api.getMockRecords();
        this._renderStream(recordsRes.records || []);
      }
    } catch (_) {}
  }

  updateStatus(status) {
    if (!status) return;
    this.status = status;

    const badge = this.container.querySelector('#mock-state-badge');
    const btnStart = this.container.querySelector('#mock-btn-start');
    const btnStop = this.container.querySelector('#mock-btn-stop');

    const statRunning = this.container.querySelector('#mock-stat-running');
    const statHz = this.container.querySelector('#mock-stat-hz');
    const statSamples = this.container.querySelector('#mock-stat-samples');
    const statErrors = this.container.querySelector('#mock-stat-errors');
    const statVoltage = this.container.querySelector('#mock-stat-voltage');
    const statPower = this.container.querySelector('#mock-stat-power');

    const running = Boolean(status.is_running);
    if (btnStart) btnStart.disabled = running;
    if (btnStop) btnStop.disabled = !running;

    if (badge) {
      badge.textContent = running ? 'MOCK RUNNING' : 'MOCK IDLE';
      badge.className = `mode-pill ${running ? 'mode-mock' : 'mode-live'}`;
    }

    if (statRunning) statRunning.textContent = running ? 'ACTIVE' : 'STOPPED';
    if (statHz) statHz.textContent = `${status.sample_rate_hz || 0} Hz`;
    if (statSamples) statSamples.textContent = `${status.samples_generated || 0}`;
    if (statErrors) statErrors.textContent = `${status.errors_injected || 0}`;

    if (status.last_generated_record) {
      const rec = status.last_generated_record;
      if (statVoltage) statVoltage.textContent = `${rec.voltage_v.toFixed(3)} V`;
      if (statPower) {
        statPower.textContent = rec.power_w !== null ? `${rec.power_w.toFixed(2)} W` : '— W';
      }
    }
  }

  _renderStream(records) {
    const consoleEl = this.container.querySelector('#mock-stream-console');
    if (!consoleEl || records.length === 0) return;

    const lines = records.slice(-30).map((r) => {
      const timeStr = new Date(r.received_timestamp_ns / 1e6).toLocaleTimeString();
      if (r.is_valid) {
        return `<span class="terminal-line-dim">[${timeStr}]</span> <span class="terminal-line-ok">[MOCK]</span> V=${r.voltage_v.toFixed(3)}V I=${r.current_a !== null ? r.current_a.toFixed(3) + 'A' : '0A'} P=${r.power_w !== null ? r.power_w.toFixed(2) + 'W' : '0W'} T=${r.temperature_c !== null ? r.temperature_c.toFixed(1) + '°C' : '—'} <span class="terminal-line-dim">cells=${(r.cell_voltages_v || []).join(',')}</span>`;
      } else {
        return `<span class="terminal-line-dim">[${timeStr}]</span> <span class="terminal-line-err">[FAULT]</span> ${r.errors ? r.errors.join('; ') : 'Invalid frame'} <span class="terminal-line-dim">raw: ${r.raw_payload}</span>`;
      }
    });

    consoleEl.innerHTML = lines.join('<br/>');
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  update(changeType, appState) {
    if (changeType === 'MOCK_STATUS') {
      this.updateStatus(appState.mockStatus);
    }
  }
}
