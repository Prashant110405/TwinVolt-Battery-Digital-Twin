/**
 * Hardware & Arduino Integration View
 *
 * Provides dual-transport hardware gateway (USB Serial & Bluetooth Low Energy),
 * firmware workspace editor, port discovery, live connection controls,
 * static validation/compilation console, and real-time telemetry stream.
 */

import { api } from '../api.js';
import { store } from '../state.js';
import { bleManager, TWINVOLT_BLE_CONFIG } from '../ble.js';
import { canonicalPipeline } from '../telemetry_pipeline.js';

export class HardwareView {
  constructor(container) {
    this.container = container;
    this.currentFile = null;
    this.ports = [];
    this.files = [];
    this.status = null;
    this.pollTimer = null;
    this.benchStreamTimer = null;
    this._initDom();
    this._bindEvents();
  }

  _initDom() {
    this.container.innerHTML = `
      <div class="hw-header-bar">
        <div>
          <div class="eyebrow">HARDWARE GATEWAY & FIRMWARE</div>
          <h1 style="font-size: var(--text-2xl); font-weight: 700; margin: 0;">Dual-Transport Hardware Integration</h1>
        </div>
        <div style="display: flex; gap: var(--space-2); align-items: center;">
          <div id="hw-connection-badge" class="status-pill disconnected">
            <span class="indicator-dot"></span>
            <span id="hw-badge-text">DISCONNECTED</span>
          </div>
          <button id="hw-btn-refresh-ports" class="btn btn-secondary btn-sm" title="Scan system COM ports">
            🔄 Refresh Ports
          </button>
        </div>
      </div>

      <!-- Transport Mode Selector -->
      <div class="transport-mode-bar" role="tablist" aria-label="Hardware Transport Mode">
        <button id="hw-tab-serial" class="transport-tab-btn active" data-transport="SERIAL" role="tab" aria-selected="true">
          🔌 USB Serial
        </button>
        <button id="hw-tab-ble" class="transport-tab-btn" data-transport="BLE" role="tab" aria-selected="false">
          📶 Bluetooth Low Energy (BLE)
        </button>
      </div>

      <!-- Real-time Hardware Metrics Banner -->
      <div class="hw-metrics-row">
        <div class="hw-metric-cell">
          <span class="label" id="hw-label-target">Active Device / Port</span>
          <span class="value" id="hw-stat-port">—</span>
        </div>
        <div class="hw-metric-cell">
          <span class="label" id="hw-label-protocol">Transport / Baud</span>
          <span class="value" id="hw-stat-baud">—</span>
        </div>
        <div class="hw-metric-cell">
          <span class="label">Sample Rate</span>
          <span class="value" id="hw-stat-hz">0.0 Hz</span>
        </div>
        <div class="hw-metric-cell">
          <span class="label" id="hw-label-frames">Frames / Packets</span>
          <span class="value" id="hw-stat-frames">0</span>
        </div>
        <div class="hw-metric-cell">
          <span class="label">Parse Errors</span>
          <span class="value" id="hw-stat-errors" style="color: var(--color-danger);">0</span>
        </div>
        <div class="hw-metric-cell">
          <span class="label">Last Voltage</span>
          <span class="value" id="hw-stat-last-v" style="color: var(--color-cyan);">— V</span>
        </div>
      </div>

      <div class="hw-grid">
        <!-- Left Column: Hardware Connection & Firmware Tools -->
        <div style="display: flex; flex-direction: column; gap: var(--space-4);">

          <!-- Transport 1: USB Serial Connection Panel -->
          <div id="hw-panel-serial" class="hw-card">
            <div class="hw-card-title">
              <span>🔌 USB Serial Hardware Connection</span>
            </div>

            <div style="display: flex; flex-direction: column; gap: var(--space-3);">
              <div>
                <label style="display: block; font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: 4px;">
                  System COM Port:
                </label>
                <select id="hw-port-select" class="form-select" style="width: 100%;">
                  <option value="">Scanning serial ports...</option>
                </select>
              </div>

              <!-- Port Notice / Diagnostic info -->
              <div id="hw-port-notice" style="display: none; padding: 8px 12px; background: rgba(56, 189, 248, 0.08); border-left: 3px solid var(--color-cyan); border-radius: var(--radius-sm); font-size: var(--text-xs); line-height: 1.4; color: var(--text-secondary);">
                💡 <strong>USB Power + BLE Data Mode:</strong> If your ESP32 is plugged in via USB for power but no USB-UART COM port appears, your cable may be power-only (lacks data wires) or drivers are needed. Switch to the <strong>Bluetooth Low Energy (BLE)</strong> tab above to stream live telemetry wirelessly!
              </div>

              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3);">
                <div>
                  <label style="display: block; font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: 4px;">
                    Baud Rate:
                  </label>
                  <select id="hw-baud-select" class="form-select" style="width: 100%;">
                    <option value="9600">9600 baud</option>
                    <option value="19200">19200 baud</option>
                    <option value="38400">38400 baud</option>
                    <option value="57600">57600 baud</option>
                    <option value="115200" selected>115200 baud</option>
                    <option value="230400">230400 baud</option>
                  </select>
                </div>
                <div>
                  <label style="display: block; font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: 4px;">
                    Data Protocol:
                  </label>
                  <select id="hw-format-select" class="form-select" style="width: 100%;">
                    <option value="AUTO" selected>Auto-Detect (JSON/CSV)</option>
                    <option value="JSON">JSON Lines</option>
                    <option value="CSV">CSV Tabular</option>
                    <option value="BMS_BINARY">BMS Binary Frame</option>
                  </select>
                </div>
              </div>

              <div>
                <label style="display: block; font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: 4px;">
                  Target Digital Twin:
                </label>
                <select id="hw-twin-target-select" class="form-select" style="width: 100%;">
                  <option value="twin_prototype_3s1p">twin_prototype_3s1p</option>
                </select>
              </div>

              <div style="display: flex; gap: var(--space-2); margin-top: var(--space-2);">
                <button id="hw-btn-connect" class="btn btn-primary" style="flex: 1;">
                  Connect USB Serial
                </button>
                <button id="hw-btn-disconnect" class="btn btn-danger" style="flex: 1;" disabled>
                  Disconnect
                </button>
              </div>

              <div style="display: flex; gap: var(--space-2); margin-top: var(--space-2);">
                <button id="hw-btn-stream-bench" class="btn btn-secondary btn-sm" style="flex: 1;" title="Stream 1 Hz simulated ESP32 bench telemetry across the entire pipeline">
                  ⚡ Stream Bench Telemetry (1 Hz)
                </button>
              </div>

              <div id="hw-conn-msg" style="font-size: var(--text-xs); color: var(--text-muted); min-height: 18px;"></div>
            </div>
          </div>

          <!-- Transport 2: Bluetooth Low Energy (BLE) Panel -->
          <div id="hw-panel-ble" class="hw-card" style="display: none;">
            <div class="hw-card-title">
              <span>📶 Bluetooth Low Energy (BLE) GATT Connection</span>
            </div>

            <div style="display: flex; flex-direction: column; gap: var(--space-3);">
              <!-- Browser Web Bluetooth Support Notice -->
              <div id="hw-ble-support-banner" style="padding: 8px 12px; border-radius: var(--radius-sm); font-size: var(--text-xs); line-height: 1.4;">
                Checking Web Bluetooth support...
              </div>

              <div style="background: rgba(15, 23, 42, 0.4); padding: 10px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); font-size: var(--text-xs);">
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                  <span style="color: var(--text-muted);">Target Device:</span>
                  <span style="font-family: var(--font-mono); color: var(--color-cyan);">Twin Volt</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                  <span style="color: var(--text-muted);">Service UUID:</span>
                  <span style="font-family: var(--font-mono); color: var(--text-secondary); font-size: 11px;">7a100001-1234-5678-1234-56789abcdef0</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                  <span style="color: var(--text-muted);">Telemetry Char:</span>
                  <span style="font-family: var(--font-mono); color: var(--text-secondary); font-size: 11px;">7a100002... (NOTIFY | READ)</span>
                </div>
                <div style="display: flex; justify-content: space-between;">
                  <span style="color: var(--text-muted);">Control Char:</span>
                  <span style="font-family: var(--font-mono); color: var(--text-secondary); font-size: 11px;">7a100003... (WRITE | READ)</span>
                </div>
              </div>

              <div style="padding: 8px 12px; background: rgba(16, 185, 129, 0.08); border-left: 3px solid var(--color-success); border-radius: var(--radius-sm); font-size: var(--text-xs); line-height: 1.4; color: var(--text-secondary);">
                🔋 <strong>USB Power + BLE Data Mode:</strong> Keep your ESP32 powered from your laptop USB port while streaming live battery telemetry wirelessly via Bluetooth Low Energy!
              </div>

              <div>
                <label style="display: block; font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: 4px;">
                  Target Digital Twin:
                </label>
                <select id="hw-ble-twin-target-select" class="form-select" style="width: 100%;">
                  <option value="twin_prototype_3s1p">twin_prototype_3s1p</option>
                </select>
              </div>

              <div style="display: flex; gap: var(--space-2); margin-top: var(--space-2);">
                <button id="hw-btn-ble-connect" class="btn btn-primary" style="flex: 1;">
                  📶 Scan & Connect Bluetooth
                </button>
                <button id="hw-btn-ble-disconnect" class="btn btn-danger" style="flex: 1;" disabled>
                  Disconnect BLE
                </button>
              </div>

              <div id="hw-ble-msg" style="font-size: var(--text-xs); color: var(--text-muted); min-height: 18px;"></div>
            </div>
          </div>

          <!-- Compiler & Flashing Panel -->
          <div class="hw-card">
            <div class="hw-card-title">
              <span>🛠️ Firmware Validation & Flashing</span>
            </div>

            <div style="display: flex; flex-direction: column; gap: var(--space-3);">
              <div>
                <label style="display: block; font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: 4px;">
                  Target Board Profile (FQBN):
                </label>
                <select id="hw-board-fqbn" class="form-select" style="width: 100%;">
                  <option value="esp32:esp32:esp32" selected>ESP32 Dev Module (Dual BLE/Serial)</option>
                  <option value="arduino:avr:uno">Arduino Uno (ATmega328P)</option>
                  <option value="arduino:avr:nano">Arduino Nano (ATmega328P)</option>
                  <option value="arduino:avr:mega">Arduino Mega 2560</option>
                </select>
              </div>

              <div style="display: flex; gap: var(--space-2);">
                <button id="hw-btn-verify" class="btn btn-secondary btn-sm" style="flex: 1;">
                  🔍 Verify / Check Code
                </button>
                <button id="hw-btn-flash" class="btn btn-secondary btn-sm" style="flex: 1;" title="Flash via local arduino-cli">
                  ⚡ Flash to Board
                </button>
              </div>

              <div>
                <div style="font-size: var(--text-xs); color: var(--text-secondary); margin-bottom: 4px;">
                  Compiler Output:
                </div>
                <div id="hw-compiler-console" class="terminal-console" style="height: 130px;">Ready. Select a firmware sketch and click Verify.</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Right Column: Firmware Workspace Editor & Live Stream -->
        <div style="display: flex; flex-direction: column; gap: var(--space-4);">
          <!-- Firmware Source Workspace -->
          <div class="hw-card">
            <div class="hw-card-title">
              <span>📄 Firmware Workspace Editor</span>
              <div style="display: flex; gap: var(--space-2);">
                <input type="file" id="hw-file-input" accept=".ino,.cpp,.c,.h" style="display: none;" />
                <button id="hw-btn-upload-file" class="btn btn-secondary btn-sm">Upload .ino</button>
                <button id="hw-btn-save-file" class="btn btn-secondary btn-sm">Save</button>
                <a id="hw-btn-download-file" class="btn btn-secondary btn-sm" download>Download</a>
              </div>
            </div>

            <div style="display: flex; gap: var(--space-3); margin-bottom: var(--space-3); align-items: center;">
              <select id="hw-file-select" class="form-select" style="flex: 1;">
                <option value="">Loading workspace files...</option>
              </select>
              <span id="hw-file-meta" style="font-size: var(--text-xs); color: var(--text-muted); font-family: var(--font-mono);"></span>
            </div>

            <div class="code-editor-wrap">
              <div class="code-editor-toolbar">
                <span id="hw-editor-filename">No file selected</span>
                <span>UTF-8 • ESP32 / Arduino C++</span>
              </div>
              <textarea id="hw-code-editor" class="code-editor-textarea" placeholder="// Select or upload a firmware sketch..." spellcheck="false"></textarea>
            </div>
          </div>

          <!-- Live Raw Hardware Telemetry Stream -->
          <div class="hw-card">
            <div class="hw-card-title">
              <span id="hw-stream-title">📡 Live Hardware Telemetry Stream (USB Serial)</span>
              <button id="hw-btn-clear-stream" class="btn btn-secondary btn-sm">Clear Stream</button>
            </div>
            <div id="hw-stream-console" class="terminal-console" style="height: 180px;">
Waiting for hardware connection...
            </div>
          </div>
        </div>
      </div>
    `;
  }

