/** Temporary historical dataset workspace. Import here never writes live telemetry. */
import { api } from '../api.js';
import { escapeHTML } from '../html.js';

const MAPPING_ROLES = [
  ['timestamp', 'Timestamp', ['ISO timestamp', 'ns', 'ms', 's']],
  ['voltage', 'Pack voltage', ['V', 'mV']],
  ['current', 'Pack current', ['A', 'mA']],
  ['temperature', 'Temperature', ['°C', '°F']],
  ['soc', 'SOC', ['%', 'fraction']],
  ['soh', 'SOH', ['%', 'fraction']],
  ['cell_voltage', 'Explicit cell voltage channel', ['V', 'mV']],
];

export class DatasetLabView {
  constructor(container) {
    this.container = container;
    this.datasets = [];
    this.active = null;
    this.previewOffset = 0;
    this.requestId = 0;
    this.seriesObserver = null;
    this.uploading = false;
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <section aria-labelledby="dataset-title">
        <div class="dataset-page-heading">
          <div><p class="eyebrow">HISTORICAL DATA WORKSPACE</p><h1 id="dataset-title">Dataset Lab</h1>
            <p class="card-subtitle">Profile and explore uploaded files in an isolated temporary session. Uploads do not become live telemetry.</p></div>
          <span class="badge badge-blue">CSV · JSON</span>
        </div>
        <div class="card dataset-upload-card">
          <div id="dataset-dropzone" class="dataset-dropzone" tabindex="0" role="button" aria-label="Choose a CSV or JSON dataset file">
            <input id="dataset-file" type="file" accept=".csv,.json,text/csv,application/json" hidden />
            <div class="dataset-upload-icon" aria-hidden="true">↑</div>
            <strong>Drop a dataset file here or browse</strong>
            <span>CSV and JSON are enabled. Maximum upload size is configured by the server.</span>
            <span class="dataset-format-note">Files are parsed in memory and expire after one hour. XLSX/XLS and Parquet parsers are not installed in this environment. For Kaggle, upload an already downloaded CSV or JSON file.</span>
          </div>
          <div id="dataset-upload-status" class="action-message" role="status" aria-live="polite"></div>
        </div>
        <div class="grid-12 dataset-workspace">
          <div class="col-4 card">
            <div class="card-header"><span class="card-title">Temporary datasets</span><button id="dataset-refresh" class="btn btn-secondary btn-sm">Refresh</button></div>
            <div id="dataset-list" class="dataset-list" aria-live="polite">Loading datasets…</div>
          </div>
          <div class="col-8">
            <div id="dataset-detail" class="card dataset-empty">Select a dataset or upload a CSV/JSON file to begin.</div>
          </div>
        </div>
        <div class="card dataset-replay-note"><strong>Replay stays separate</strong><p>The current CSV replay API runs against the selected Twin instance and defaults to resetting it. Dataset replay is not enabled here until an isolated replay sandbox is available.</p></div>
      </section>`;
    this._bind();
    this.loadDatasets();
  }

  _bind() {
    const input = this.container.querySelector('#dataset-file');
    const zone = this.container.querySelector('#dataset-dropzone');
    zone.addEventListener('click', () => input.click());
    zone.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); input.click(); }
    });
    input.addEventListener('change', () => { if (input.files[0]) this.upload(input.files[0]); input.value = ''; });
    zone.addEventListener('dragover', (event) => { event.preventDefault(); zone.classList.add('drag-active'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-active'));
    zone.addEventListener('drop', (event) => {
      event.preventDefault(); zone.classList.remove('drag-active');
      if (event.dataTransfer.files[0]) this.upload(event.dataTransfer.files[0]);
    });
    this.container.querySelector('#dataset-refresh').addEventListener('click', () => this.loadDatasets());
  }

  async upload(file) {
    if (this.uploading) return;
    const status = this.container.querySelector('#dataset-upload-status');
    if (!/\.(csv|json)$/i.test(file.name)) {
      status.className = 'action-message error'; status.textContent = 'This installation accepts CSV and JSON files only.'; return;
    }
    status.className = 'action-message'; status.textContent = `Uploading and profiling ${file.name}…`;
    this.uploading = true;
    this.container.querySelector('#dataset-file').disabled = true;
    try {
      this.active = await api.uploadDataset(file);
      status.textContent = `${file.name} parsed successfully. Source rows are retained unchanged for this temporary session.`;
      await this.loadDatasets();
      await this.renderDetail();
    } catch (error) {
      status.className = 'action-message error'; status.textContent = `Dataset upload failed: ${error.message}`;
    } finally {
      this.uploading = false;
      this.container.querySelector('#dataset-file').disabled = false;
    }
  }

  async loadDatasets() {
    const list = this.container.querySelector('#dataset-list');
    try {
      this.datasets = await api.getDatasets();
      list.replaceChildren();
      if (!this.datasets.length) { list.textContent = 'No temporary datasets. Upload CSV or JSON to start.'; return; }
      this.datasets.forEach((dataset) => {
        const button = document.createElement('button');
        button.type = 'button'; button.className = `dataset-list-item${this.active?.dataset_id === dataset.dataset_id ? ' selected' : ''}`;
        const name = document.createElement('strong'); name.textContent = dataset.filename;
        const info = document.createElement('span'); info.textContent = `${dataset.row_count.toLocaleString()} rows · ${dataset.column_count} columns`;
        button.append(name, info);
        button.addEventListener('click', async () => {
          this.active = dataset; this.previewOffset = 0;
          await this.renderDetail(); await this.loadDatasets();
        });
        list.append(button);
      });
    } catch (error) {
      list.textContent = `Dataset service unavailable: ${error.message}`;
    }
  }

  async renderDetail() {
    this.seriesObserver?.disconnect();
    if (!this.active) return;
    const detail = this.container.querySelector('#dataset-detail');
    detail.innerHTML = '<p role="status">Loading dataset profile and preview…</p>';
    const currentId = this.active.dataset_id;
    try {
      const [dataset, preview] = await Promise.all([
        api.getDataset(currentId), api.getDatasetPreview(currentId, this.previewOffset, 25),
      ]);
      if (this.active?.dataset_id !== currentId) return;
      this.active = dataset;
      detail.innerHTML = this._detailHTML(dataset, preview);
      this._bindDetail(dataset, preview);
    } catch (error) {
      if (this.active?.dataset_id === currentId) detail.textContent = `Dataset detail unavailable: ${error.message}`;
    }
  }

  _detailHTML(dataset, preview) {
    const profile = dataset.profile;
    const columns = profile.columns;
    const mapping = profile.mappings || {};
    const options = (selected) => `<option value="">Not mapped</option>${preview.columns.map((name) => `<option value="${escapeHTML(name)}" ${selected === name ? 'selected' : ''}>${escapeHTML(name)}</option>`).join('')}`;
    const roleRows = MAPPING_ROLES.map(([role, label, units]) => {
      const current = mapping[role] || {};
      const unitChoices = role === 'timestamp'
        ? `<option value="" ${!current.unit ? 'selected' : ''}>ISO timestamp / select numeric unit</option>${units.slice(1).map((u) => `<option value="${u}" ${current.unit === u ? 'selected' : ''}>${u}</option>`).join('')}`
        : `<option value="">Choose unit…</option>${units.map((u) => `<option value="${u}" ${current.unit === u ? 'selected' : ''}>${u}</option>`).join('')}`;
      const candidate = columns.find((col) => col.name === current.column)?.name || columns.find((col) => col.candidate_mapping === role)?.name || '';
      return `<div class="dataset-mapping-row"><label for="map-${role}">${label}</label><select id="map-${role}" class="form-select" data-map-role="${role}">${options(current.column || candidate)}</select><select id="unit-${role}" class="form-select" data-unit-role="${role}" aria-label="${label} unit">${unitChoices}</select></div>`;
    }).join('');
    const customRows = Object.entries(mapping).filter(([key]) => key.startsWith('series:')).map(([key, value], index) =>
      `<div class="dataset-mapping-row dataset-custom-mapping"><label>Custom series ${index + 1}<input class="form-input" data-series-name value="${escapeHTML(key.slice(7))}" maxlength="90" aria-label="Custom series name" /></label><select class="form-select" data-series-column aria-label="Custom series column">${options(value.column)}</select><input class="form-input" data-series-unit value="${escapeHTML(value.unit || '')}" placeholder="Unit (optional)" aria-label="Custom series unit" /></div>`
    ).join('');
    const quality = profile.timestamp;
    const profileCards = `<div class="dataset-kpis"><div><strong>${dataset.row_count.toLocaleString()}</strong><span>Source rows</span></div><div><strong>${dataset.column_count}</strong><span>Columns</span></div><div><strong>${profile.duplicate_row_count.toLocaleString()}</strong><span>Duplicate rows</span></div><div><strong>${quality.duplicate_count.toLocaleString()}</strong><span>Duplicate timestamps</span></div></div>`;
    const columnRows = columns.map((col) => `<tr><td>${escapeHTML(col.name)}</td><td>${escapeHTML(col.inferred_type)}</td><td>${col.missing_count}</td><td>${col.invalid_numeric_count}</td><td>${col.non_finite_count}</td><td>${col.candidate_unit ? escapeHTML(col.candidate_unit) : '—'}</td></tr>`).join('');
    const timestampSummary = quality.available
      ? `Timestamp mapping available · ${quality.valid_count.toLocaleString()} valid · ordered: ${quality.monotonic_non_decreasing === null ? 'unknown' : quality.monotonic_non_decreasing ? 'yes' : 'no'} · intervals: ${quality.sampling_interval_seconds.count.toLocaleString()} positive`
      : 'No confirmed, parseable timestamp mapping. Charts will use source row index until a timestamp column and numeric unit are explicitly mapped.';
    return `<div class="dataset-detail-head"><div><span class="eyebrow">RAW UPLOAD · TEMPORARY SESSION</span><h2>${escapeHTML(dataset.filename)}</h2><p class="card-subtitle">${escapeHTML(dataset.dataset_id)} · ${(dataset.size_bytes / 1024).toFixed(1)} KB · expires after 1 hour</p></div><button id="dataset-delete" class="btn btn-secondary btn-sm" aria-label="Delete ${escapeHTML(dataset.filename)}">Delete</button></div>
      ${profileCards}<div class="dataset-quality-note" role="status">${escapeHTML(timestampSummary)}${profile.parser_warnings.length ? `<br>Parser warnings: ${profile.parser_warnings.map(escapeHTML).join(' ')}` : ''}</div>
      <div class="dataset-section"><div class="card-header"><span class="card-title">Column mapping</span><span class="badge badge-amber">Suggestions require confirmation</span></div><p class="card-subtitle">No unit conversion or battery quantity is assumed. Cell channels must be explicitly present in the source.</p>
        <form id="dataset-mappings" class="dataset-mappings">${roleRows}<div id="dataset-custom-mappings">${customRows}</div><button id="dataset-add-series" class="btn btn-secondary btn-sm" type="button">Add user-defined numeric series</button><button class="btn btn-primary" type="submit">Save mappings</button><span id="mapping-status" role="status"></span></form></div>
      <div class="dataset-section"><div class="card-header"><span class="card-title">Data quality report</span><span class="badge badge-gray">Raw rows retained</span></div><div class="data-table-container dataset-table-scroll"><table class="data-table"><thead><tr><th>Column</th><th>Inferred type</th><th>Missing</th><th>Invalid numeric</th><th>Non-finite</th><th>Unit hint</th></tr></thead><tbody>${columnRows}</tbody></table></div></div>
      <div class="dataset-section"><div class="card-header"><div><span class="card-title">Dataset analytics</span><p class="card-subtitle">Each chart uses one mapped quantity and its canonical unit. Server bounds rendered points; original rows remain unchanged.</p></div><button id="dataset-chart-refresh" class="btn btn-secondary btn-sm">Refresh charts</button></div><div id="dataset-chart-grid" class="dataset-chart-grid"><div id="dataset-chart-empty" class="dataset-empty-chart">Map at least one numeric field to display its actual source values.</div></div><p id="dataset-chart-caption" class="card-subtitle"></p></div>
      <div class="dataset-section"><div class="card-header"><span class="card-title">Source preview</span><div class="dataset-pager"><button id="dataset-prev" class="btn btn-secondary btn-sm" ${this.previewOffset <= 0 ? 'disabled' : ''}>Previous</button><span>Rows ${(preview.offset + 1).toLocaleString()}–${Math.min(preview.offset + preview.rows.length, preview.total_rows).toLocaleString()} of ${preview.total_rows.toLocaleString()}</span><button id="dataset-next" class="btn btn-secondary btn-sm" ${preview.offset + preview.limit >= preview.total_rows ? 'disabled' : ''}>Next</button></div></div><div class="data-table-container dataset-table-scroll"><table class="data-table"><thead><tr>${preview.columns.map((col) => `<th>${escapeHTML(col)}</th>`).join('')}</tr></thead><tbody>${preview.rows.map((row) => `<tr>${preview.columns.map((col) => `<td>${escapeHTML(row[col] === null || row[col] === undefined ? '—' : row[col])}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>`;
  }

  _bindDetail(dataset) {
    this.container.querySelector('#dataset-delete').addEventListener('click', async () => {
      if (!window.confirm(`Delete temporary dataset “${dataset.filename}”?`)) return;
      try { await api.deleteDataset(dataset.dataset_id); this.active = null; this.container.querySelector('#dataset-detail').textContent = 'Dataset deleted.'; await this.loadDatasets(); }
      catch (error) { this.container.querySelector('#dataset-detail').prepend(document.createTextNode(`Delete failed: ${error.message} `)); }
    });
    this.container.querySelector('#dataset-mappings').addEventListener('submit', async (event) => {
      event.preventDefault();
      const status = this.container.querySelector('#mapping-status');
      const mappings = {};
      for (const [role] of MAPPING_ROLES) {
        const column = this.container.querySelector(`[data-map-role="${role}"]`).value;
        const unit = this.container.querySelector(`[data-unit-role="${role}"]`).value;
        if (column) mappings[role] = { column, unit: unit || null };
      }
      this.container.querySelectorAll('.dataset-custom-mapping').forEach((row) => {
        const name = row.querySelector('[data-series-name]').value.trim();
        const column = row.querySelector('[data-series-column]').value;
        const unit = row.querySelector('[data-series-unit]').value.trim();
        if (name && column) mappings[`series:${name}`] = { column, unit: unit || null };
      });
      status.textContent = 'Saving explicit mappings…';
      try { this.active = await api.mapDataset(dataset.dataset_id, mappings); await this.renderDetail(); }
      catch (error) { status.textContent = `Mapping error: ${error.message}`; }
    });
    this.container.querySelector('#dataset-add-series').addEventListener('click', () => {
      const wrapper = this.container.querySelector('#dataset-custom-mappings');
      const row = document.createElement('div'); row.className = 'dataset-mapping-row dataset-custom-mapping';
      const label = document.createElement('label'); label.textContent = 'User-defined numeric series';
      const name = document.createElement('input'); name.className = 'form-input'; name.dataset.seriesName = ''; name.maxLength = 90; name.placeholder = 'Quantity name'; name.setAttribute('aria-label', 'Custom series name'); label.append(name);
      const column = document.createElement('select'); column.className = 'form-select'; column.dataset.seriesColumn = ''; column.setAttribute('aria-label', 'Custom series source column');
      for (const sourceColumn of dataset.profile.columns) { const option = document.createElement('option'); option.value = sourceColumn.name; option.textContent = sourceColumn.name; column.append(option); }
      const unit = document.createElement('input'); unit.className = 'form-input'; unit.dataset.seriesUnit = ''; unit.placeholder = 'Unit (optional)'; unit.setAttribute('aria-label', 'Custom series unit');
      row.append(label, column, unit); wrapper.append(row); name.focus();
    });
    this.container.querySelector('#dataset-prev').addEventListener('click', async () => { this.previewOffset = Math.max(0, this.previewOffset - 25); await this.renderDetail(); });
    this.container.querySelector('#dataset-next').addEventListener('click', async () => { this.previewOffset += 25; await this.renderDetail(); });
    this.container.querySelector('#dataset-chart-refresh').addEventListener('click', () => this.loadChart(dataset));
    this.loadChart(dataset);
  }

  async loadChart(dataset) {
    const grid = this.container.querySelector('#dataset-chart-grid');
    const empty = this.container.querySelector('#dataset-chart-empty');
    const caption = this.container.querySelector('#dataset-chart-caption');
    const selected = Object.entries(dataset.profile.mappings || {}).filter(([key]) => key !== 'timestamp').map(([, item]) => item.column).filter(Boolean).slice(0, 5);
    if (dataset.profile.mappings?.voltage?.column && dataset.profile.mappings?.current?.column) selected.push('calculated_power_w');
    const columns = [...new Set(selected)];
    if (!columns.length) { grid.replaceChildren(empty); empty.hidden = false; return; }
    grid.replaceChildren(); caption.textContent = 'Loading mapped source series…';
    const requestId = ++this.requestId;
    try {
      const result = await api.getDatasetSeries(dataset.dataset_id, columns);
      if (requestId !== this.requestId || this.active?.dataset_id !== dataset.dataset_id) return;
      if (!result.points.length) { grid.append(empty); empty.hidden = false; empty.textContent = 'No source rows are available for these charts.'; return; }
      empty.hidden = true;
      columns.forEach((column) => {
        const card = document.createElement('article'); card.className = 'dataset-series-card';
        const title = document.createElement('h3');
        const role = Object.entries(dataset.profile.mappings || {}).find(([, item]) => item.column === column)?.[0];
        const roleLabels = { voltage: 'Voltage', current: 'Current', temperature: 'Temperature', soc: 'State of charge', soh: 'State of health', cell_voltage: 'Explicit cell voltage' };
        const unit = column === 'calculated_power_w' ? 'W' : ({ voltage: 'V', current: 'A', temperature: '°C', soc: '%', soh: '%', cell_voltage: 'V' }[role] || dataset.profile.mappings?.[role]?.unit || 'source unit');
        title.textContent = `${column === 'calculated_power_w' ? 'Calculated power' : roleLabels[role] || column} · ${unit}`;
        const axis = document.createElement('p'); axis.className = 'card-subtitle'; axis.textContent = `${result.x_axis === 'timestamp_ns' ? 'Source timestamp' : 'Source row index'} · ${unit}`;
        const canvas = document.createElement('canvas'); canvas.setAttribute('role', 'img'); canvas.tabIndex = 0;
        canvas.setAttribute('aria-label', `${title.textContent} chart using ${result.rendered_point_count} dataset points`);
        card.append(title, axis, canvas); grid.append(card);
        canvas._datasetChartData = { result, column, unit };
        this._drawChart(canvas, result, column, unit);
      });
      this.seriesObserver?.disconnect();
      if (typeof ResizeObserver === 'function') {
        this.seriesObserver = new ResizeObserver(() => this.container.querySelectorAll('.dataset-series-card canvas').forEach((canvas) => {
          if (canvas._datasetChartData) this._drawChart(canvas, canvas._datasetChartData.result, canvas._datasetChartData.column, canvas._datasetChartData.unit);
        }));
        this.seriesObserver.observe(grid);
      }
      caption.textContent = `${result.rendered_point_count.toLocaleString()} of ${result.raw_row_count.toLocaleString()} raw rows rendered (stride ${result.stride}). X axis: ${result.x_axis === 'timestamp_ns' ? 'source timestamp' : 'source row index'}. ${result.derived.calculated_power_w?.sign_convention || ''}`;
    } catch (error) {
      grid.replaceChildren(empty); empty.hidden = false; empty.textContent = `Chart unavailable: ${error.message}`;
    }
  }

  _drawChart(canvas, result, column, unit) {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.parentElement.clientWidth;
    const height = 300;
    canvas.width = Math.floor(width * dpr); canvas.height = Math.floor(height * dpr);
    canvas.style.width = '100%'; canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, width, height);
    const pad = { left: 58, right: 18, top: 18, bottom: 42 };
    const plotW = Math.max(width - pad.left - pad.right, 1), plotH = height - pad.top - pad.bottom;
    const values = result.points.map((point) => point[column]).filter(Number.isFinite);
    if (!values.length) return;
    let min = Math.min(...values), max = Math.max(...values);
    if (min === max) { min -= 1; max += 1; }
    ctx.strokeStyle = '#e3e9f1'; ctx.fillStyle = '#52627a'; ctx.font = '11px sans-serif'; ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (plotH * i / 4); ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
      ctx.fillText((max - (max - min) * i / 4).toPrecision(4), 3, y + 4);
    }
    const timestamps = result.points.map((point) => point.timestamp_ns).filter(Number.isFinite);
    const minX = result.x_axis === 'timestamp_ns' && timestamps.length ? result.x_min_ns : 0;
    const maxX = result.x_axis === 'timestamp_ns' && timestamps.length ? result.x_max_ns : Math.max(result.raw_row_count - 1, 0);
    const xFraction = (point) => {
      if (result.x_axis === 'timestamp_ns') {
        if (!Number.isFinite(point.timestamp_ns)) return null;
        return maxX === minX ? 0 : (point.timestamp_ns - minX) / (maxX - minX);
      }
      return result.raw_row_count <= 1 ? 0 : point.row_index / (result.raw_row_count - 1);
    };
    const xLabel = (x) => result.x_axis === 'timestamp_ns'
      ? new Date(x / 1e6).toLocaleString() : `row ${x + 1}`;
    ctx.fillText(xLabel(result.x_axis === 'timestamp_ns' ? minX : 0), pad.left, height - 23);
    const lastLabel = xLabel(result.x_axis === 'timestamp_ns' ? maxX : Math.max(result.raw_row_count - 1, 0));
    ctx.fillText(lastLabel, Math.max(pad.left, width - pad.right - ctx.measureText(lastLabel).width), height - 23);
    ctx.fillText(`Mapped value (${unit})`, pad.left, height - 8);
    ctx.strokeStyle = '#2563eb'; ctx.lineWidth = 1.8; ctx.beginPath();
    let started = false;
    result.points.forEach((point, idx) => {
      const value = point[column];
      if (point.gap_before?.includes(column)) started = false;
      const fraction = xFraction(point);
      if (!Number.isFinite(value) || fraction === null) { started = false; return; }
      const x = pad.left + plotW * fraction;
      const y = pad.top + plotH * (1 - (value - min) / (max - min));
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    });
    ctx.stroke();
    canvas.setAttribute('aria-label', `Dataset analytics chart for ${column} (${unit}) from ${result.rendered_point_count} selected source rows.`);
    canvas.onpointermove = (event) => {
      const rect = canvas.getBoundingClientRect();
      const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left - pad.left) / plotW));
      let index = 0;
      let smallestDistance = Infinity;
      result.points.forEach((point, candidateIndex) => {
        const pointFraction = xFraction(point);
        if (pointFraction === null) return;
        const distance = Math.abs(pointFraction - fraction);
        if (distance < smallestDistance) { index = candidateIndex; smallestDistance = distance; }
      });
      const point = result.points[index];
      const time = Number.isFinite(point.timestamp_ns) ? new Date(point.timestamp_ns / 1e6).toISOString() : `source row ${point.row_index + 1}`;
      canvas.title = `${time}\n${column}: ${Number.isFinite(point[column]) ? point[column] : '—'} ${unit}`;
    };
  }

  update() {}
  destroy() { this.seriesObserver?.disconnect(); }
}
