/**
 * TwinVolt Bluetooth Low Energy (BLE) Client Manager
 *
 * Implements Web Bluetooth GATT connectivity for the ESP32 TwinVolt battery monitor:
 * - Device discovery filtered by device name ("Twin Volt") and Primary Service UUID
 * - GATT connection lifecycle and unexpected disconnect handling
 * - Telemetry characteristic notification subscription and MTU framing decode
 * - Payload validation, unit normalization, and shared telemetry pipeline ingestion
 */

import { api } from './api.js';
import { store } from './state.js';
import { wsClient } from './websocket.js';
import { canonicalPipeline } from './telemetry_pipeline.js';

export const TWINVOLT_BLE_CONFIG = {
  DEVICE_NAME: 'Twin Volt',
  SERVICE_UUID: '7a100001-1234-5678-1234-56789abcdef0',
  TELEMETRY_CHAR_UUID: '7a100002-1234-5678-1234-56789abcdef0',
  CONTROL_CHAR_UUID: '7a100003-1234-5678-1234-56789abcdef0',
};

export class BleConnectionManager {
  constructor() {
    this.device = null;
    this.server = null;
    this.service = null;
    this.telemetryChar = null;
    this.controlChar = null;

    this.isConnecting = false;
    this.notificationsCount = 0;
    this.parseErrorsCount = 0;
    this.recentRecords = [];
    this.maxRecentRecords = 50;

    this._onNotificationBound = this._handleNotification.bind(this);
    this._onDisconnectedBound = this._handleDisconnected.bind(this);

    this._timestampsWindow = [];
    this._sampleRateHz = 0.0;
  }

  /**
   * Checks whether Web Bluetooth API is supported in the current browser and context.
   * @returns {{ supported: boolean, reason?: string }}
   */
  checkSupport() {
    if (typeof navigator === 'undefined') {
      return { supported: false, reason: 'Navigator environment unavailable.' };
    }
    if (!navigator.bluetooth) {
      const isSecure = window.isSecureContext;
      const ua = navigator.userAgent;
      let hint = 'Browser does not support Web Bluetooth.';
      if (!isSecure) {
        hint += ' Note: Web Bluetooth requires a Secure Context (HTTPS or localhost).';
      } else if (ua.includes('Firefox')) {
        hint += ' Firefox does not support Web Bluetooth. Please use Chrome, Edge, or Opera.';
      } else if (ua.includes('Safari') && !ua.includes('Chrome')) {
        hint += ' Safari on macOS does not support Web Bluetooth. Please use Chrome or Edge.';
      }
      return { supported: false, reason: hint };
    }
    return { supported: true };
  }

