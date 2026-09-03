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
      this.data[key].push(value !== undefined && value !== null ? Number(value) : null);
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

    // Active Selection State
    this.activeTwinId = null;
    this.activePack = null;
    this.activeTwinStatus = null;
    this.allTwins = [];
    this.allPacks = [];

    // Current Telemetry & State Readouts
    this.latestState = null;
    this.latestTelemetry = null;
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

  setWsStatus(status, latencyMs = null) {
    this.wsStatus = status;
    if (latencyMs !== null) {
      this.clientLatencyMs = latencyMs;
    }
    this.notify('WS_STATUS', { status, latencyMs });
  }

  setActiveTwin(twinId, statusObj = null) {
    this.activeTwinId = twinId;
    this.activeTwinStatus = statusObj;
    this.timeSeries.clear();
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
    this.latestState = stateMsg;
    this.stepCount = stateMsg.step_index || this.stepCount + 1;
    this.anomaliesCount = stateMsg.anomalies_count || 0;

    // Push into time-series buffer
    const t = stateMsg.timestamp_ns
      ? stateMsg.timestamp_ns / 1e9
      : Date.now() / 1000;

    this.timeSeries.push(t, {
      model_v: stateMsg.terminal_voltage_v,
      sim_soc: stateMsg.simulated_soc !== undefined ? stateMsg.simulated_soc * 100 : null,
      est_soc: stateMsg.estimated_soc !== undefined && stateMsg.estimated_soc !== null ? stateMsg.estimated_soc * 100 : null,
      temp_c: stateMsg.temperature_c,
      v_res: stateMsg.voltage_residual_v,
      t_res: stateMsg.temperature_residual_c,
      meas_v: stateMsg.diagnostics?.telemetry_voltage_v || null,
      meas_i: stateMsg.diagnostics?.telemetry_current_a || null,
    });

    this.notify('STATE_UPDATED', { state: stateMsg });
  }

  addEvent(eventMsg) {
    this.events.unshift(eventMsg);
    if (this.events.length > this.maxEvents) {
      this.events.pop();
    }
    this.notify('EVENT_RECEIVED', { event: eventMsg });
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