  _bindEvents() {
    // Transport Tab Toggling
    const tabSerial = this.container.querySelector('#hw-tab-serial');
    const tabBle = this.container.querySelector('#hw-tab-ble');

    tabSerial?.addEventListener('click', () => this.switchTransport('SERIAL'));
    tabBle?.addEventListener('click', () => this.switchTransport('BLE'));

    // USB Serial controls
    this.container.querySelector('#hw-btn-refresh-ports')?.addEventListener('click', () => this.refreshPorts());
    this.container.querySelector('#hw-btn-connect')?.addEventListener('click', () => this.connectHardware());
    this.container.querySelector('#hw-btn-disconnect')?.addEventListener('click', () => this.disconnectHardware());

    // BLE controls
    this.container.querySelector('#hw-btn-ble-connect')?.addEventListener('click', () => this.connectBle());
    this.container.querySelector('#hw-btn-ble-disconnect')?.addEventListener('click', () => this.disconnectBle());

    // Firmware editor controls
    this.container.querySelector('#hw-file-select')?.addEventListener('change', (e) => this.loadFile(e.target.value));
    this.container.querySelector('#hw-btn-save-file')?.addEventListener('click', () => this.saveCurrentFile());

    const fileInput = this.container.querySelector('#hw-file-input');
    this.container.querySelector('#hw-btn-upload-file')?.addEventListener('click', () => fileInput?.click());
    fileInput?.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        this.uploadFile(e.target.files[0]);
      }
    });

    this.container.querySelector('#hw-btn-verify')?.addEventListener('click', () => this.verifyCurrentFile());
    this.container.querySelector('#hw-btn-flash')?.addEventListener('click', () => this.flashCurrentFile());

    // Stream console clear
    this.container.querySelector('#hw-btn-clear-stream')?.addEventListener('click', () => {
      const consoleEl = this.container.querySelector('#hw-stream-console');
      if (consoleEl) consoleEl.textContent = 'Stream cleared.\n';
    });

    // Bench Stream toggle
    this.container.querySelector('#hw-btn-stream-bench')?.addEventListener('click', () => this.toggleBenchStream());
  }

  toggleBenchStream() {
    const btn = this.container.querySelector('#hw-btn-stream-bench');
    if (this.benchStreamTimer) {
      clearInterval(this.benchStreamTimer);
      this.benchStreamTimer = null;
      if (btn) {
        btn.textContent = '⚡ Stream Bench Telemetry (1 Hz)';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-secondary');
      }
      return;
    }

    if (btn) {
      btn.textContent = '⏹️ Stop Bench Stream (1 Hz)';
      btn.classList.remove('btn-secondary');
      btn.classList.add('btn-danger');
    }

    let step = store.stepCount || 10;
    const sendFrame = () => {
      step++;
      const v = 12.38 + Math.sin(step * 0.15) * 0.12 + (Math.random() - 0.5) * 0.02;
      const i = 1.22 + Math.cos(step * 0.15) * 0.18 + (Math.random() - 0.5) * 0.03;
      const t = 26.2 + (Math.sin(step * 0.05) * 1.5);
      const sysId = store.activeTwinId || 'twin_prototype_3s1p';

      // Feed through canonical pipeline so store + dashboard update immediately
      const rec = canonicalPipeline.ingest({
        pack_voltage_v: Number(v.toFixed(3)),
        pack_current_a: Number(i.toFixed(3)),
        ambient_temperature_c: Number(t.toFixed(1)),
        system_id: sysId,
      }, 'BENCH');

      const streamConsole = this.container.querySelector('#hw-stream-console');
      if (streamConsole && rec) {
        const line = `[BENCH 1Hz] ${new Date().toLocaleTimeString()} v=${rec.voltage_v.toFixed(3)}V i=${rec.current_a.toFixed(3)}A p=${rec.power_w}W temp=${rec.temperature_c.toFixed(1)}°C\n`;
        streamConsole.textContent = line + streamConsole.textContent.slice(0, 3000);
      }
    };

    sendFrame();
    this.benchStreamTimer = setInterval(sendFrame, 1000);
  }

  switchTransport(transport) {
    store.setActiveTransport(transport);

    const tabSerial = this.container.querySelector('#hw-tab-serial');
    const tabBle = this.container.querySelector('#hw-tab-ble');
    const panelSerial = this.container.querySelector('#hw-panel-serial');
    const panelBle = this.container.querySelector('#hw-panel-ble');
    const streamTitle = this.container.querySelector('#hw-stream-title');

    if (transport === 'SERIAL') {
      tabSerial?.classList.add('active');
      tabSerial?.setAttribute('aria-selected', 'true');
      tabBle?.classList.remove('active');
      tabBle?.setAttribute('aria-selected', 'false');

      if (panelSerial) panelSerial.style.display = 'block';
      if (panelBle) panelBle.style.display = 'none';
      if (streamTitle) streamTitle.textContent = '📡 Live Hardware Telemetry Stream (USB Serial)';

      this.renderSerialMetrics();
    } else {
      tabBle?.classList.add('active');
      tabBle?.setAttribute('aria-selected', 'true');
      tabSerial?.classList.remove('active');
      tabSerial?.setAttribute('aria-selected', 'false');

      if (panelBle) panelBle.style.display = 'block';
      if (panelSerial) panelSerial.style.display = 'none';
      if (streamTitle) streamTitle.textContent = '📡 Live Hardware Telemetry Stream (Bluetooth BLE)';

      this.renderBleMetrics();
    }
  }

  async mount() {
    this._checkBleSupport();
    await this.refreshPorts();
    await this.refreshFiles();
    await this.pollStatus();

    // Start background status poll every 1.2s
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(() => this.pollStatus(), 1200);
  }

  unmount() {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    if (this.benchStreamTimer) {
      clearInterval(this.benchStreamTimer);
      this.benchStreamTimer = null;
    }
  }

  _checkBleSupport() {
    const banner = this.container.querySelector('#hw-ble-support-banner');
    const btnConnect = this.container.querySelector('#hw-btn-ble-connect');
    if (!banner) return;

    const check = bleManager.checkSupport();
    if (check.supported) {
      banner.style.background = 'rgba(16, 185, 129, 0.1)';
      banner.style.color = 'var(--color-success)';
      banner.style.border = '1px solid rgba(16, 185, 129, 0.2)';
      banner.innerHTML = '✓ <strong>Web Bluetooth Available:</strong> Native Chromium BLE GATT API is supported in this browser.';
      if (btnConnect) btnConnect.disabled = false;
    } else {
      banner.style.background = 'rgba(239, 68, 68, 0.1)';
      banner.style.color = 'var(--color-danger)';
      banner.style.border = '1px solid rgba(239, 68, 68, 0.2)';
      banner.innerHTML = `⚠️ <strong>Web Bluetooth Limitation:</strong> ${check.reason}`;
      if (btnConnect) btnConnect.disabled = true;
    }
  }

  async refreshPorts() {
    const portSelect = this.container.querySelector('#hw-port-select');
    const noticeEl = this.container.querySelector('#hw-port-notice');
    try {
      const res = await api.getSerialPorts();
      this.ports = res.ports || [];
      if (!portSelect) return;
      portSelect.innerHTML = '';

      let hasUsbUart = false;
      let hasBluetoothLink = false;

      if (this.ports.length === 0) {
        portSelect.innerHTML = '<option value="">No COM ports detected (connect Arduino/ESP32 over USB)</option>';
      } else {
        this.ports.forEach((p) => {
          const opt = document.createElement('option');
          opt.value = p.device;

          let tag = '';
          if (p.is_arduino_candidate) {
            tag = ' ★ [USB-UART / MCU]';
            hasUsbUart = true;
          } else if (p.is_bluetooth_link) {
            tag = ' [Bluetooth RFCOMM Link]';
            hasBluetoothLink = true;
          }

          opt.textContent = `${p.device} — ${p.description || p.name}${tag}`;
          portSelect.appendChild(opt);
        });
      }

      // Show diagnostic notice if only Bluetooth links are found or no hardware USB port
      if (noticeEl) {
        noticeEl.style.display = (!hasUsbUart && hasBluetoothLink) ? 'block' : 'none';
      }
    } catch (err) {
      console.warn('[HardwareView] Failed to list ports:', err.message);
      if (portSelect) portSelect.innerHTML = `<option value="">Error scanning ports: ${err.message}</option>`;
    }
  }

  async connectBle() {
    const msgEl = this.container.querySelector('#hw-ble-msg');
    const btnConnect = this.container.querySelector('#hw-btn-ble-connect');
    const btnDisconnect = this.container.querySelector('#hw-btn-ble-disconnect');

    if (btnConnect) btnConnect.disabled = true;
    if (msgEl) {
      msgEl.textContent = 'Requesting Bluetooth device pairing... Select "Twin Volt" in the browser prompt.';
      msgEl.style.color = 'var(--color-cyan)';
    }

    try {
      const res = await bleManager.connect();
      if (msgEl) {
        msgEl.textContent = `✓ Connected to ${res.deviceName} via BLE GATT. Subscribed to notifications.`;
        msgEl.style.color = 'var(--color-success)';
      }
      if (btnDisconnect) btnDisconnect.disabled = false;
      this.renderBleMetrics();
    } catch (err) {
      if (msgEl) {
        msgEl.textContent = `✗ ${err.message}`;
        msgEl.style.color = 'var(--color-danger)';
      }
      if (btnConnect) btnConnect.disabled = false;
    }
  }

  async disconnectBle() {
    const msgEl = this.container.querySelector('#hw-ble-msg');
    const btnConnect = this.container.querySelector('#hw-btn-ble-connect');
    const btnDisconnect = this.container.querySelector('#hw-btn-ble-disconnect');

    try {
      await bleManager.disconnect();
      if (msgEl) {
        msgEl.textContent = 'Bluetooth device disconnected cleanly.';
        msgEl.style.color = 'var(--text-muted)';
      }
      if (btnConnect) btnConnect.disabled = false;
      if (btnDisconnect) btnDisconnect.disabled = true;
      this.renderBleMetrics();
    } catch (err) {
      if (msgEl) {
        msgEl.textContent = `Error disconnecting: ${err.message}`;
      }
    }
  }

  async connectHardware() {
    const port = this.container.querySelector('#hw-port-select')?.value;
    const baud = parseInt(this.container.querySelector('#hw-baud-select')?.value || '115200', 10);
    const format = this.container.querySelector('#hw-format-select')?.value || 'AUTO';
    const twin = this.container.querySelector('#hw-twin-target-select')?.value || 'twin_prototype_3s1p';
    const msgEl = this.container.querySelector('#hw-conn-msg');

    if (!port) {
      if (msgEl) {
        msgEl.textContent = 'Please select a valid COM port.';
        msgEl.style.color = 'var(--color-danger)';
      }
      return;
    }

    if (msgEl) {
      msgEl.textContent = `Connecting to ${port} @ ${baud} baud...`;
      msgEl.style.color = 'var(--color-cyan)';
    }

    try {
      const res = await api.connectArduino({
        port,
        baud_rate: baud,
        data_format: format,
        system_id: twin,
      });
      this.status = res;
      store.setHardwareStatus(res);
      this.renderSerialMetrics();
      if (msgEl) {
        msgEl.textContent = `✓ Connected to ${port}`;
        msgEl.style.color = 'var(--color-success)';
      }
    } catch (err) {
      if (msgEl) {
        msgEl.textContent = `✗ Connection failed: ${err.message}`;
        msgEl.style.color = 'var(--color-danger)';
      }
    }
  }

  async disconnectHardware() {
    const msgEl = this.container.querySelector('#hw-conn-msg');
    try {
      const res = await api.disconnectArduino();
      this.status = res;
      store.setHardwareStatus(res);
      this.renderSerialMetrics();
      if (msgEl) {
        msgEl.textContent = 'Hardware disconnected.';
        msgEl.style.color = 'var(--text-muted)';
      }
    } catch (err) {
      if (msgEl) {
        msgEl.textContent = `Error disconnecting: ${err.message}`;
      }
    }
  }

  async pollStatus() {
    try {
      if (store.activeTransport === 'SERIAL') {
        const status = await api.getArduinoStatus();
        this.status = status;
        store.setHardwareStatus(status);
        this.renderSerialMetrics();

        if (status.state === 'CONNECTED') {
          const streamRes = await api.getArduinoRecords();
          this._renderStreamRecords(streamRes.records || [], 'SERIAL');
        }
      } else {
        // BLE Transport
        this.renderBleMetrics();
        const bleRecords = bleManager.getRecentRecords();
        if (bleRecords.length > 0) {
          this._renderStreamRecords(bleRecords, 'BLE');
        }
      }
    } catch (_) {}
  }

  renderSerialMetrics() {
    // Merge REST-polled status with live pipeline USB state for accurate metrics
    const usbPipeline = store.usbStatus || {};
    const restStatus = this.status || store.hardwareStatus || {};

    // Prefer pipeline state when it's streaming; fall back to REST state
    const pipelineState = usbPipeline.state || 'DISCONNECTED';
    const restState = restStatus.state || 'DISCONNECTED';
    const effectiveState = ['STREAMING', 'CONNECTED_NO_DATA'].includes(pipelineState)
      ? pipelineState
      : restState;

    const status = {
      ...restStatus,
      state: effectiveState,
      port: usbPipeline.portName || restStatus.port,
      baud_rate: usbPipeline.baudRate || restStatus.baud_rate,
      sample_rate_hz: usbPipeline.sampleRateHz ?? restStatus.sample_rate_hz ?? 0,
      frames_received: usbPipeline.framesReceived ?? restStatus.frames_received ?? 0,
      parse_errors: usbPipeline.parseErrors ?? restStatus.parse_errors ?? 0,
      last_valid_reading: (usbPipeline.lastValidReading) || restStatus.last_valid_reading,
    };


    const badge = this.container.querySelector('#hw-connection-badge');
    const badgeText = this.container.querySelector('#hw-badge-text');
    const labelTarget = this.container.querySelector('#hw-label-target');
    const labelProtocol = this.container.querySelector('#hw-label-protocol');
    const labelFrames = this.container.querySelector('#hw-label-frames');

    const statPort = this.container.querySelector('#hw-stat-port');
    const statBaud = this.container.querySelector('#hw-stat-baud');
    const statHz = this.container.querySelector('#hw-stat-hz');
    const statFrames = this.container.querySelector('#hw-stat-frames');
    const statErrors = this.container.querySelector('#hw-stat-errors');
    const statLastV = this.container.querySelector('#hw-stat-last-v');

    const btnConnect = this.container.querySelector('#hw-btn-connect');
    const btnDisconnect = this.container.querySelector('#hw-btn-disconnect');

    if (labelTarget) labelTarget.textContent = 'Serial Port';
    if (labelProtocol) labelProtocol.textContent = 'Baud Rate';
    if (labelFrames) labelFrames.textContent = 'Frames Received';

    const isConnected = ['CONNECTED_NO_DATA', 'STREAMING'].includes(status.state);
    const isConn = isConnected;
    if (btnConnect) btnConnect.disabled = isConn;
    if (btnDisconnect) btnDisconnect.disabled = !isConn;

    if (badge) {
      badge.className = `status-pill ${status.state.toLowerCase()}`;
    }
    if (badgeText) {
      badgeText.textContent = `SERIAL: ${status.state}`;
    }

    if (statPort) statPort.textContent = status.port || '—';
    if (statBaud) statBaud.textContent = status.baud_rate ? `${status.baud_rate} baud` : '—';
    if (statHz) statHz.textContent = `${status.sample_rate_hz || 0} Hz`;
    if (statFrames) statFrames.textContent = `${status.frames_received || 0}`;
    if (statErrors) statErrors.textContent = `${status.parse_errors || 0}`;

    if (statLastV) {
      if (status.last_valid_reading && Number.isFinite(status.last_valid_reading.voltage_v)) {
        statLastV.textContent = `${status.last_valid_reading.voltage_v.toFixed(3)} V`;
      } else {
        statLastV.textContent = '— V';
      }
    }
  }

  renderBleMetrics() {
    const ble = store.bleStatus;

    const badge = this.container.querySelector('#hw-connection-badge');
    const badgeText = this.container.querySelector('#hw-badge-text');
    const labelTarget = this.container.querySelector('#hw-label-target');
    const labelProtocol = this.container.querySelector('#hw-label-protocol');
    const labelFrames = this.container.querySelector('#hw-label-frames');

    const statPort = this.container.querySelector('#hw-stat-port');
    const statBaud = this.container.querySelector('#hw-stat-baud');
    const statHz = this.container.querySelector('#hw-stat-hz');
    const statFrames = this.container.querySelector('#hw-stat-frames');
    const statErrors = this.container.querySelector('#hw-stat-errors');
    const statLastV = this.container.querySelector('#hw-stat-last-v');

    const btnConnect = this.container.querySelector('#hw-btn-ble-connect');
    const btnDisconnect = this.container.querySelector('#hw-btn-ble-disconnect');

    if (labelTarget) labelTarget.textContent = 'BLE Device';
    if (labelProtocol) labelProtocol.textContent = 'GATT Protocol';
    if (labelFrames) labelFrames.textContent = 'Notifications';

    const isConn = ['CONNECTED_NO_DATA', 'STREAMING'].includes(ble.state);
    if (btnConnect) btnConnect.disabled = isConn;
    if (btnDisconnect) btnDisconnect.disabled = !isConn;

    if (badge) {
      badge.className = `status-pill ${ble.state.toLowerCase()}`;
    }
    if (badgeText) {
      badgeText.textContent = `BLE: ${ble.state}`;
    }

    if (statPort) statPort.textContent = ble.deviceName || 'Twin Volt';
    if (statBaud) statBaud.textContent = isConn ? 'GATT Notify' : '—';
    if (statHz) statHz.textContent = `${ble.sampleRateHz || 0} Hz`;
    if (statFrames) statFrames.textContent = `${ble.notificationsReceived || 0}`;
    if (statErrors) statErrors.textContent = `${ble.parseErrors || 0}`;

    if (statLastV) {
      if (ble.lastValidReading && Number.isFinite(ble.lastValidReading.voltage_v)) {
        statLastV.textContent = `${ble.lastValidReading.voltage_v.toFixed(3)} V`;
      } else {
        statLastV.textContent = '— V';
      }
    }
  }

  _renderStreamRecords(records, transport) {
    const consoleEl = this.container.querySelector('#hw-stream-console');
    if (!consoleEl || records.length === 0) return;

    const lines = records.slice(-25).map((r) => {
      const ts = r.received_timestamp_ns ? (r.received_timestamp_ns / 1e6) : (r.received_at_ms || Date.now());
      const timeStr = new Date(ts).toLocaleTimeString();
      const prefix = transport === 'BLE' ? 'BLE' : 'SER';

      if (r.is_valid) {
        return `<span class="terminal-line-dim">[${timeStr} ${prefix}]</span> <span class="terminal-line-ok">OK</span> V=${r.voltage_v.toFixed(3)}V${r.current_a !== null ? ' I=' + r.current_a.toFixed(3) + 'A' : ''}${r.temperature_c !== null ? ' T=' + r.temperature_c.toFixed(1) + '°C' : ''} <span class="terminal-line-dim">payload: ${r.raw_payload}</span>`;
      } else {
        return `<span class="terminal-line-dim">[${timeStr} ${prefix}]</span> <span class="terminal-line-err">ERR</span> ${r.error || (r.errors ? r.errors.join('; ') : 'Malformed')} <span class="terminal-line-dim">raw: ${r.raw_payload}</span>`;
      }
    });

    consoleEl.innerHTML = lines.join('<br/>');
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  // --- Firmware Files and Flashing Methods ---

  async refreshFiles() {
    const fileSelect = this.container.querySelector('#hw-file-select');
    try {
      const res = await api.getFirmwareFiles();
      this.files = res.files || [];
      if (!fileSelect) return;
      fileSelect.innerHTML = '';

      if (this.files.length === 0) {
        fileSelect.innerHTML = '<option value="">No firmware files in workspace</option>';
      } else {
        this.files.forEach((f) => {
          const opt = document.createElement('option');
          opt.value = f.filename;
          opt.textContent = `${f.filename} (${(f.size_bytes / 1024).toFixed(1)} KB)`;
          fileSelect.appendChild(opt);
        });
        if (this.files.length > 0) {
          const defaultFile = this.files.find(f => f.filename === 'TwinVolt_ESP32_BLE_Serial.ino') ||
                              this.files.find(f => f.filename === 'TwinVolt_Arduino_Example.ino') ||
                              this.files[0];
          fileSelect.value = defaultFile.filename;
          await this.loadFile(defaultFile.filename);
        }
      }
    } catch (err) {
      console.warn('[HardwareView] Failed to list firmware files:', err.message);
    }
  }

  async loadFile(filename) {
    if (!filename) return;
    this.currentFile = filename;
    const editor = this.container.querySelector('#hw-code-editor');
    const titleEl = this.container.querySelector('#hw-editor-filename');
    const metaEl = this.container.querySelector('#hw-file-meta');
    const downloadBtn = this.container.querySelector('#hw-btn-download-file');

    if (titleEl) titleEl.textContent = filename;
    if (downloadBtn) downloadBtn.href = `/api/v1/firmware/files/${encodeURIComponent(filename)}/download`;

    try {
      const text = await api.getFirmwareContent(filename);
      if (editor) editor.value = text;
      const fileInfo = this.files.find(f => f.filename === filename);
      if (metaEl && fileInfo) {
        metaEl.textContent = `${(fileInfo.size_bytes / 1024).toFixed(1)} KB • modified ${fileInfo.modified_iso.split('T')[0]}`;
      }
    } catch (err) {
      if (editor) editor.value = `// Failed to load file: ${err.message}`;
    }
  }

  async saveCurrentFile() {
    if (!this.currentFile) return;
    const editor = this.container.querySelector('#hw-code-editor');
    const msgEl = this.container.querySelector('#hw-conn-msg');
    try {
      await api.saveFirmware(this.currentFile, editor.value);
      if (msgEl) {
        msgEl.textContent = `✓ Saved ${this.currentFile}`;
        msgEl.style.color = 'var(--color-success)';
      }
    } catch (err) {
      if (msgEl) {
        msgEl.textContent = `✗ Save failed: ${err.message}`;
        msgEl.style.color = 'var(--color-danger)';
      }
    }
  }

  async uploadFile(file) {
    const msgEl = this.container.querySelector('#hw-conn-msg');
    try {
      const res = await api.uploadFirmware(file);
      await this.refreshFiles();
      await this.loadFile(res.filename);
      if (msgEl) {
        msgEl.textContent = `✓ Uploaded ${res.filename}`;
        msgEl.style.color = 'var(--color-success)';
      }
    } catch (err) {
      if (msgEl) {
        msgEl.textContent = `✗ Upload failed: ${err.message}`;
        msgEl.style.color = 'var(--color-danger)';
      }
    }
  }

  async verifyCurrentFile() {
    if (!this.currentFile) return;
    const consoleEl = this.container.querySelector('#hw-compiler-console');
    const fqbn = this.container.querySelector('#hw-board-fqbn')?.value || 'esp32:esp32:esp32';
    if (consoleEl) consoleEl.textContent = `Verifying ${this.currentFile} against profile ${fqbn}...\n`;

    try {
      const res = await api.verifyFirmware(this.currentFile, fqbn);
      if (consoleEl) {
        const statusLine = res.is_valid ? '>>> VERIFICATION PASSED <<<' : '>>> VERIFICATION NOTICE <<<';
        consoleEl.textContent = `${statusLine}\n\n${res.output}\n\nStatic Checks: ${JSON.stringify(res.static_checks, null, 2)}`;
      }
    } catch (err) {
      if (consoleEl) consoleEl.textContent = `Error during verification: ${err.message}`;
    }
  }

  async flashCurrentFile() {
    if (!this.currentFile) return;
    const consoleEl = this.container.querySelector('#hw-compiler-console');
    const port = this.container.querySelector('#hw-port-select')?.value;
    const fqbn = this.container.querySelector('#hw-board-fqbn')?.value || 'esp32:esp32:esp32';

    if (!port) {
      alert('Please select an active COM port before flashing.');
      return;
    }

    if (consoleEl) consoleEl.textContent = `Attempting firmware flash to ${port} (${fqbn})...\n`;

    try {
      const res = await api.flashFirmware(this.currentFile, port, fqbn);
      if (consoleEl) {
        consoleEl.textContent = res.output;
      }
    } catch (err) {
      if (consoleEl) consoleEl.textContent = `Flash error: ${err.message}`;
    }
  }

  update(changeType, appState) {
    if (changeType === 'HARDWARE_STATUS' && appState.activeTransport === 'SERIAL') {
      this.status = appState.hardwareStatus;
      this.renderSerialMetrics();
    } else if (changeType === 'BLE_STATUS' || (changeType === 'HARDWARE_TELEMETRY' && appState.activeTransport === 'BLE')) {
      this.renderBleMetrics();
    } else if (changeType === 'TRANSPORT_CHANGED') {
      this.switchTransport(appState.activeTransport);
    } else if (changeType === 'HARDWARE_TELEMETRY' || changeType === 'USB_STATUS') {
      if (appState.activeTransport !== 'BLE') {
        this.renderSerialMetrics();
      }
    }
  }
}
