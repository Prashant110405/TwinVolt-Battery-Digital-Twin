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

    // Replay State
    this.activeMode = 'LIVE'; // LIVE, REPLAY
    this.lastReplayResult = null;
    this.isReplaying = false;
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

    this.timeSeries.push(t, {
      model_v: stateMsg.terminal_voltage_v,
      sim_soc: Number.isFinite(stateMsg.simulated_soc) ? stateMsg.simulated_soc * 100 : null,
      est_soc: Number.isFinite(stateMsg.estimated_soc) ? stateMsg.estimated_soc * 100 : null,
      temp_c: stateMsg.temperature_c,
      v_res: Number.isFinite(stateMsg.voltage_residual_v) ? stateMsg.voltage_residual_v : null,
      t_res: Number.isFinite(stateMsg.temperature_residual_c) ? stateMsg.temperature_residual_c : null,
      meas_v: Number.isFinite(stateMsg.diagnostics?.telemetry_voltage_v) ? stateMsg.diagnostics.telemetry_voltage_v : null,
      meas_i: Number.isFinite(stateMsg.diagnostics?.telemetry_current_a) ? stateMsg.diagnostics.telemetry_current_a : null,
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
