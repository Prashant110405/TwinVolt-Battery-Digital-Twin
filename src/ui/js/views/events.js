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

      if (tbody) {
        const rows = appState.events
          .filter((evt) => !evt.system_id || evt.system_id === appState.activeTwinId)
          .map((evt) => {
            const row = document.createElement('tr');
            const values = [evt.timestamp_ns, evt.event_type, evt.system_id || '—', evt.event_id || '—', evt.payload ? JSON.stringify(evt.payload) : '{}'];
            values.forEach((value, index) => {
              const cell = document.createElement('td');
              cell.className = 'cell-mono';
              if (index === 4) cell.classList.add('event-payload');
              if (index === 1) {
                const badgeEl = document.createElement('span');
                badgeEl.className = 'badge badge-purple';
                badgeEl.textContent = String(value ?? '—');
                cell.append(badgeEl);
              } else {
                cell.textContent = value === null || value === undefined ? '—' : String(value);
              }
              row.append(cell);
            });
            return row;
          });
        if (rows.length > 0) tbody.replaceChildren(...rows);
        else {
          const row = document.createElement('tr');
          const cell = document.createElement('td');
          cell.colSpan = 5;
          cell.className = 'unavailable-text';
          cell.textContent = 'No events are available for the selected twin.';
          row.append(cell);
          tbody.replaceChildren(row);
        }
      }
    }
  }

  destroy() {}
}
