/**
 * TwinVolt Central Reactive Application State Store
 *
 * Maintains in-memory frontend state, bounded ring buffers for high-frequency
 * telemetry/state charting, and subscriber listeners without domain math.
 */

class BoundedBuffer {
  constructor(maxCapacity = 300) {
    this.maxCapacity = maxCapacity;
    this.timestamps = [];
    this.data = {};
  }

  push(timestamp, signals) {
    this.timestamps.push(timestamp);
    for (const [key, value] of Object.entries(signals)) {
      if (!this.data[key]) {
        this.data[key] = [];
      }
      this.data[key].push(Number.isFinite(value) ? value : null);
    }

    if (this.timestamps.length > this.maxCapacity) {
      this.timestamps.shift();
      for (const key in this.data) {
        this.data[key].shift();
      }
    }
  }

  clear() {
    this.timestamps = [];
    this.data = {};
  }
}

class AppState {
  constructor() {
    this.listeners = new Set();

    // Connection & Environment State
    this.wsStatus = 'DISCONNECTED'; // CONNECTED, RECONNECTING, DISCONNECTED
    this.clientLatencyMs = null;
    this.apiHealth = null;
    this.twinLoadError = null;

    // Active Selection State
    this.activeTwinId = null;
    this.activePack = null;
    this.activeTwinStatus = null;
    this.allTwins = [];
    this.allPacks = [];

    // Current Telemetry & State Readouts
    this.latestState = null;
    this.latestTelemetry = null;
    this.lastStateReceivedAtMs = null;
    this.stepCount = 0;
    this.anomaliesCount = 0;

    // Bounded History Buffers
    this.timeSeries = new BoundedBuffer(300);
    this.events = []; // max 100 domain events
    this.maxEvents = 100;

    // Replay & Hardware Mode State
    this.activeMode = 'IDLE'; // IDLE, LIVE, MOCK, REPLAY
    this.hardwareStatus = null;
    this.mockStatus = null;
    this.lastReplayResult = null;
    this.isReplaying = false;

    // Dual-Transport Hardware State (USB Serial vs Bluetooth BLE)
    this.activeTransport = 'SERIAL'; // 'SERIAL' | 'BLE'
    this.usbStatus = {
      state: 'DISCONNECTED', // DISCONNECTED, CONNECTING, CONNECTED_NO_DATA, STREAMING, STALE, ERROR
      portName: null,
      baudRate: 115200,
      framesReceived: 0,
      validFrames: 0,
      parseErrors: 0,
      sampleRateHz: 0.0,
      lastReceivedTimestampMs: null,
      lastError: null,
    };
    this.bleStatus = {
      state: 'DISCONNECTED', // DISCONNECTED, CONNECTING, CONNECTED_NO_DATA, STREAMING, STALE, ERROR
      deviceName: null,
      deviceId: null,
      serviceUuid: null,
      notificationsReceived: 0,
      parseErrors: 0,
      sampleRateHz: 0.0,
      lastReceivedTimestampMs: null,
      lastValidReading: null,
      lastError: null,
    };
    this.hardwareState = 'DISCONNECTED';
    this.latestHardwareReading = null;
  }

  setActiveTransport(transport) {
    this.activeTransport = transport;
    this.notify('TRANSPORT_CHANGED', { transport });
  }

  setHardwareTelemetry(record) {
    this.latestHardwareReading = record;
    this.hardwareState = 'STREAMING';
    this.activeMode = 'LIVE';

    // Append to timeSeries buffer for real-time charting
    const t = record.timestamp_ms / 1000;
    this.timeSeries.push(t, {
      meas_v: record.voltage_v,
      meas_i: record.current_a,
      meas_p: record.power_w,
      temp_c: record.temperature_c,
      meas_t: record.temperature_c,
      sim_soc: record.soc_percent,
      est_soc: record.soc_percent,
    });

    this.notify('HARDWARE_TELEMETRY', { record });
  }

