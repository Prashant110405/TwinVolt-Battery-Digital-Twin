/**
 * Diagnostics & Decision Support View Component (Level 5.4 Phase 4)
 * Renders explainable fault lifecycle states, ranked hypotheses, supporting evidence, and actionable maintenance advice.
 */

import { api } from '../api.js';
import { store } from '../state.js';
import { escapeHTML } from '../html.js';

export class DiagnosticsView {
  constructor(container) {
    this.container = container;
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="grid-12">
        <!-- Diagnostic Status Overview Card -->
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <div>
                <span class="card-title">Battery Decision Support & Fault Lifecycle</span>
                <span class="card-subtitle">Explainable multi-hypothesis diagnostics with evidence grounding</span>
              </div>
              <div style="display: flex; gap: var(--space-2); align-items: center;">
                <span id="diag-lifecycle-badge" class="badge badge-green">NORMAL</span>
                <span id="diag-severity-badge" class="badge badge-gray">NORMAL</span>
                <span id="diag-context-badge" class="badge badge-purple">CONTEXT: REST</span>
                <button id="btn-reset-diag" class="btn btn-secondary btn-sm">Reset Diagnostics</button>
              </div>
            </div>
            <div class="grid-12" style="margin-top: var(--space-3);">
              <div class="col-4">
                <div class="metric-card">
                  <div class="metric-label">Leading Diagnostic Hypothesis</div>
                  <div id="diag-primary-hyp" class="metric-value" style="font-size: var(--text-base);">None (Normal Operation)</div>
                </div>
              </div>
              <div class="col-4">
                <div class="metric-card">
                  <div class="metric-label">Evidence Strength Tier</div>
                  <div id="diag-confidence" class="metric-value" style="font-size: var(--text-base);">NO_EVIDENCE</div>
                </div>
              </div>
              <div class="col-4">
                <div class="metric-card">
                  <div class="metric-label">Data Quality & Continuity</div>
                  <div id="diag-data-quality" class="metric-value" style="font-size: var(--text-base); color: var(--color-success);">VALID</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Explainable Diagnostic Narrative & Recommended Actions -->
        <div class="col-6">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Diagnostic Explanation & Engineering Narrative</span>
              <span class="badge badge-blue">Explainable AI</span>
            </div>
            <div id="diag-narrative" style="padding: var(--space-3); background: rgba(0, 0, 0, 0.2); border-radius: var(--radius-md); font-family: var(--font-sans); font-size: var(--text-sm); line-height: 1.6; color: var(--text-secondary); min-height: 120px;">
              Diagnostic engine running in steady-state; no anomalous evidence detected.
            </div>
            <div style="margin-top: var(--space-4);">
              <div class="metric-label" style="margin-bottom: var(--space-2);">Recommended Operator Actions</div>
              <ul id="diag-actions-list" style="padding-left: var(--space-4); margin: 0; color: var(--text-primary); font-size: var(--text-sm); line-height: 1.6;">
                <li>Maintain standard operational monitoring schedule.</li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Primary Hypothesis Deep Dive -->
        <div class="col-6">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Hypothesis Evidence & Confounds</span>
              <span id="diag-hyp-score" class="badge badge-purple">Score: 0.00</span>
            </div>
            <div class="data-table-container">
              <table class="data-table">
                <tbody>
                  <tr>
                    <td>Hypothesis Category</td>
                    <td id="diag-hyp-cat" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Signal Coverage</td>
                    <td id="diag-hyp-coverage" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Critical Advisory Eligible</td>
                    <td id="diag-hyp-critical" class="cell-mono">--</td>
                  </tr>
                  <tr>
                    <td>Untestable Confounds</td>
                    <td id="diag-hyp-confounds" style="font-size: var(--text-xs); color: var(--text-muted);">None</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Ranked Root-Cause Hypotheses Table -->
        <div class="col-12">
          <div class="card">
            <div class="card-header">
              <span class="card-title">Ranked Hypothesis Rule Catalog</span>
              <button id="btn-refresh-diag" class="btn btn-secondary btn-sm">Refresh</button>
            </div>
            <div class="data-table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Hypothesis ID</th>
                    <th>Category</th>
                    <th>Evidence Score</th>
                    <th>Strength Tier</th>
                    <th>Coverage</th>
                    <th>Critical Eligible</th>
                  </tr>
                </thead>
                <tbody id="diag-hypotheses-tbody">
                  <tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No active hypotheses evaluated yet.</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    `;

    this._bindEvents();
    this.refresh();
  }

  _bindEvents() {
    const btnReset = this.container.querySelector('#btn-reset-diag');
    if (btnReset) {
      btnReset.addEventListener('click', async () => {
        if (!store.activeTwinId) return;
        try {
          await api.resetTwinDiagnostics(store.activeTwinId);
          await this.refresh();
        } catch (err) {
          console.error('[DiagnosticsView] Reset failed:', err);
        }
      });
    }

    const btnRefresh = this.container.querySelector('#btn-refresh-diag');
    if (btnRefresh) {
      btnRefresh.addEventListener('click', () => this.refresh());
    }

    // Subscribe to real-time store updates
    store.subscribe((type, state, payload) => {
      if (type === 'TWIN_STATE_UPDATED' || type === 'TWIN_EVENT') {
        this.refresh();
      }
    });
  }

  async refresh() {
    const systemId = store.activeTwinId;
    if (!systemId) return;

    try {
      const diagData = await api.getTwinDiagnostics(systemId);
      this._renderDiagnostics(diagData);

      const hypList = await api.getTwinHypotheses(systemId);
      this._renderHypotheses(hypList);
    } catch (err) {
      // Unstepped or unconfigured twin
    }
  }

  _renderDiagnostics(diag) {
    if (!diag) return;

    // Badges
    const badgeLifecycle = this.container.querySelector('#diag-lifecycle-badge');
    if (badgeLifecycle) {
      const state = diag.lifecycle_state || 'NORMAL';
      badgeLifecycle.textContent = state;
      badgeLifecycle.className = 'badge';
      if (state === 'NORMAL') badgeLifecycle.classList.add('badge-green');
      else if (state === 'ANOMALY_DETECTED' || state === 'SUSPECTED') badgeLifecycle.classList.add('badge-amber');
      else if (state === 'DIAGNOSED') badgeLifecycle.classList.add('badge-red');
      else if (state === 'DIAGNOSED_CRITICAL') badgeLifecycle.classList.add('badge-red');
      else badgeLifecycle.classList.add('badge-gray');
    }

    const badgeSeverity = this.container.querySelector('#diag-severity-badge');
    if (badgeSeverity) {
      badgeSeverity.textContent = `SEVERITY: ${diag.severity || 'NORMAL'}`;
    }

    const badgeContext = this.container.querySelector('#diag-context-badge');
    if (badgeContext) {
      badgeContext.textContent = `CONTEXT: ${diag.operating_context || 'REST'}`;
    }

    // Narrative & Actions
    const elNarrative = this.container.querySelector('#diag-narrative');
    if (elNarrative && diag.explanation_narrative) {
      elNarrative.textContent = diag.explanation_narrative;
    }

    const elActions = this.container.querySelector('#diag-actions-list');
    if (elActions && diag.recommended_operator_actions) {
      elActions.innerHTML = diag.recommended_operator_actions
        .map((a) => `<li>${escapeHTML(a)}</li>`)
        .join('');
    }

    // Leading Hypothesis
    const elLead = this.container.querySelector('#diag-primary-hyp');
    const elConfidence = this.container.querySelector('#diag-confidence');
    const elDataQuality = this.container.querySelector('#diag-data-quality');

    if (diag.primary_hypothesis) {
      if (elLead) elLead.textContent = diag.primary_hypothesis.title || diag.primary_hypothesis.hypothesis_id;
      if (elConfidence) elConfidence.textContent = diag.primary_hypothesis.evidence_strength_tier || diag.primary_hypothesis.confidence_level;
      
      const scoreBadge = this.container.querySelector('#diag-hyp-score');
      if (scoreBadge) scoreBadge.textContent = Number.isFinite(diag.primary_hypothesis.evidence_score)
        ? `Score: ${diag.primary_hypothesis.evidence_score.toFixed(2)}` : 'Score: —';
      
      const elCat = this.container.querySelector('#diag-hyp-cat');
      if (elCat) elCat.textContent = diag.primary_hypothesis.category;

      const elCov = this.container.querySelector('#diag-hyp-coverage');
      if (elCov) elCov.textContent = Number.isFinite(diag.primary_hypothesis.required_signal_coverage)
        ? `${(diag.primary_hypothesis.required_signal_coverage * 100).toFixed(0)}%` : '—';

      const elCrit = this.container.querySelector('#diag-hyp-critical');
      if (elCrit) elCrit.textContent = diag.primary_hypothesis.is_critical_eligible ? 'YES' : 'NO';

      const elConfounds = this.container.querySelector('#diag-hyp-confounds');
      if (elConfounds && diag.primary_hypothesis.untestable_confounds) {
        elConfounds.innerHTML = diag.primary_hypothesis.untestable_confounds.map(escapeHTML).join('<br/>') || 'None';
      }
    } else {
      if (elLead) elLead.textContent = 'None (Nominal Operation)';
      if (elConfidence) elConfidence.textContent = 'NO_EVIDENCE';
    }

    if (elDataQuality) {
      const dq = diag.data_quality_status || 'VALID';
      elDataQuality.textContent = dq;
      elDataQuality.style.color = dq === 'VALID' ? 'var(--color-success)' : 'var(--color-danger)';
    }
  }

  _renderHypotheses(hypotheses) {
    const tbody = this.container.querySelector('#diag-hypotheses-tbody');
    if (!tbody || !hypotheses || hypotheses.length === 0) return;

    tbody.innerHTML = hypotheses
      .map((h) => {
        const score = Number.isFinite(h.evidence_score) ? h.evidence_score.toFixed(2) : '—';
        const cov = Number.isFinite(h.required_signal_coverage) ? `${(h.required_signal_coverage * 100).toFixed(0)}%` : '—';
        const crit = h.is_critical_eligible ? '<span style="color: var(--color-danger); font-weight: 600;">YES</span>' : 'NO';
        return `
          <tr>
            <td class="cell-mono" style="font-weight: 600;">${escapeHTML(h.hypothesis_id)}</td>
            <td><span class="badge badge-purple">${escapeHTML(h.category)}</span></td>
            <td class="cell-mono">${score}</td>
            <td><span class="badge badge-gray">${escapeHTML(h.evidence_strength_tier || h.confidence_level || 'NO_EVIDENCE')}</span></td>
            <td class="cell-mono">${cov}</td>
            <td class="cell-mono">${crit}</td>
          </tr>
        `;
      })
      .join('');
  }
}
