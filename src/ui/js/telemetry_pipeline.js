/**
 * TwinVolt Canonical Telemetry Pipeline
 *
 * Implements a unified validation, normalization, and distribution pipeline
 * for all telemetry sources (Web Serial, Backend USB Serial, Web Bluetooth BLE,
 * and Simulation).
 *
 * Features:
 * - Strict physical range validation (3S Li-Ion pack defaults).
 * - Zero-value preservation (e.g. 0.0A load current).
 * - Real-time Coulomb Counting SoC estimation.
 * - Hardware connection state machine: DISCONNECTED, CONNECTING, CONNECTED_NO_DATA, STREAMING, STALE, ERROR.
 * - Stale-data watchdog timer (configurable timeout, default 3.0s).
 * - Co-simulation step triggering via REST/WebSocket.
 */

import { api } from './api.js';
import { store } from './state.js';
import { wsClient } from './websocket.js';

// Physical Battery Constraints (Default 3S Li-Ion configuration)
export const BATTERY_PHYSICAL_LIMITS = {
  NOMINAL_VOLTAGE_V: 11.1,
  MIN_PLAUSIBLE_VOLTAGE_V: 0.5,
  MAX_PLAUSIBLE_VOLTAGE_V: 20.0,
  PACK_V_MIN_SAFE: 9.0,
  PACK_V_MAX_SAFE: 12.75,
  MIN_PLAUSIBLE_CURRENT_A: -30.0,
  MAX_PLAUSIBLE_CURRENT_A: 30.0,
  MIN_PLAUSIBLE_TEMP_C: -20.0,
  MAX_PLAUSIBLE_TEMP_C: 90.0,
  NOMINAL_CAPACITY_AH: 2.2, // 3S1P 18650 2200mAh pack
};

export class CanonicalTelemetryPipeline {
  constructor() {
    this.staleTimeoutMs = 3000;
    this.watchdogTimer = null;
    this.lastFrameTimestampMs = null;
    this.lastValidRecord = null;
    this.activeSource = null; // 'USB_SERIAL' | 'BLE' | 'GATEWAY_SERIAL' | 'BENCH'

    // Coulomb counting state
    this.coulombSocPercent = 92.0; // Initialized from baseline or model
    this.lastCoulombTimeMs = null;

    // Transport states
    this.transportStates = {
      usb: 'DISCONNECTED', // DISCONNECTED, CONNECTING, CONNECTED_NO_DATA, STREAMING, STALE, ERROR
      ble: 'DISCONNECTED',
    };

    this.metrics = {
      framesReceived: 0,
      validFrames: 0,
      parseErrors: 0,
      sampleRateHz: 0.0,
    };

    this._sampleTimestamps = [];
    this._startWatchdog();
  }

  _startWatchdog() {
    if (this.watchdogTimer) clearInterval(this.watchdogTimer);
    this.watchdogTimer = setInterval(() => this._checkFreshness(), 1000);
  }

  _checkFreshness() {
    const now = Date.now();
    for (const transport of ['usb', 'ble']) {
      if (this.transportStates[transport] === 'STREAMING') {
        if (this.lastFrameTimestampMs && now - this.lastFrameTimestampMs > this.staleTimeoutMs) {
          this.setTransportState(transport, 'STALE');
          if (store.latestHardwareReading) {
            store.latestHardwareReading.isStale = true;
            store.notify('HARDWARE_STALE', { transport });
          }
        }
      }
    }
  }

  setTransportState(transport, state, extra = {}) {
    this.transportStates[transport] = state;
    if (state === 'STREAMING') {
      this.lastFrameTimestampMs = Date.now();
    } else if (state === 'DISCONNECTED') {
      if (this.activeSource === transport.toUpperCase()) {
        this.activeSource = null;
      }
    }

    store.updateHardwareState({
      transport,
      state,
      ...extra,
    });
  }