  updateHardwareState({ transport, state, ...extra }) {
    if (transport === 'usb') {
      this.usbStatus = { ...this.usbStatus, state, ...extra };
      this.notify('USB_STATUS', { usbStatus: this.usbStatus });
    } else if (transport === 'ble') {
      this.bleStatus = { ...this.bleStatus, state, ...extra };
      this.notify('BLE_STATUS', { bleStatus: this.bleStatus });
    }

    // Determine aggregate hardware state based on active transport
    // activeTransport is 'SERIAL' or 'BLE'; transport keys are 'usb' or 'ble'
    const isBlActive = this.activeTransport === 'BLE';
    const currentActiveState = isBlActive ? this.bleStatus.state : this.usbStatus.state;
    this.hardwareState = currentActiveState;
    if (this.hardwareState === 'STREAMING') {
      this.activeMode = 'LIVE';
    } else if (['DISCONNECTED', 'ERROR'].includes(this.hardwareState) && this.activeMode === 'LIVE') {
      this.activeMode = 'IDLE';
    }

    this.notify('HARDWARE_STATE', {
      hardwareState: this.hardwareState,
      activeTransport: this.activeTransport,
      usbStatus: this.usbStatus,
      bleStatus: this.bleStatus,
    });
  }

  setBleStatus(status) {
    this.bleStatus = { ...this.bleStatus, ...status };
    this.updateHardwareState({ transport: 'ble', state: status.state || this.bleStatus.state, ...status });
  }

  setHardwareStatus(status) {
    this.hardwareStatus = status;
    if (status) {
      const mappedState = status.state === 'CONNECTED'
        ? (status.frames_received > 0 ? 'STREAMING' : 'CONNECTED_NO_DATA')
        : (status.state === 'DISCONNECTED' ? 'DISCONNECTED' : status.state);

      this.updateHardwareState({
        transport: 'usb',
        state: mappedState,
        portName: status.port,
        baudRate: status.baud_rate,
        framesReceived: status.frames_received || 0,
        sampleRateHz: status.sample_rate_hz || 0.0,
        lastError: status.last_error,
      });

      if (status.last_valid_reading) {
        this.latestHardwareReading = {
          transport: 'GATEWAY_SERIAL',
          sourceBadge: 'REAL HARDWARE — USB',
          voltage_v: status.last_valid_reading.voltage_v,
          current_a: status.last_valid_reading.current_a,
          power_w: status.last_valid_reading.power_w,
          temperature_c: status.last_valid_reading.temperature_c,
          soc_percent: status.last_valid_reading.soc_fraction ? status.last_valid_reading.soc_fraction * 100 : null,
          receivedAt: Date.now(),
          isStale: false,
        };
      }
    }
    this.notify('HARDWARE_STATUS', { hardwareStatus: status });
  }

