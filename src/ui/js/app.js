/**
 * TwinVolt Main Application Bootstrapper & Router
 * Coordinates view lifecycles, navigation tabs, twin selection, and state subscription.
 */

import { api } from './api.js';
import { store } from './state.js';
import { EstimationView } from './views/estimation.js';
import { EventsView } from './views/events.js';
import { OverviewView } from './views/overview.js';
import { ReplayView } from './views/replay.js';
import { TelemetryView } from './views/telemetry.js';
import { TwinView } from './views/twin.js';
import { wsClient } from './websocket.js';

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
      twin: document.getElementById('view-twin'),
      estimation: document.getElementById('view-estimation'),
      replay: document.getElementById('view-replay'),
      events: document.getElementById('view-events'),
    };

    if (viewContainers.overview) this.views.overview = new OverviewView(viewContainers.overview);
    if (viewContainers.telemetry) this.views.telemetry = new TelemetryView(viewContainers.telemetry);
    if (viewContainers.twin) this.views.twin = new TwinView(viewContainers.twin);
    if (viewContainers.estimation) this.views.estimation = new EstimationView(viewContainers.estimation);
    if (viewContainers.replay) this.views.replay = new ReplayView(viewContainers.replay);
    if (viewContainers.events) this.views.events = new EventsView(viewContainers.events);
  }

  _setupNavigation() {
    const navButtons = document.querySelectorAll('.nav-item-btn');
    navButtons.forEach((btn) => {
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

    // Update Nav Buttons
    document.querySelectorAll('.nav-item-btn').forEach((btn) => {
      if (btn.getAttribute('data-view') === viewName) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
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
  }

  async _syncInitialData() {
    try {
      // 1. Fetch Health
      const health = await api.getHealth();
      store.apiHealth = health;

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
    }
  }

  async _selectTwin(systemId) {
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
    }
  }

  _handleStateChange(changeType, appState, payload) {
    // 1. Update Header Elements
    const statusPill = document.getElementById('header-ws-status');
    const latencyEl = document.getElementById('header-latency');
    if (statusPill) {
      statusPill.textContent = appState.wsStatus;
      statusPill.className = `status-pill ${appState.wsStatus.toLowerCase()}`;
    }
    if (latencyEl) {
      if (appState.clientLatencyMs !== null && appState.wsStatus === 'CONNECTED') {
        latencyEl.textContent = `${appState.clientLatencyMs} ms`;
      } else {
        latencyEl.textContent = '-- ms';
      }
    }

    // 2. Update Twin Dropdown
    const twinSelect = document.getElementById('header-twin-select');
    if (twinSelect && changeType === 'TWINS_LIST') {
      twinSelect.innerHTML = appState.allTwins.length > 0
        ? appState.allTwins.map((id) => `<option value="${id}" ${id === appState.activeTwinId ? 'selected' : ''}>${id}</option>`).join('')
        : '<option value="">No Active Twins</option>';
    }

    // 3. Update Active Views
    for (const view of Object.values(this.views)) {
      if (view && typeof view.update === 'function') {
        view.update(changeType, appState);
      }
    }
  }
}

// Bootstrap on DOM Loaded
window.addEventListener('DOMContentLoaded', () => {
  window.twinVoltApp = new TwinVoltApp();
  window.twinVoltApp.init();
});
