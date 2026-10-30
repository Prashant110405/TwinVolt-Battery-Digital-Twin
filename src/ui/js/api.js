/**
 * Thin HTTP REST Client for TwinVolt API
 * Communicates strictly through verified Subtask 4.2 endpoints.
 *
 * BASE URL RESOLUTION (priority order):
 *  1. window.TWINVOLT_API_BASE_URL — set by config.js injected in index.html for
 *     Vercel / production deployments where the backend runs on a separate host.
 *  2. Empty string '' — relative URLs, works when FastAPI serves the UI directly
 *     (local dev with `python -m src.server`, Docker, systemd).
 *
 * HOW TO CONFIGURE FOR PRODUCTION (Vercel + separate backend):
 *  a) In Vercel Dashboard → Project → Settings → Environment Variables, add:
 *       TWINVOLT_API_BASE_URL  =  https://your-backend.railway.app
 *       TWINVOLT_WS_BASE_URL   =  wss://your-backend.railway.app
 *  b) Run `python scripts/build-config.py` in your CI/CD step to inject the
 *     URLs into src/ui/js/config.js before Vercel deploys the static files.
 *
 * LOCAL DEVELOPMENT: no configuration needed — relative '' URLs are automatic.
 */

/**
 * Resolves the REST API base URL from the runtime configuration object
 * injected by config.js, or defaults to relative '' for same-origin (local dev
 * or unified Vercel deployment). Supports both TWINVOLT_* and VITE_* variable styles.
 * @returns {string}
 */
function _resolveApiBaseUrl() {
  if (typeof window !== 'undefined') {
    const candidate = window.TWINVOLT_API_BASE_URL || window.VITE_API_BASE_URL;
    if (
      typeof candidate === 'string' &&
      candidate !== '' &&
      candidate !== '__TWINVOLT_API_BASE_URL__' &&
      candidate !== '__VITE_API_BASE_URL__'
    ) {
      return candidate.replace(/\/+$/, '');
    }
  }
  return '';
}

/**
 * Resolves the WebSocket base URL (wss:// or ws://) from the runtime config,
 * or derives it from window.location for the same-origin case.
 * Supports both TWINVOLT_* and VITE_* variable styles.
 * @returns {string}
 */
export function resolveWsBaseUrl() {
  if (typeof window !== 'undefined') {
    const candidate = window.TWINVOLT_WS_BASE_URL || window.VITE_WS_BASE_URL;
    if (
      typeof candidate === 'string' &&
      candidate !== '' &&
      candidate !== '__TWINVOLT_WS_BASE_URL__' &&
      candidate !== '__VITE_WS_BASE_URL__'
    ) {
      return candidate.replace(/\/+$/, '');
    }
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return proto + '//' + window.location.host;
  }
  return 'ws://localhost:8000';
}

class ApiClient {
  constructor(baseUrl = _resolveApiBaseUrl()) {
    this.baseUrl = baseUrl;
  }

  async _request(path, options = {}) {
    const url = `${this.baseUrl}${path}`;
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    const controller = new AbortController();
    const externalSignal = options.signal;
    const abortFromCaller = () => controller.abort(externalSignal?.reason);
    if (externalSignal?.aborted) abortFromCaller();
    else externalSignal?.addEventListener('abort', abortFromCaller, { once: true });
    const timeout = setTimeout(() => controller.abort(new Error('Request timed out after 30 seconds.')), 30_000);
    try {
      const res = await fetch(url, { ...options, headers, signal: controller.signal });
      if (!res.ok) {
        let errData = {};
        try {
          errData = await res.json();
        } catch (_) {
          errData = { message: res.statusText };
        }
        const error = new Error(errData.message || errData.detail || `HTTP Error ${res.status}`);
        error.status = res.status;
        error.errorType = errData.error_type || 'HttpError';
        error.details = errData.details || {};
        throw error;
      }
      if (res.status === 204) return null;
      try { return await res.json(); }
      catch (error) {
        const invalid = new Error('The server returned an invalid JSON response.');
        invalid.cause = error;
        throw invalid;
      }
    } catch (err) {
      const error = err.name === 'AbortError'
        ? new Error(externalSignal?.aborted ? 'Request was cancelled.' : 'Request timed out after 30 seconds.')
        : (err instanceof TypeError ? new Error('Cannot reach the TwinVolt API. Check the server connection and retry.') : err);
      console.warn(`[API] ${options.method || 'GET'} ${path} failed:`, error.message);
      throw error;
    } finally {
      clearTimeout(timeout);
      externalSignal?.removeEventListener('abort', abortFromCaller);
    }
  }

