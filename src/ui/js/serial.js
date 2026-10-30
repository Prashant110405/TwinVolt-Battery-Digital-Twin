/**
 * TwinVolt Web Serial Client Manager
 *
 * Implements browser-native Web Serial API (navigator.serial) for direct,
 * driverless USB-UART communication with the ESP32 / Arduino microcontroller.
 *
 * Conforms to Requirement 4:
 * - Uses navigator.serial.getPorts() to discover previously granted devices.
 * - Uses navigator.serial.requestPort() with user permission modal.
 * - Opens at 115200 baud (matching ESP32 firmware setting).
 * - Stream line decoding (TextDecoderStream or manual chunk buffering).
 * - Proper reader lock release and clean teardown on disconnect.
 * - Feeds into canonical telemetry pipeline.
 */

import { canonicalPipeline } from './telemetry_pipeline.js';
import { store } from './state.js';

export class WebSerialManager {
  constructor() {
    this.port = null;
    this.reader = null;
    this.keepReading = false;
    this.isConnecting = false;
    this.buffer = '';

    this.baudRate = 115200;
    this.framesReceived = 0;
    this.validFrames = 0;
    this.parseErrors = 0;
    this.lastReceivedTimestampMs = null;
    this.lastValidReading = null;

    this._onDisconnectBound = this._handleDisconnect.bind(this);
  }

  /**
   * Checks whether Web Serial API is supported in the current browser.
   * @returns {{ supported: boolean, reason?: string }}
   */
  checkSupport() {
    if (typeof navigator === 'undefined') {
      return { supported: false, reason: 'Navigator environment unavailable.' };
    }
    if (!navigator.serial) {
      const isSecure = window.isSecureContext;
      const ua = navigator.userAgent;
      let hint = 'Browser does not support the Web Serial API.';
      if (!isSecure) {
        hint += ' Web Serial requires a Secure Context (HTTPS or localhost).';
      } else if (ua.includes('Firefox')) {
        hint += ' Firefox does not support Web Serial. Please use Google Chrome, Microsoft Edge, or Opera.';
      } else if (ua.includes('Safari') && !ua.includes('Chrome')) {
        hint += ' Safari does not support Web Serial. Please use Google Chrome or Microsoft Edge.';
      }
      return { supported: false, reason: hint };
    }
    return { supported: true };
  }

  /**
   * Returns list of already-authorized Web Serial ports.
   */
  async getAuthorizedPorts() {
    if (!this.checkSupport().supported) return [];
    try {
      return await navigator.serial.getPorts();
    } catch (err) {
      console.warn('[WebSerial] Failed to get authorized ports:', err);
      return [];
    }
  }

  /**
   * Requests user authorization for a serial port and opens it at 115200 baud.
   */
  async requestAndConnect(baud = 115200) {
    const support = this.checkSupport();
    if (!support.supported) {
      canonicalPipeline.setTransportState('usb', 'ERROR', { error: support.reason });
      throw new Error(support.reason);
    }

    if (this.isConnecting) return;
    this.isConnecting = true;

    canonicalPipeline.setTransportState('usb', 'CONNECTING');

    try {
      // 1. Request port from user
      this.port = await navigator.serial.requestPort();
      if (!this.port) {
        throw new Error('No serial port was selected.');
      }

      this.baudRate = baud;

      // 2. Open port
      await this.port.open({
        baudRate: this.baudRate,
        dataBits: 8,
        stopBits: 1,
        parity: 'none',
        bufferSize: 4096,
      });

      console.info(`[WebSerial] Port opened at ${this.baudRate} baud.`);

      // 3. Listen for hardware unplug events
      navigator.serial.addEventListener('disconnect', this._onDisconnectBound);

      canonicalPipeline.setTransportState('usb', 'CONNECTED_NO_DATA', {
        portName: 'Web Serial Device',
        baudRate: this.baudRate,
      });

      // 4. Start read loop
      this.keepReading = true;
      this.isConnecting = false;
      this._readLoop().catch((err) => {
        console.warn('[WebSerial] Read loop terminated:', err);
      });

      return { success: true, baudRate: this.baudRate };
    } catch (err) {
      this.isConnecting = false;
      await this._cleanup();

      const errMsg = err.name === 'NotFoundError'
        ? 'Serial device selection was cancelled by the user.'
        : `Web Serial connection error: ${err.message}`;

      canonicalPipeline.setTransportState('usb', 'ERROR', { error: errMsg });
      console.error('[WebSerial] Connection failure:', err);
      throw new Error(errMsg);
    }
  }

  async _readLoop() {
    const textDecoder = new TextDecoderStream();
    const readableStreamClosed = this.port.readable.pipeTo(textDecoder.writable);
    const reader = textDecoder.readable.getReader();
    this.reader = reader;

    try {
      while (this.keepReading) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        if (value) {
          this._handleChunk(value);
        }
      }
    } catch (err) {
      if (this.keepReading) {
        console.warn('[WebSerial] Stream read error:', err);
        canonicalPipeline.setTransportState('usb', 'ERROR', { error: err.message });
      }
    } finally {
      try {
        reader.releaseLock();
      } catch (_) {}
      await readableStreamClosed.catch(() => {});
    }
  }

  _handleChunk(chunk) {
    this.buffer += chunk;
    const lines = this.buffer.split(/\r?\n/);
    // Keep incomplete tail
    this.buffer = lines.pop();

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      this.framesReceived++;
      const nowMs = Date.now();

      // Feed into canonical pipeline
      const rec = canonicalPipeline.ingest(trimmed, 'USB_SERIAL');
      if (rec && rec.is_valid) {
        this.validFrames++;
        this.lastReceivedTimestampMs = nowMs;
        this.lastValidReading = rec;
      } else {
        this.parseErrors++;
      }
    }
  }

  async disconnect() {
    console.info('[WebSerial] Disconnecting...');
    this.keepReading = false;
    await this._cleanup();
    canonicalPipeline.setTransportState('usb', 'DISCONNECTED');
    console.info('[WebSerial] Disconnected cleanly.');
  }

  _handleDisconnect(event) {
    if (event.target === this.port) {
      console.warn('[WebSerial] Hardware USB device was unplugged.');
      this.disconnect();
    }
  }

  async _cleanup() {
    this.keepReading = false;
    if (this.reader) {
      try {
        await this.reader.cancel();
      } catch (_) {}
      this.reader = null;
    }
    if (this.port) {
      try {
        await this.port.close();
      } catch (_) {}
      this.port = null;
    }
    navigator.serial?.removeEventListener('disconnect', this._onDisconnectBound);
  }
}

export const webSerialManager = new WebSerialManager();
