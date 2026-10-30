/**
 * TwinVolt Main Application Bootstrapper & Router
 * Coordinates view lifecycles, navigation tabs, twin selection, and state subscription.
 */

import { api } from './api.js';
import { store } from './state.js';
import { BenchmarkingView } from './views/benchmarking.js';
import { DiagnosticsView } from './views/diagnostics.js';
import { DatasetLabView } from './views/dataset_lab.js';
import { EstimationView } from './views/estimation.js';
import { EventsView } from './views/events.js';
import { HardwareView } from './views/hardware.js';
import { MockView } from './views/mock.js';
import { OverviewView } from './views/overview.js';
import { ReplayView } from './views/replay.js';
import { TelemetryView } from './views/telemetry.js';
import { TwinView } from './views/twin.js';
import { wsClient } from './websocket.js';
import { bleManager } from './ble.js';

class TwinVoltApp {
  constructor() {
    this.views = {};
    this.currentView = 'overview';
  }

  async init() {
    console.log('[TwinVolt] Initializing UI Application Layer...');

    // 1. Mount Views
    this._mountViews();

    // 2. Setup Navigation
    this._setupNavigation();

    // 3. Setup Global State Subscription
    store.subscribe((changeType, appState, payload) => {
      this._handleStateChange(changeType, appState, payload);
    });

    // 4. Initial REST Sync
    await this._syncInitialData();

    // 5. Connect WebSocket if a twin is active
    if (store.activeTwinId) {
      wsClient.connect(store.activeTwinId);
    }
  }

  _mountViews() {
    const viewContainers = {
      overview: document.getElementById('view-overview'),
      telemetry: document.getElementById('view-telemetry'),
      hardware: document.getElementById('view-hardware'),
      mock: document.getElementById('view-mock'),
      twin: document.getElementById('view-twin'),
      estimation: document.getElementById('view-estimation'),
      replay: document.getElementById('view-replay'),
      events: document.getElementById('view-events'),
      diagnostics: document.getElementById('view-diagnostics'),
      benchmarking: document.getElementById('view-benchmarking'),
      datasets: document.getElementById('view-datasets'),
    };

    if (viewContainers.overview) this.views.overview = new OverviewView(viewContainers.overview);
    if (viewContainers.telemetry) this.views.telemetry = new TelemetryView(viewContainers.telemetry);
    if (viewContainers.hardware) this.views.hardware = new HardwareView(viewContainers.hardware);
    if (viewContainers.mock) this.views.mock = new MockView(viewContainers.mock);
    if (viewContainers.twin) this.views.twin = new TwinView(viewContainers.twin);
    if (viewContainers.estimation) this.views.estimation = new EstimationView(viewContainers.estimation);
    if (viewContainers.replay) this.views.replay = new ReplayView(viewContainers.replay);
    if (viewContainers.events) this.views.events = new EventsView(viewContainers.events);
    if (viewContainers.diagnostics) this.views.diagnostics = new DiagnosticsView(viewContainers.diagnostics);
    if (viewContainers.benchmarking) this.views.benchmarking = new BenchmarkingView(viewContainers.benchmarking);
    if (viewContainers.datasets) this.views.datasets = new DatasetLabView(viewContainers.datasets);
  }

  _setupNavigation() {
    const navButtons = document.querySelectorAll('.nav-item-btn');
    navButtons.forEach((btn) => {
      btn.setAttribute('aria-current', btn.classList.contains('active') ? 'page' : 'false');
      btn.addEventListener('click', () => {
        const targetView = btn.getAttribute('data-view');
        if (targetView && this.views[targetView]) {
          this.switchView(targetView);
        }
      });
    });

    const twinSelect = document.getElementById('header-twin-select');
    if (twinSelect) {
      twinSelect.addEventListener('change', async (e) => {
        const selectedId = e.target.value;
        if (selectedId) {
          await this._selectTwin(selectedId);
        }
      });
    }
  }

  switchView(viewName) {
    if (!this.views[viewName]) return;

    if (this.currentView && this.views[this.currentView] && typeof this.views[this.currentView].unmount === 'function') {
      this.views[this.currentView].unmount();
    }

    // Update Nav Buttons
    document.querySelectorAll('.nav-item-btn').forEach((btn) => {
      if (btn.getAttribute('data-view') === viewName) {
        btn.classList.add('active');
        btn.setAttribute('aria-current', 'page');
      } else {
        btn.classList.remove('active');
        btn.setAttribute('aria-current', 'false');
      }
    });

    // Update View Containers
    document.querySelectorAll('.view-container').forEach((c) => {
      c.classList.remove('active');
    });

    const activeContainer = document.getElementById(`view-view-${viewName}`) || document.getElementById(`view-${viewName}`);
    if (activeContainer) {
      activeContainer.classList.add('active');
    }

    this.currentView = viewName;
    if (this.views[viewName] && typeof this.views[viewName].mount === 'function') {
      this.views[viewName].mount();
    }
  }