  setMockStatus(status) {
    this.mockStatus = status;
    if (status && status.is_running) {
      this.activeMode = 'MOCK';
    }
    this.notify('MOCK_STATUS', { mockStatus: status });
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify(changeType, payload = {}) {
    for (const listener of this.listeners) {
      try {
        listener(changeType, this, payload);
      } catch (err) {
        console.error('Error in state listener:', err);
      }
    }
  }

  setTwinLoadError(error) {
    this.twinLoadError = error || null;
    this.notify('TWIN_LOAD_ERROR', { error: this.twinLoadError });
  }

  setWsStatus(status, latencyMs = null) {
    this.wsStatus = status;
    this.clientLatencyMs = status === 'CONNECTED' && latencyMs !== null ? latencyMs : null;
    this.notify('WS_STATUS', { status, latencyMs });
  }

  setActiveTwin(twinId, statusObj = null) {
    if (twinId === this.activeTwinId && statusObj) {
      this.activeTwinStatus = statusObj;
      this.stepCount = Number.isFinite(statusObj.total_steps) ? statusObj.total_steps : this.stepCount;
      this.anomaliesCount = Number.isFinite(statusObj.total_anomalies) ? statusObj.total_anomalies : null;
      this.notify('TWIN_STATUS', { twinId, status: statusObj });
      return;
    }
    this.activeTwinId = twinId;
    this.activeTwinStatus = statusObj;
    this.activePack = null;
    this.timeSeries.clear();
    this.latestState = null;
    this.latestTelemetry = null;
    this.lastStateReceivedAtMs = null;
    this.stepCount = Number.isFinite(statusObj?.total_steps) ? statusObj.total_steps : 0;
    this.anomaliesCount = Number.isFinite(statusObj?.total_anomalies) ? statusObj.total_anomalies : null;
    this.notify('TWIN_CHANGED', { twinId, status: statusObj });
  }

  setActivePack(pack) {
    this.activePack = pack;
    this.notify('PACK_CHANGED', { pack });
  }

  setTwinsList(twins) {
    this.allTwins = twins || [];
    this.notify('TWINS_LIST', { twins: this.allTwins });
  }

  setPacksList(packs) {
    this.allPacks = packs || [];
    this.notify('PACKS_LIST', { packs: this.allPacks });
  }

  updateTwinState(stateMsg) {
    if (!stateMsg || typeof stateMsg !== 'object' || stateMsg.system_id !== this.activeTwinId
      || !Number.isFinite(stateMsg.timestamp_ns)
      || !Number.isFinite(stateMsg.step_index)) return;
    for (const key of ['terminal_voltage_v', 'simulated_soc', 'temperature_c']) {
      if (!Number.isFinite(stateMsg[key])) return;
    }
    if (this.latestState && (stateMsg.step_index <= this.latestState.step_index
      || stateMsg.timestamp_ns < this.latestState.timestamp_ns)) return;
    this.latestState = stateMsg;
    this.lastStateReceivedAtMs = Date.now();
    this.stepCount = stateMsg.step_index;
    this.anomaliesCount = Number.isFinite(stateMsg.anomalies_count) ? stateMsg.anomalies_count : null;

    // Push into time-series buffer
    const t = stateMsg.timestamp_ns / 1e9;
    const measV = Number.isFinite(stateMsg.diagnostics?.telemetry_voltage_v) ? stateMsg.diagnostics.telemetry_voltage_v : null;
    const measI = Number.isFinite(stateMsg.diagnostics?.telemetry_current_a) ? stateMsg.diagnostics.telemetry_current_a : null;
    const measP = (measV !== null && measI !== null) ? Number((measV * measI).toFixed(3)) : null;

    this.timeSeries.push(t, {
      model_v: stateMsg.terminal_voltage_v,
      sim_soc: Number.isFinite(stateMsg.simulated_soc) ? stateMsg.simulated_soc * 100 : null,
      est_soc: Number.isFinite(stateMsg.estimated_soc) ? stateMsg.estimated_soc * 100 : null,
      temp_c: stateMsg.temperature_c,
      v_res: Number.isFinite(stateMsg.voltage_residual_v) ? stateMsg.voltage_residual_v : null,
      t_res: Number.isFinite(stateMsg.temperature_residual_c) ? stateMsg.temperature_residual_c : null,
      meas_v: measV,
      meas_i: measI,
      meas_p: measP,
    });

    this.notify('STATE_UPDATED', { state: stateMsg });
  }

  addEvent(eventMsg) {
    if (!eventMsg || typeof eventMsg !== 'object' || !Number.isFinite(eventMsg.timestamp_ns)
      || typeof eventMsg.event_type !== 'string' || typeof eventMsg.event_id !== 'string') return;
    this.events.unshift(eventMsg);
    if (this.events.length > this.maxEvents) {
      this.events.pop();
    }
    this.notify('EVENT_RECEIVED', { event: eventMsg });
  }

  notifyTelemetryAck(message) {
    if (message && message.system_id === this.activeTwinId) {
      this.notify('TELEMETRY_ACK', { message });
    }
  }

  setReplayResult(result) {
    this.lastReplayResult = result;
    this.isReplaying = false;
    this.notify('REPLAY_RESULT', { result });
  }

  setMode(mode) {
    this.activeMode = mode;
    this.notify('MODE_CHANGED', { mode });
  }
}

export const store = new AppState();
