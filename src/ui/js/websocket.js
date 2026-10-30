/**
 * Native WebSocket Real-Time Client for TwinVolt
 * Manages connection lifecycles, auto-reconnect, heartbeat ping/pong, and state dispatching.
 *
 * WebSocket URL resolution supports both deployment modes:
 *  • Same-origin (local dev / Docker): resolveWsBaseUrl() returns ws(s)://window.location.host
 *  • Cross-origin (Vercel + separate backend): window.TWINVOLT_WS_BASE_URL set by config.js
 */

import { store } from './state.js';
import { resolveWsBaseUrl } from './api.js';

class WebSocketClient {
  constructor() {
    this.ws = null;
    this.systemId = null;
    this.reconnectTimer = null;
    this.pingTimer = null;
    this.pingSentTime = 0;
    this.reconnectAttempts = 0;
    this.maxReconnectDelayMs = 5000;
    this.isExplicitDisconnect = false;
  }

  connect(systemId = null) {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      if (this.systemId === systemId) return;
      this.disconnect();
    }

    this.systemId = systemId;
    this.isExplicitDisconnect = false;

    // Resolve WebSocket base URL — supports both same-origin (local dev) and
    // cross-origin (Vercel frontend + separate persistent backend) modes.
    const wsBase = resolveWsBaseUrl();
    const path = systemId
      ? `/api/v1/ws/twins/${encodeURIComponent(systemId)}`
      : '/api/v1/ws';

    const wsUrl = wsBase + path;
    store.setWsStatus('RECONNECTING');

    try {
      this.ws = new WebSocket(wsUrl);
      const socket = this.ws;

      socket.onopen = () => {
        if (this.ws !== socket) return;
        this.reconnectAttempts = 0;
        store.setWsStatus('CONNECTED');
        this._startHeartbeat();
      };

      socket.onmessage = (evt) => {
        if (this.ws !== socket) return;
        try {
          const msg = JSON.parse(evt.data);
          this._handleMessage(msg);
        } catch (err) {
          console.warn('[WS] Failed to parse message JSON:', err);
        }
      };

      socket.onclose = () => {
        if (this.ws !== socket) return;
        this.ws = null;
        this._stopHeartbeat();
        store.setWsStatus('DISCONNECTED');
        if (!this.isExplicitDisconnect) {
          this._scheduleReconnect();
        }
      };

      socket.onerror = (err) => {
        if (this.ws !== socket) return;
        console.warn('[WS] Error:', err);
      };
    } catch (err) {
      console.error('[WS] Connection creation failed:', err);
      store.setWsStatus('DISCONNECTED');
      this._scheduleReconnect();
    }
  }

  disconnect() {
    this.isExplicitDisconnect = true;
    this._stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    store.setWsStatus('DISCONNECTED');
  }

  sendMessage(payload) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Cannot send message, socket not OPEN.');
      return false;
    }
    this.ws.send(JSON.stringify(payload));
    return true;
  }

  sendPing() {
    this.pingSentTime = Date.now();
    return this.sendMessage({ type: 'ping' });
  }

  sendTelemetry(payload) {
    return this.sendMessage({
      type: 'telemetry_ingest',
      system_id: this.systemId,
      ...payload,
    });
  }

  _handleMessage(msg) {
    switch (msg.type) {
      case 'connected':
        store.setWsStatus('CONNECTED');
        break;

      case 'pong':
        if (this.pingSentTime > 0) {
          const latency = Date.now() - this.pingSentTime;
          store.setWsStatus('CONNECTED', latency);
        }
        break;

      case 'telemetry_ack':
        store.notifyTelemetryAck(msg);
        break;

      case 'twin_state':
        store.updateTwinState(msg);
        break;

      case 'twin_event':
        store.addEvent(msg);
        break;

      case 'error':
        console.warn('[WS Server Error]', msg.code, msg.message);
        break;

      default:
        break;
    }
  }

  _startHeartbeat() {
    this._stopHeartbeat();
    this.sendPing();
    this.pingTimer = setInterval(() => {
      this.sendPing();
    }, 5000);
  }

  _stopHeartbeat() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  _scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelayMs);
    store.setWsStatus('RECONNECTING');
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect(this.systemId);
    }, delay);
  }
}

export const wsClient = new WebSocketClient();