  /**
   * Prompts user to select the Twin Volt ESP32 device and establishes GATT connection.
   * Must be called in response to a user gesture (e.g. click).
   */
  async connect() {
    const support = this.checkSupport();
    if (!support.supported) {
      store.setBleStatus({
        state: 'ERROR',
        lastError: support.reason,
      });
      throw new Error(support.reason);
    }

    if (this.isConnecting) return;
    this.isConnecting = true;

    canonicalPipeline.setTransportState('ble', 'CONNECTING');

    try {
      // 1. Request user authorization for Twin Volt device
      const options = {
        filters: [
          { name: TWINVOLT_BLE_CONFIG.DEVICE_NAME },
          { namePrefix: 'Twin' },
          { services: [TWINVOLT_BLE_CONFIG.SERVICE_UUID] },
        ],
        optionalServices: [TWINVOLT_BLE_CONFIG.SERVICE_UUID],
      };

      try {
        this.device = await navigator.bluetooth.requestDevice(options);
      } catch (filterErr) {
        // Fallback: If device is paired without advertised service in scan response, prompt with acceptAllDevices
        console.warn('[BLE] Filtered requestDevice failed, attempting general discovery:', filterErr.message);
        this.device = await navigator.bluetooth.requestDevice({
          acceptAllDevices: true,
          optionalServices: [TWINVOLT_BLE_CONFIG.SERVICE_UUID],
        });
      }

      if (!this.device) {
        throw new Error('No Bluetooth device was selected.');
      }

      console.info(`[BLE] Device selected: ${this.device.name || 'Unnamed'} (ID: ${this.device.id})`);

      // Register disconnect listener before connecting
      this.device.removeEventListener('gattserverdisconnected', this._onDisconnectedBound);
      this.device.addEventListener('gattserverdisconnected', this._onDisconnectedBound);

      // 2. Connect GATT Server
      this.server = await this.device.gatt.connect();
      console.info('[BLE] GATT Server connected.');

      // 3. Discover Primary Telemetry Service
      this.service = await this.server.getPrimaryService(TWINVOLT_BLE_CONFIG.SERVICE_UUID);
      console.info(`[BLE] Primary Service ${TWINVOLT_BLE_CONFIG.SERVICE_UUID} discovered.`);

      // 4. Retrieve Telemetry Characteristic
      this.telemetryChar = await this.service.getCharacteristic(TWINVOLT_BLE_CONFIG.TELEMETRY_CHAR_UUID);
      console.info(`[BLE] Telemetry Characteristic ${TWINVOLT_BLE_CONFIG.TELEMETRY_CHAR_UUID} retrieved.`);

      // 5. Try discovering optional Control Characteristic
      try {
        this.controlChar = await this.service.getCharacteristic(TWINVOLT_BLE_CONFIG.CONTROL_CHAR_UUID);
      } catch (_) {
        this.controlChar = null;
      }

      // 6. Subscribe to Telemetry Notifications
      this.telemetryChar.removeEventListener('characteristicvaluechanged', this._onNotificationBound);
      this.telemetryChar.addEventListener('characteristicvaluechanged', this._onNotificationBound);
      await this.telemetryChar.startNotifications();
      console.info('[BLE] Telemetry notifications started.');

      this.isConnecting = false;
      this.notificationsCount = 0;
      this.parseErrorsCount = 0;
      this._timestampsWindow = [];

      canonicalPipeline.setTransportState('ble', 'CONNECTED_NO_DATA', {
        deviceName: this.device.name || TWINVOLT_BLE_CONFIG.DEVICE_NAME,
        deviceId: this.device.id,
        serviceUuid: TWINVOLT_BLE_CONFIG.SERVICE_UUID,
        notificationsReceived: 0,
        parseErrors: 0,
        sampleRateHz: 0.0,
      });

      return {
        success: true,
        deviceName: this.device.name || TWINVOLT_BLE_CONFIG.DEVICE_NAME,
        deviceId: this.device.id,
      };
    } catch (err) {
      this.isConnecting = false;
      this._cleanupGatt();

      const errMsg = err.name === 'NotFoundError'
        ? 'Bluetooth device selection was cancelled by the user.'
        : `BLE connection error: ${err.message}`;

      canonicalPipeline.setTransportState('ble', 'ERROR', { lastError: errMsg });
      console.error('[BLE] Connection failure:', err);
      throw new Error(errMsg);
    }
  }

  /**
   * Gracefully disconnects active BLE GATT connection and cleans up listeners.
   */
  async disconnect() {
    if (this.telemetryChar) {
      try {
        this.telemetryChar.removeEventListener('characteristicvaluechanged', this._onNotificationBound);
        await this.telemetryChar.stopNotifications();
      } catch (err) {
        console.warn('[BLE] Error stopping notifications during disconnect:', err.message);
      }
    }

    if (this.device) {
      this.device.removeEventListener('gattserverdisconnected', this._onDisconnectedBound);
      if (this.device.gatt && this.device.gatt.connected) {
        this.device.gatt.disconnect();
      }
    }

    this._cleanupGatt();
    canonicalPipeline.setTransportState('ble', 'DISCONNECTED');
    console.info('[BLE] Disconnected cleanly.');
  }

  _cleanupGatt() {
    this.server = null;
    this.service = null;
    this.telemetryChar = null;
    this.controlChar = null;
  }

  _handleDisconnected() {
    console.warn('[BLE] Device disconnected unexpectedly.');
    this._cleanupGatt();
    canonicalPipeline.setTransportState('ble', 'DISCONNECTED', {
      lastError: 'Device disconnected unexpectedly.',
    });
  }

  /**
   * Decodes incoming BLE notification buffer, normalizes telemetry, and feeds the shared pipeline.
   * @param {Event} event - characteristicvaluechanged event
   */
  _handleNotification(event) {
    const value = event.target.value;
    if (!value || value.byteLength === 0) return;

    this.notificationsCount++;
    const nowMs = Date.now();
    const nowS = nowMs / 1000;
    this._updateSampleRate(nowS);

    const decoder = new TextDecoder('utf-8');
    const rawText = decoder.decode(value).trim();

    try {
      const rec = canonicalPipeline.ingest(rawText, 'BLE');
      if (rec && rec.is_valid) {
        this._recordReceived(rec, nowMs);
      } else {
        this.parseErrorsCount++;
      }
    } catch (err) {
      this.parseErrorsCount++;
    }
  }

