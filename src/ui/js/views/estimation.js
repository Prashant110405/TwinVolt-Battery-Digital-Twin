/**
 * Estimation View Component
 * Compares simulated SOC with online state estimators (EKF / Coulomb Counting).
 */

import { store } from '../state.js';

export class EstimationView {
  constructor(container) {
    this.container = container;
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="grid-12">
        <div class="col-4">
          <div class="card metric-widget">
            <span class="metric-label">Simulated Model SOC</span>
            <div class="metric-value-row">
              <span id="est-sim-soc" class="metric-value">--</span>
              <span class="metric-unit">%</span>
            </div>
            <div class="card-subtitle">From physical model state transition</div>
          </div>
        </div>

        <div class="col-4">
          <div class="card metric-widget">
            <span class="metric-label">Estimated Online SOC</span>
            <div class="metric-value-row">
              <span id="est-online-soc" class="metric-value">--</span>
              <span class="metric-unit">%</span>
            </div>
            <div class="card-subtitle">From Extended Kalman Filter observer</div>
          </div>
        </div>

        <div class="col-4">
          <div class="card metric-widget">
            <span class="metric-label">State of Charge Discrepancy</span>
            <div class="metric-value-row">
              <span id="est-soc-discrepancy" class="metric-value">--</span>
              <span class="metric-unit">%</span>
            </div>
            <div class="card-subtitle">Δz = Simulated SOC − Estimated SOC</div>
          </div>
        </div>

        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Estimation Outputs & Availability</span>
              <span class="badge badge-gray">Backend-reported</span>
            </div>
            <div class="grid-12">
              <div class="col-6">
                <div class="data-table-container">
                  <table class="data-table">
                    <tbody>
                      <tr>
                        <td>Active Estimator Type</td>
                        <td class="cell-mono">Not exposed by current API</td>
                      </tr>
                      <tr>
                        <td>State of Health (SOH)</td>
                        <td class="cell-mono">Not yet available from current API</td>
                      </tr>
                      <tr>
                        <td>Observability Quality State</td>
                        <td class="cell-mono">Not exposed by current API</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <div class="col-6">
                <div class="metric-widget">
                  <span class="metric-label">EKF Innovation Covariance Matrix (P)</span>
                  <p class="unavailable-text" style="margin-top: var(--space-2);">
                    Not exposed by current API contract
                  </p>
                </div>
              </div>
              <div class="col-12">
                <p class="unavailable-text">RUL by criterion, uncertainty bounds, and prognostic validation are not exposed by the current API. No projection or confidence value is inferred in the UI.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  update(changeType, appState) {
    if (changeType === 'TWIN_CHANGED' && !appState.latestState) {
      for (const id of ['est-sim-soc', 'est-online-soc', 'est-soc-discrepancy']) {
        const el = document.getElementById(id);
        if (el) el.textContent = '—';
      }
    }
    if (changeType === 'STATE_UPDATED' && appState.latestState) {
      const s = appState.latestState;
      const elSim = document.getElementById('est-sim-soc');
      const elEst = document.getElementById('est-online-soc');
      const elDelta = document.getElementById('est-soc-discrepancy');

      const simPct = s.simulated_soc !== undefined ? s.simulated_soc * 100 : null;
      const estPct = s.estimated_soc !== undefined && s.estimated_soc !== null ? s.estimated_soc * 100 : null;

      if (elSim && simPct !== null) elSim.textContent = simPct.toFixed(2);
      if (elEst) elEst.textContent = estPct !== null ? estPct.toFixed(2) : '--';

      if (elDelta) {
        if (simPct !== null && estPct !== null) {
          const delta = Math.abs(simPct - estPct);
          elDelta.textContent = delta.toFixed(3);
        } else {
          elDelta.textContent = '--';
        }
      }
    }
  }

  destroy() {}
}
