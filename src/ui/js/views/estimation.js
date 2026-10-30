/**
 * Estimation View Component
 * Compares simulated SOC with online state estimators (EKF / Coulomb Counting).
 */

import { api } from '../api.js';
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

        <div class="col-4">
          <div class="card metric-widget">
            <span class="metric-label">Hardware Coulomb SOC</span>
            <div class="metric-value-row">
              <span id="est-hw-soc" class="metric-value">--</span>
              <span class="metric-unit">%</span>
            </div>
            <div class="card-subtitle">Real-time coulomb counting from pipeline</div>
          </div>
        </div>

        <div class="col-4">
          <div class="card metric-widget">
            <span class="metric-label">Battery SOH</span>
            <div class="metric-value-row">
              <span id="est-soh" class="metric-value">--</span>
              <span class="metric-unit">%</span>
            </div>
            <div class="card-subtitle">State of Health from degradation model</div>
          </div>
        </div>

        <div class="col-4">
          <div class="card metric-widget">
            <span class="metric-label">Co-Simulation Steps</span>
            <div class="metric-value-row">
              <span id="est-step-count" class="metric-value">0</span>
              <span class="metric-unit">cycles</span>
            </div>
            <div class="card-subtitle">Total twin step executions</div>
          </div>
        </div>

        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Estimation Outputs & Availability</span>
              <span id="est-source-badge" class="badge badge-gray">Awaiting data</span>
            </div>
            <div class="grid-12">
              <div class="col-6">
                <div class="data-table-container">
                  <table class="data-table">
                    <tbody>
                      <tr>
                        <td>Active Estimator Type</td>
                        <td id="est-estimator-type" class="cell-mono">Awaiting twin initialization</td>
                      </tr>
                      <tr>
                        <td>State of Health (SOH)</td>
                        <td id="est-soh-detail" class="cell-mono">Awaiting calibration data</td>
                      </tr>
                      <tr>
                        <td>Observability Quality State</td>
                        <td id="est-obs-quality" class="cell-mono">Awaiting sufficient excitation</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <div class="col-6">
                <div class="metric-widget">
                  <span class="metric-label">EKF Innovation Covariance Matrix (P)</span>
                  <p id="est-ekf-cov" class="unavailable-text" style="margin-top: var(--space-2);">
                    Awaiting EKF estimator step data
                  </p>
                </div>
              </div>
              <div class="col-12">
                <p class="unavailable-text">RUL by criterion, uncertainty bounds, and prognostic validation require extended operational history. Values will populate as the digital twin accumulates co-simulation cycles.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  mount() {
    this._fetchEstimatorInfo();
  }

  unmount() {}

  async _fetchEstimatorInfo() {
    const systemId = store.activeTwinId;
    if (!systemId) return;

    try {
      const [twinStatus, healthData] = await Promise.allSettled([
        api.getTwin(systemId),
        api.getTwinHealth(systemId),
      ]);

      const twin = twinStatus.status === 'fulfilled' ? twinStatus.value : null;
      const health = healthData.status === 'fulfilled' ? healthData.value : null;

      // Estimator type from model name
      const elEstType = document.getElementById('est-estimator-type');
      if (elEstType && twin) {
        const modelName = twin.model_name || 'ECM Model';
        const hasEKF = modelName.toLowerCase().includes('ekf') || twin.total_steps > 0;
        elEstType.textContent = hasEKF ? `EKF + Coulomb Counter (${modelName})` : `Coulomb Counter (${modelName})`;
      }

      // SOH detail
      const elSohDetail = document.getElementById('est-soh-detail');
      if (elSohDetail && health) {
        const sohPct = Number.isFinite(health.soh_unified_fraction) ? (health.soh_unified_fraction * 100).toFixed(1) + '%' : null;
        const calStatus = health.calibration_status || 'UNCALIBRATED';
        elSohDetail.textContent = sohPct ? `${sohPct} (${calStatus})` : calStatus;
      }

      // Source badge
      const elBadge = document.getElementById('est-source-badge');
      if (elBadge && twin) {
        if (twin.total_steps > 0) {
          elBadge.textContent = `${twin.total_steps} steps completed`;
          elBadge.className = 'badge badge-green';
        } else {
          elBadge.textContent = 'Twin initialized — awaiting telemetry';
          elBadge.className = 'badge badge-amber';
        }
      }
    } catch (_) {
      // Twin not available yet
    }
  }

  update(changeType, appState) {
    if (changeType === 'TWIN_CHANGED') {
      for (const id of ['est-sim-soc', 'est-online-soc', 'est-soc-discrepancy', 'est-hw-soc', 'est-soh']) {
        const el = document.getElementById(id);
        if (el) el.textContent = '—';
      }
      if (appState.activeTwinId) {
        this._fetchEstimatorInfo();
      }
    }

    if (changeType === 'STATE_UPDATED' && appState.latestState) {
      const s = appState.latestState;
      const elSim = document.getElementById('est-sim-soc');
      const elEst = document.getElementById('est-online-soc');
      const elDelta = document.getElementById('est-soc-discrepancy');
      const elSteps = document.getElementById('est-step-count');

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

      if (elSteps && Number.isFinite(s.step_index)) {
        elSteps.textContent = s.step_index;
      }

      // SOH from diagnostics
      const elSoh = document.getElementById('est-soh');
      if (elSoh && s.diagnostics && Number.isFinite(s.diagnostics.soh_unified_fraction)) {
        elSoh.textContent = (s.diagnostics.soh_unified_fraction * 100).toFixed(1);
      }

      // Observability quality
      const elObs = document.getElementById('est-obs-quality');
      if (elObs && Number.isFinite(s.step_index)) {
        if (s.step_index > 50) {
          elObs.textContent = 'SUFFICIENT — Estimator converged';
        } else if (s.step_index > 10) {
          elObs.textContent = `CONVERGING — ${s.step_index} steps`;
        } else {
          elObs.textContent = `WARMING UP — ${s.step_index} steps`;
        }
      }
    }

    // Live hardware SoC from pipeline coulomb counting
    if (changeType === 'HARDWARE_TELEMETRY' && appState.latestHardwareReading) {
      const hw = appState.latestHardwareReading;
      const elHwSoc = document.getElementById('est-hw-soc');
      if (elHwSoc && Number.isFinite(hw.soc_percent)) {
        elHwSoc.textContent = hw.soc_percent.toFixed(1);
      }
    }
  }

  destroy() {}
}