  /**
   * Flexible payload parser supporting canonical JSON, compact JSON, and CSV.
   */
  _parsePayload(rawText, nowMs) {
    // 1. JSON Format Check
    if (rawText.startsWith('{') && rawText.endsWith('}')) {
      const parsed = JSON.parse(rawText);

      // Support both canonical field names and compact micro-keys
      const v = Number.isFinite(parsed.pack_voltage_v) ? parsed.pack_voltage_v : (Number.isFinite(parsed.voltage_v) ? parsed.voltage_v : (Number.isFinite(parsed.v) ? parsed.v : null));
      const i = Number.isFinite(parsed.pack_current_a) ? parsed.pack_current_a : (Number.isFinite(parsed.current_a) ? parsed.current_a : (Number.isFinite(parsed.i) ? parsed.i : 0.0));
      const temp = Number.isFinite(parsed.ambient_temperature_c) ? parsed.ambient_temperature_c : (Number.isFinite(parsed.temperature_c) ? parsed.temperature_c : (Number.isFinite(parsed.t) ? parsed.t : null));
      const soc = Number.isFinite(parsed.soc_fraction) ? parsed.soc_fraction : (Number.isFinite(parsed.soc) ? parsed.soc / 100 : null);

      if (v === null || isNaN(v) || v <= 0.0) {
        return { is_valid: false, error: 'Missing or negative pack voltage.', raw: rawText };
      }

      const p = Number.isFinite(parsed.pack_power_w) ? parsed.pack_power_w : (Number.isFinite(parsed.power_w) ? parsed.power_w : (Number.isFinite(parsed.p) ? parsed.p : Number((v * (i || 0)).toFixed(2))));

      return {
        is_valid: true,
        source_id: parsed.system_id || store.activeTwinId || 'twin_prototype_3s1p',
        timestamp_ms: parsed.millis ? parsed.millis : nowMs,
        voltage_v: Number(v.toFixed(3)),
        current_a: Number(i.toFixed(3)),
        power_w: Number(p.toFixed(2)),
        temperature_c: temp !== null ? Number(temp.toFixed(1)) : 25.0,
        soc_fraction: soc,
        relay_state: parsed.relay_state !== undefined ? Boolean(parsed.relay_state) : null,
        fan_state: parsed.fan_state !== undefined ? Boolean(parsed.fan_state) : null,
        raw_payload: rawText,
      };
    }

    // 2. CSV Format Check: "timestamp_ms,voltage_v,current_a,temperature_c"
    const parts = rawText.split(',').map((s) => s.trim());
    if (parts.length >= 2) {
      const v = parseFloat(parts[1] || parts[0]);
      const i = parts.length >= 3 ? parseFloat(parts[2] || '0') : 0.0;
      const t = parts.length >= 4 ? parseFloat(parts[3] || '25') : 25.0;

      if (Number.isFinite(v) && v > 0.0) {
        return {
          is_valid: true,
          source_id: store.activeTwinId || 'twin_prototype_3s1p',
          timestamp_ms: nowMs,
          voltage_v: Number(v.toFixed(3)),
          current_a: Number.isFinite(i) ? Number(i.toFixed(3)) : 0.0,
          power_w: Number((v * (Number.isFinite(i) ? i : 0)).toFixed(2)),
          temperature_c: Number.isFinite(t) ? Number(t.toFixed(1)) : 25.0,
          soc_fraction: null,
          raw_payload: rawText,
        };
      }
    }

    return { is_valid: false, error: 'Unrecognized format (expected JSON or CSV).', raw: rawText };
  }

  _recordReceived(record, nowMs) {
    this.recentRecords.push({
      ...record,
      received_at_ms: nowMs,
    });
    if (this.recentRecords.length > this.maxRecentRecords) {
      this.recentRecords.shift();
    }

    store.setBleStatus({
      notificationsReceived: this.notificationsCount,
      parseErrors: this.parseErrorsCount,
      sampleRateHz: this._sampleRateHz,
      lastReceivedTimestampMs: nowMs,
      lastValidReading: record,
      lastError: null,
      freshness: 'VALID',
    });

    // NOTE: Backend co-simulation ingestion is already handled by
    // canonicalPipeline.ingest() → _stepDigitalTwin() in the notification
    // handler. Do NOT send telemetry to backend again here — that would
    // cause double-stepping of the digital twin for every BLE frame.
  }

  _updateSampleRate(nowS) {
    this._timestampsWindow.push(nowS);
    if (this._timestampsWindow.length > 20) {
      this._timestampsWindow.shift();
    }
    if (this._timestampsWindow.length >= 2) {
      const dt = this._timestampsWindow[this._timestampsWindow.length - 1] - this._timestampsWindow[0];
      if (dt > 0.0) {
        this._sampleRateHz = Number(((this._timestampsWindow.length - 1) / dt).toFixed(1));
      }
    }
  }

  getRecentRecords() {
    return [...this.recentRecords];
  }
}

export const bleManager = new BleConnectionManager();
