/**
 * Domain Events View Component
 * Real-time event log streaming runtime observations and domain lifecycle events.
 */

import { store } from '../state.js';

export class EventsView {
  constructor(container) {
    this.container = container;
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="grid-12">
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Real-Time Domain Event Log</span>
              <span id="event-count-badge" class="badge badge-cyan">0 Events</span>
            </div>
            <p class="card-subtitle" style="margin-bottom: var(--space-3);">
              Live events published on the in-process DigitalTwinEventBus and streamed over WebSocket.
            </p>
            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Timestamp (Epoch ns)</th>
                    <th>Event Type</th>
                    <th>Source ID</th>
                    <th>Event Identifier</th>
                    <th>Payload Details</th>
                  </tr>
                </thead>
                <tbody id="events-tbody">
                  <tr>
                    <td colspan="5" class="unavailable-text" style="text-align: center; padding: var(--space-4);">
                      No events captured yet. Streaming live...
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  update(changeType, appState) {
    if (changeType === 'EVENT_RECEIVED' || changeType === 'TWIN_CHANGED') {
      const tbody = document.getElementById('events-tbody');
      const badge = document.getElementById('event-count-badge');

      if (badge) {
        badge.textContent = `${appState.events.length} Events`;
      }

      if (tbody && appState.events.length > 0) {
        let html = '';
        for (const evt of appState.events) {
          const payloadStr = evt.payload ? JSON.stringify(evt.payload) : '{}';
          html += `
            <tr>
              <td class="cell-mono">${evt.timestamp_ns || Date.now() * 1000000}</td>
              <td><span class="badge badge-purple">${evt.event_type}</span></td>
              <td class="cell-mono">${evt.system_id || '--'}</td>
              <td class="cell-mono">${evt.event_id || '--'}</td>
              <td class="cell-mono" style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                ${payloadStr}
              </td>
            </tr>
          `;
        }
        tbody.innerHTML = html;
      }
    }
  }

  destroy() {}
}