  async _syncInitialData() {
    try {
      // 1. Fetch Health
      const health = await api.getHealth();
      store.apiHealth = health;
      const version = document.getElementById('header-version');
      if (version && health.version) version.textContent = `API v${health.version}`;

      // 2. Fetch Packs
      const packsRes = await api.getPacks();
      store.setPacksList(packsRes.packs || []);

      // 3. Fetch Twins
      const twinsRes = await api.getTwins();
      store.setTwinsList(twinsRes.twins || []);

      // 4. Set Default Twin
      if (twinsRes.twins && twinsRes.twins.length > 0) {
        await this._selectTwin(twinsRes.twins[0]);
      }
    } catch (err) {
      console.warn('[TwinVolt] Initial REST sync notice:', err.message);
      store.setTwinLoadError(err.message);
    }
  }

  async _selectTwin(systemId) {
    store.setTwinLoadError(null);
    // Clear the old twin before waiting for REST so its cached readings cannot
    // be shown under the newly selected identifier.
    wsClient.disconnect();
    store.setActiveTwin(systemId, null);
    try {
      const twinStatus = await api.getTwin(systemId);
      store.setActiveTwin(systemId, twinStatus);

      // Find and set associated pack
      if (twinStatus.pack_id) {
        try {
          const pack = await api.getPack(twinStatus.pack_id);
          store.setActivePack(pack);
        } catch (_) {}
      }

      // Reconnect WebSocket to new twin
      wsClient.connect(systemId);
    } catch (err) {
      console.error(`[TwinVolt] Failed to load twin status for ${systemId}:`, err);
      store.setTwinLoadError(err.message);
    }
  }

  _handleStateChange(changeType, appState, payload) {
    // 0. Update Mode Badge
    const modeBadge = document.getElementById('header-mode-badge');
    const modeText = document.getElementById('header-mode-text');
    if (modeBadge && modeText) {
      const mode = (appState.activeMode || 'LIVE').toUpperCase();
      const transportLabel = appState.activeTransport === 'BLE' ? ' [BLE]' : '';
      modeText.textContent = `${mode} MODE${transportLabel}`;
      modeBadge.className = `mode-pill mode-${mode.toLowerCase()}`;
    }

    // 1. Update Header Elements
    const statusPill = document.getElementById('header-ws-status');
    const latencyEl = document.getElementById('header-latency');
    if (statusPill) {
      statusPill.replaceChildren();
      const dot = document.createElement('span');
      dot.className = 'indicator-dot';
      dot.setAttribute('aria-hidden', 'true');
      statusPill.append(dot, document.createTextNode(appState.wsStatus.replace('_', ' ')));
      statusPill.className = `status-pill ${appState.wsStatus.toLowerCase()}`;
      statusPill.setAttribute('role', 'status');
      statusPill.setAttribute('aria-label', `Twin stream ${appState.wsStatus.toLowerCase().replace('_', ' ')}`);
    }
    if (latencyEl) {
      if (appState.clientLatencyMs !== null && appState.wsStatus === 'CONNECTED') {
        latencyEl.textContent = `${appState.clientLatencyMs} ms`;
        document.getElementById('latency-readout')?.removeAttribute('hidden');
      } else {
        latencyEl.textContent = '—';
        document.getElementById('latency-readout')?.setAttribute('hidden', '');
      }
    }

    // 2. Update Twin Dropdown
    const twinSelect = document.getElementById('header-twin-select');
    if (twinSelect && changeType === 'TWINS_LIST') {
      twinSelect.replaceChildren();
      if (appState.allTwins.length > 0) {
        appState.allTwins.forEach((twin) => {
          const id = typeof twin === 'string' ? twin : twin.system_id;
          if (!id) return;
          const option = document.createElement('option');
          option.value = id;
          option.textContent = id;
          option.selected = id === appState.activeTwinId;
          twinSelect.append(option);
        });
      } else {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No active twins';
        twinSelect.append(option);
      }
    }

    // 3. Update Active Views
    for (const view of Object.values(this.views)) {
      if (view && typeof view.update === 'function') {
        view.update(changeType, appState, payload);
      }
    }
  }
}

// Bootstrap on DOM Loaded
window.addEventListener('DOMContentLoaded', () => {
  window.twinVoltApp = new TwinVoltApp();
  window.twinVoltApp.init();
});
