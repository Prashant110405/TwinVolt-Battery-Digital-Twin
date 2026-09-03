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

    try {
      const res = await fetch(url, { ...options, headers });
      if (!res.ok) {
        let errData = {};
        try {
          errData = await res.json();
        } catch (_) {
          errData = { message: res.statusText };
        }
        const error = new Error(errData.message || `HTTP Error ${res.status}`);
        error.status = res.status;
        error.errorType = errData.error_type || 'HttpError';
        error.details = errData.details || {};
        throw error;
      }
      return await res.json();
    } catch (err) {
      console.warn(`[API] ${options.method || 'GET'} ${path} failed:`, err.message);
      throw err;
    }
  }

  // Health
  async getHealth() {
    return this._request('/health');
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

  async getTelemetryHistory(systemId, limit = 100) {
    return this._request(`/api/v1/twins/${encodeURIComponent(systemId)}/telemetry/history?limit=${limit}`);
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
}

export const api = new ApiClient();
