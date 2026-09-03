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
            <span class="metric-label">Estimated Online SOC (EKF)</span>
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
              <span class="card-title">Observer Diagnostics & Advanced Estimation State</span>
              <span class="badge badge-purple">KALMAN FILTER</span>
            </div>
            <div class="grid-12">
              <div class="col-6">
                <div class="data-table-container">
                  <table class="data-table">
                    <tbody>
                      <tr>
                        <td>Active Estimator Type</td>
                        <td class="cell-mono">Extended Kalman Filter (EKF)</td>
                      </tr>
                      <tr>
                        <td>Current Health State (SOH)</td>
                        <td id="est-soh" class="cell-mono">100.0% (Nominal)</td>
                      </tr>
                      <tr>
                        <td>Observability Quality State</td>
                        <td><span class="badge badge-cyan">VALID</span></td>
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
            </div>
          </div>
        </div>
      </div>
    `;
  }

  update(changeType, appState) {
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