  // Health
  async getHealth() {
    return this._request('/health');
  }

  async getGatewayStatus() {
    return this._request('/api/v1/gateway/status');
  }

  // Battery Packs
  async getPacks() {
    return this._request('/api/v1/packs');
  }

  async getPack(packId) {
    return this._request(`/api/v1/packs/${encodeURIComponent(packId)}`);
  }

  async createPack(profilePayload) {
    return this._request('/api/v1/packs', {
      method: 'POST',
      body: JSON.stringify(profilePayload),
    });
  }

  async deletePack(packId) {
    return this._request(`/api/v1/packs/${encodeURIComponent(packId)}`, {
      method: 'DELETE',
    });
  }

  // Digital Twins
  async getTwins() {
    return this._request('/api/v1/twins');
  }

  async getTwin(systemId) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}`);
  }

  async createTwin(payload) {
    return this._request('/api/v1/twins', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async initializeTwin(systemId, initData = {}) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/initialize`, {
      method: 'POST',
      body: JSON.stringify(initData),
    });
  }

  async stepTwin(systemId, snapshotData) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/step`, {
      method: 'POST',
      body: JSON.stringify(snapshotData),
    });
  }

  async stepRawTwin(systemId, rawData, formatId = 'CSV') {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/step/raw`, {
      method: 'POST',
      body: JSON.stringify({ raw_data: rawData, format_identifier: formatId }),
    });
  }

  async getLatestState(systemId) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/state`);
  }

  async getStateHistory(systemId, limit = 100) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/state/history?limit=${limit}`);
  }

  async getTelemetryHistory(systemId, limit = 100, descending = false) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/telemetry/history?limit=${limit}&descending=${descending}`);
  }

  // Dataset Lab (temporary in-memory uploads; separate from live telemetry)
  async uploadDataset(file) {
    const path = `/api/v1/datasets?filename=${encodeURIComponent(file.name)}`;
    return this._request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
    });
  }

  async getDatasets() { return this._request('/api/v1/datasets'); }
  async getDataset(datasetId) { return this._request(`/api/v1/datasets/${encodeURIComponent(datasetId)}`); }
  async getDatasetPreview(datasetId, offset = 0, limit = 25) {
    return this._request(`/api/v1/datasets/${encodeURIComponent(datasetId)}/preview?offset=${offset}&limit=${limit}`);
  }
  async mapDataset(datasetId, mappings) {
    return this._request(`/api/v1/datasets/${encodeURIComponent(datasetId)}/mappings`, {
      method: 'PUT', body: JSON.stringify({ mappings }),
    });
  }
  async getDatasetSeries(datasetId, columns, limit = 1500) {
    const params = new URLSearchParams({ limit: String(limit) });
    columns.forEach((column) => params.append('columns', column));
    return this._request(`/api/v1/datasets/${encodeURIComponent(datasetId)}/series?${params}`);
  }
  async deleteDataset(datasetId) {
    return this._request(`/api/v1/datasets/${encodeURIComponent(datasetId)}`, { method: 'DELETE' });
  }

  async resetTwin(systemId) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/reset`, {
      method: 'POST',
    });
  }

  async deleteTwin(systemId) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}`, {
      method: 'DELETE',
    });
  }

  // Telemetry Ingest
  async ingestTelemetry(payload) {
    const fullPayload = {
      timestamp_ns: payload.timestamp_ns || (Date.now() * 1_000_000),
      ...payload,
    };
    return this._request('/api/v1/telemetry/ingest', {
      method: 'POST',
      body: JSON.stringify(fullPayload),
    });
  }

  // Diagnostics & Intelligence (Level 5.4)
  async getTwinDiagnostics(systemId) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/diagnostics`);
  }

  async getTwinDiagnosticHistory(systemId) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/diagnostics/history`);
  }

  async getTwinHypotheses(systemId) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/diagnostics/hypotheses`);
  }

  async resetTwinDiagnostics(systemId) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/diagnostics/reset`, {
      method: 'POST',
    });
  }

  // Health, Calibration & Validation (Level 5.1 - 5.3)
  async getTwinHealth(systemId) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/health`);
  }

  async getTwinCalibration(systemId) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/calibration`);
  }

  async getTwinValidation(systemId) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/validation`);
  }

  // Replay
  async replayProfile(systemId, payload) {
    return this._request(`/api/v1/replay/${encodeURIComponent(systemId)}/profile`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async replayCSV(systemId, payload) {
    return this._request(`/api/v1/replay/${encodeURIComponent(systemId)}/csv`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getLatestReplay(systemId) {
    return this._request(`/api/v1/replay/${encodeURIComponent(systemId)}/latest`);
  }

  // Benchmarking & Experimental Validation (Level 5.5)
  async getBenchmarkDatasets() {
    return this._request('/api/v1/benchmarks/datasets');
  }

  async getBenchmarkDataset(datasetId) {
    return this._request(`/api/v1/benchmarks/datasets/${encodeURIComponent(datasetId)}`);
  }

  async runBenchmark(systemId, payload) {
    return this._request(`/api/v1/benchmarks/${encodeURIComponent(systemId)}/run`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getLatestBenchmark(systemId) {
    return this._request(`/api/v1/benchmarks/${encodeURIComponent(systemId)}/latest`);
  }

  async getBenchmarkHistory(systemId, limit = 50) {
    return this._request(`/api/v1/benchmarks/${encodeURIComponent(systemId)}/history?limit=${limit}`);
  }

  async getBenchmarkResult(benchmarkId) {
    return this._request(`/api/v1/benchmarks/results/${encodeURIComponent(benchmarkId)}`);
  }

  async resetBenchmark(systemId) {
    return this._request(`/api/v1/benchmarks/${encodeURIComponent(systemId)}/reset`, {
      method: 'POST',
    });
  }

  // Physical Serial & Arduino Hardware
  async getSerialPorts() {
    return this._request('/api/v1/gateway/serial/ports');
  }

  async connectArduino(config) {
    return this._request('/api/v1/gateway/arduino/connect', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async disconnectArduino() {
    return this._request('/api/v1/gateway/arduino/disconnect', {
      method: 'POST',
    });
  }

  async getArduinoStatus() {
    return this._request('/api/v1/gateway/arduino/status');
  }

  async getArduinoRecords() {
    return this._request('/api/v1/gateway/arduino/records');
  }

  // Arduino Firmware Workspace
  async getFirmwareFiles() {
    return this._request('/api/v1/firmware/files');
  }

  async getFirmwareContent(filename) {
    const url = `${this.baseUrl}/api/v1/firmware/files/${encodeURIComponent(filename)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to read firmware file.`);
    return res.text();
  }

  async saveFirmware(filename, content) {
    return this._request('/api/v1/firmware/save', {
      method: 'POST',
      body: JSON.stringify({ filename, content }),
    });
  }

  async uploadFirmware(file) {
    const formData = new FormData();
    formData.append('file', file);
    const url = `${this.baseUrl}/api/v1/firmware/upload`;
    const res = await fetch(url, { method: 'POST', body: formData });
    if (!res.ok) {
      let errData = {};
      try { errData = await res.json(); } catch (_) {}
      throw new Error(errData.detail || `Upload failed with HTTP ${res.status}`);
    }
    return res.json();
  }

  async verifyFirmware(filename, boardFqbn = 'arduino:avr:uno') {
    return this._request('/api/v1/firmware/verify', {
      method: 'POST',
      body: JSON.stringify({ filename, board_fqbn: boardFqbn }),
    });
  }

  async flashFirmware(filename, port, boardFqbn = 'arduino:avr:uno') {
    return this._request('/api/v1/firmware/flash', {
      method: 'POST',
      body: JSON.stringify({ filename, port, board_fqbn: boardFqbn }),
    });
  }

  // Isolated Mock Telemetry Mode
  async getMockStatus() {
    return this._request('/api/v1/mock/status');
  }

  async startMock() {
    return this._request('/api/v1/mock/start', { method: 'POST' });
  }

  async stopMock() {
    return this._request('/api/v1/mock/stop', { method: 'POST' });
  }

  async configureMock(config) {
    return this._request('/api/v1/mock/configure', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async resetMock() {
    return this._request('/api/v1/mock/reset', { method: 'POST' });
  }

  async injectMockError(errorType = 'malformed_frame') {
    return this._request('/api/v1/mock/inject-error', {
      method: 'POST',
      body: JSON.stringify({ error_type: errorType }),
    });
  }

  async getMockRecords() {
    return this._request('/api/v1/mock/records');
  }
}

export const api = new ApiClient();