  /**
   * Ingests a raw or parsed frame from any transport.
   *
   * @param {Object|string} rawPayload
   * @param {string} transport - 'USB_SERIAL' | 'BLE' | 'GATEWAY_SERIAL' | 'BENCH'
   * @returns {Object|null} Normalized canonical record, or null if invalid.
   */
  ingest(rawPayload, transport = 'USB_SERIAL') {
    this.metrics.framesReceived++;
    const nowMs = Date.now();

    // 1. Parse JSON if string
    let parsed = rawPayload;
    if (typeof rawPayload === 'string') {
      try {
        const trimmed = rawPayload.trim();
        if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || trimmed.includes('{')) {
          const jsonStart = trimmed.indexOf('{');
          const jsonEnd = trimmed.lastIndexOf('}');
          parsed = JSON.parse(trimmed.slice(jsonStart, jsonEnd + 1));
        } else {
          parsed = this._parseCsv(trimmed);
        }
      } catch (err) {
        this.metrics.parseErrors++;
        return null;
      }
    }

    if (!parsed || typeof parsed !== 'object') {
      this.metrics.parseErrors++;
      return null;
    }

    // 2. Normalize and Validate Fields
    const normalized = this._normalize(parsed, transport, nowMs);
    if (!normalized.is_valid) {
      this.metrics.parseErrors++;
      return null;
    }

    this.metrics.validFrames++;
    this.lastFrameTimestampMs = nowMs;
    this.lastValidRecord = normalized;
    this.activeSource = transport;

    // Update transport state to STREAMING
    const transportKey = transport.toLowerCase().includes('ble') ? 'ble' : 'usb';
    this.setTransportState(transportKey, 'STREAMING', {
      lastValidReading: normalized,
      sampleRateHz: this._calcSampleRate(nowMs),
    });

    // 3. Update Coulomb Counting SoC
    this._updateCoulombSoc(normalized, nowMs);

    // 4. Update Global Store
    store.setHardwareTelemetry(normalized);

    // 5. Trigger Digital Twin Co-Simulation Step
    this._stepDigitalTwin(normalized, nowMs);

