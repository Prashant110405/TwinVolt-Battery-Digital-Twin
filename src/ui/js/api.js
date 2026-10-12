/**
 * Thin HTTP REST Client for TwinVolt API
 * Communicates strictly through verified Subtask 4.2 endpoints.
 */

class ApiClient {
  constructor(baseUrl = '') {
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
    const params = new URLSearchParams({ columns: columns.join(','), limit: String(limit) });
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
    return this._request('/api/v1/telemetry/ingest', {
      method: 'POST',
      body: JSON.stringify(payload),
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
}

export const api = new ApiClient();