    return normalized;
  }

  _parseCsv(csvLine) {
    const parts = csvLine.split(',').map((s) => s.trim());
    if (parts.length >= 2) {
      const v = parseFloat(parts[0]);
      const i = parseFloat(parts[1] || '0');
      const t = parseFloat(parts[2] || '25');
      if (!isNaN(v)) {
        return { pack_voltage_v: v, pack_current_a: i, ambient_temperature_c: t };
      }
    }
    return null;
  }

  _normalize(p, transport, nowMs) {
    // Extract Voltage
    let v = null;
    if (Number.isFinite(p.pack_voltage_v)) v = p.pack_voltage_v;
    else if (Number.isFinite(p.voltage_v)) v = p.voltage_v;
    else if (Number.isFinite(p.v)) v = p.v;

    // Extract Current (preserve valid 0.0)
    let i = null;
    if (Number.isFinite(p.pack_current_a)) i = p.pack_current_a;
    else if (Number.isFinite(p.current_a)) i = p.current_a;
    else if (Number.isFinite(p.i)) i = p.i;

    // Extract Temperature
    let t = null;
    if (Number.isFinite(p.ambient_temperature_c)) t = p.ambient_temperature_c;
    else if (Number.isFinite(p.temperature_c)) t = p.temperature_c;
    else if (Number.isFinite(p.temp_c)) t = p.temp_c;
    else if (Number.isFinite(p.t)) t = p.t;

    // Validate Voltage bounds
    if (v === null || isNaN(v) || v < BATTERY_PHYSICAL_LIMITS.MIN_PLAUSIBLE_VOLTAGE_V || v > BATTERY_PHYSICAL_LIMITS.MAX_PLAUSIBLE_VOLTAGE_V) {
      return { is_valid: false, error: `Voltage ${v} out of plausible bounds` };
    }

    // Validate Current bounds
    if (i !== null && (i < BATTERY_PHYSICAL_LIMITS.MIN_PLAUSIBLE_CURRENT_A || i > BATTERY_PHYSICAL_LIMITS.MAX_PLAUSIBLE_CURRENT_A)) {
      return { is_valid: false, error: `Current ${i} out of plausible bounds` };
    }

    // Validate Temperature bounds
    if (t !== null && (t < BATTERY_PHYSICAL_LIMITS.MIN_PLAUSIBLE_TEMP_C || t > BATTERY_PHYSICAL_LIMITS.MAX_PLAUSIBLE_TEMP_C)) {
      t = 25.0; // fallback to standard ambient
    }

    // Calculate Power: P = V * I only when both are valid
    const currentA = i !== null ? Number(i.toFixed(3)) : 0.0;
    const voltageV = Number(v.toFixed(3));
    const powerW = Number((voltageV * currentA).toFixed(2));

    // Determine Source Badge
    let sourceBadge = 'REAL HARDWARE — USB';
    if (transport === 'BLE') {
      sourceBadge = 'REAL HARDWARE — BLE';
    } else if (transport === 'BENCH' || transport === 'MOCK') {
      sourceBadge = 'SIMULATION';
    }

    return {
      is_valid: true,
      device_id: 'twinvolt_esp32',
      system_id: p.system_id || store.activeTwinId || 'twin_prototype_3s1p',
      transport,
      sourceBadge,
      sequence: p.sequence !== undefined ? Number(p.sequence) : (p.millis || null),
      millis: p.millis || null,
      timestamp_ms: nowMs,
      voltage_v: voltageV,
      current_a: currentA,
      power_w: powerW,
      temperature_c: t !== null ? Number(t.toFixed(1)) : 25.0,
      relay_state: p.relay_state !== undefined ? Boolean(p.relay_state) : null,
      fan_state: p.fan_state !== undefined ? Boolean(p.fan_state) : null,
      soc_percent: this.coulombSocPercent,
      soh_percent: null, // SOH cannot be claimed from voltage alone without degradation history
      isStale: false,
    };
  }

  _updateCoulombSoc(rec, nowMs) {
    if (this.lastCoulombTimeMs !== null) {
      const dtS = Math.max(0.1, Math.min(10.0, (nowMs - this.lastCoulombTimeMs) / 1000));
      // In TwinVolt firmware: positive current = discharge current through load
      // Coulomb counting: deltaSoc = - (I * dt) / (3600 * Cap) * 100
      const capAh = BATTERY_PHYSICAL_LIMITS.NOMINAL_CAPACITY_AH;
      const deltaSoc = - (rec.current_a * dtS) / (3600 * capAh) * 100;
      this.coulombSocPercent = Math.max(0.0, Math.min(100.0, this.coulombSocPercent + deltaSoc));
    }
    this.lastCoulombTimeMs = nowMs;
    rec.soc_percent = Number(this.coulombSocPercent.toFixed(1));
  }

  _calcSampleRate(nowMs) {
    this._sampleTimestamps.push(nowMs);
    if (this._sampleTimestamps.length > 20) {
      this._sampleTimestamps.shift();
    }
    if (this._sampleTimestamps.length >= 2) {
      const spanS = (this._sampleTimestamps[this._sampleTimestamps.length - 1] - this._sampleTimestamps[0]) / 1000;
      if (spanS > 0) {
        this.metrics.sampleRateHz = Number(((this._sampleTimestamps.length - 1) / spanS).toFixed(1));
      }
    }
    return this.metrics.sampleRateHz;
  }

  _stepDigitalTwin(rec, nowMs) {
    const payload = {
      system_id: rec.system_id,
      timestamp_ns: nowMs * 1_000_000,
      pack_voltage_v: rec.voltage_v,
      pack_current_a: rec.current_a,
      pack_power_w: rec.power_w,
      ambient_temperature_c: rec.temperature_c,
      source: rec.transport,
    };

    // Prefer WebSocket if open for zero latency, otherwise REST
    if (wsClient.ws && wsClient.ws.readyState === WebSocket.OPEN) {
      wsClient.sendTelemetry(payload);
    } else {
      api.ingestTelemetry(payload).catch((err) => {
        console.warn('[Pipeline] REST co-simulation step notice:', err.message);
      });
    }
  }

  destroy() {
    if (this.watchdogTimer) {
      clearInterval(this.watchdogTimer);
      this.watchdogTimer = null;
    }
  }
}

export const canonicalPipeline = new CanonicalTelemetryPipeline();
