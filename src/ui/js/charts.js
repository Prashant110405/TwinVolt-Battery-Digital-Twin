/**
 * High-Performance Canvas2D Time-Series Streaming Chart Engine
 * Renders multi-signal buffered telemetry data smoothly at display refresh rates.
 */

export class StreamingChart {
  constructor(canvasElement, options = {}) {
    this.canvas = canvasElement;
    this.ctx = canvasElement.getContext('2d');
    this.title = options.title || '';
    this.unit = options.unit || '';
    this.series = options.series || []; // Array of { key, label, color, lineWidth, dashed }
    this.minY = options.minY !== undefined ? options.minY : null;
    this.maxY = options.maxY !== undefined ? options.maxY : null;
    this.autoScale = options.autoScale !== undefined ? options.autoScale : true;
    this.padding = { top: 20, right: 20, bottom: 25, left: 45 };

    this._resizeHandler = () => this.resize();
    window.addEventListener('resize', this._resizeHandler);
    this.canvas.setAttribute('role', 'img');
    this.canvas.setAttribute('aria-label', options.ariaLabel || 'Streaming battery twin chart. Awaiting data.');
    this.canvas.tabIndex = 0;
    this._tooltipHandler = (event) => {
      const buffer = this.lastBuffer;
      if (!buffer || buffer.timestamps.length === 0) return;
      const rect = this.canvas.getBoundingClientRect();
      const x = event.clientX - rect.left - this.padding.left;
      const plotWidth = this.width - this.padding.left - this.padding.right;
      const fraction = Math.max(0, Math.min(1, x / plotWidth));
      const first = buffer.timestamps[0];
      const last = buffer.timestamps[buffer.timestamps.length - 1];
      const target = first + fraction * (last - first);
      let index = 0;
      for (let i = 1; i < buffer.timestamps.length; i++) {
        if (Math.abs(buffer.timestamps[i] - target) < Math.abs(buffer.timestamps[index] - target)) index = i;
      }
      const stamp = new Date(buffer.timestamps[index] * 1000).toLocaleString();
      const readings = this.series.map((series) => {
        const value = buffer.data[series.key]?.[index];
        return `${series.label}: ${Number.isFinite(value) ? value : '—'}`;
      });
      this.canvas.title = [stamp, ...readings].join('\n');
    };
    this.canvas.addEventListener('pointermove', this._tooltipHandler);
    this.resizeObserver = typeof ResizeObserver === 'function'
      ? new ResizeObserver(() => this.resize()) : null;
    if (this.resizeObserver) this.resizeObserver.observe(this.canvas.parentElement);
    else window.addEventListener('resize', this._resizeHandler);
    this.resize();
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.width = rect.width;
    this.height = rect.height;

    this.canvas.width = Math.floor(this.width * dpr);
    this.canvas.height = Math.floor(this.height * dpr);
    if (this.ctx) this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  destroy() {
    this.resizeObserver?.disconnect();
    if (!this.resizeObserver) window.removeEventListener('resize', this._resizeHandler);
    this.canvas.removeEventListener('pointermove', this._tooltipHandler);
  }

  render(buffer) {
    this.lastBuffer = buffer;
    if (!this.ctx || !buffer || !buffer.timestamps || buffer.timestamps.length === 0) {
      this._renderEmpty();
      return;
    }

    const { ctx, width, height, padding } = this;
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;

    if (plotWidth <= 0 || plotHeight <= 0) return;

    ctx.clearRect(0, 0, width, height);
    this.canvas.setAttribute('aria-label', `${this.series.map((s) => s.label).join(', ')} chart with ${buffer.timestamps.length} timestamped samples.`);

    // 1. Calculate Y-Range
    let minY = this.minY !== null ? this.minY : Infinity;
    let maxY = this.maxY !== null ? this.maxY : -Infinity;

    if (this.autoScale) {
      for (const s of this.series) {
        const values = buffer.data[s.key];
        if (values) {
          for (let i = 0; i < values.length; i++) {
            const v = values[i];
            if (v !== null && !isNaN(v)) {
              if (v < minY) minY = v;
              if (v > maxY) maxY = v;
            }
          }
        }
      }
    }

    if (minY === Infinity || maxY === -Infinity || minY === maxY) {
      minY = this.minY !== null ? this.minY : (minY === Infinity ? 0 : minY - 1);
      maxY = this.maxY !== null ? this.maxY : (maxY === -Infinity ? 100 : maxY + 1);
    } else {
      // Add 5% padding to Y range
      const span = maxY - minY;
      minY -= span * 0.05;
      maxY += span * 0.05;
    }

    // 2. Render Grid & Axes
    this._drawGrid(minY, maxY, plotWidth, plotHeight);
    this._drawTimeAxis(buffer.timestamps, plotWidth, plotHeight);

    // 3. Draw Series Lines
    const count = buffer.timestamps.length;
    if (count < 2) return;
    const firstTime = buffer.timestamps[0];
    const timeSpan = buffer.timestamps[count - 1] - firstTime;

    for (const s of this.series) {
      const values = buffer.data[s.key];
      if (!values || values.length === 0) continue;

      ctx.save();
      ctx.beginPath();
      ctx.strokeStyle = s.color || '#38bdf8';
      ctx.lineWidth = s.lineWidth || 2;
      if (s.dashed) {
        ctx.setLineDash([4, 4]);
      }

      let started = false;
      for (let i = 0; i < count; i++) {
        const val = values[i];
        if (val === null || isNaN(val)) {
          started = false;
          continue;
        }

        const elapsedFraction = timeSpan > 0
          ? (buffer.timestamps[i] - firstTime) / timeSpan
          : i / (count - 1);
        const x = padding.left + elapsedFraction * plotWidth;
        const y = padding.top + plotHeight - ((val - minY) / (maxY - minY)) * plotHeight;

        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
      ctx.restore();
    }
  }

  _drawGrid(minY, maxY, plotWidth, plotHeight) {
    const { ctx, padding, width, height } = this;

    ctx.save();
    ctx.strokeStyle = '#e8edf4';
    ctx.lineWidth = 1;
    ctx.fillStyle = '#718096';
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';

    const ySteps = 4;
    for (let i = 0; i <= ySteps; i++) {
      const yVal = minY + (i / ySteps) * (maxY - minY);
      const yPos = padding.top + plotHeight - (i / ySteps) * plotHeight;

      ctx.beginPath();
      ctx.moveTo(padding.left, yPos);
      ctx.lineTo(padding.left + plotWidth, yPos);
      ctx.stroke();

      const label = yVal.toFixed(yVal < 10 && yVal > -10 ? 2 : 1);
      ctx.fillText(label, padding.left - 6, yPos);
    }

    ctx.restore();
  }

  _drawTimeAxis(timestamps, plotWidth, plotHeight) {
    if (timestamps.length < 2) return;
    const { ctx, padding } = this;
    const first = timestamps[0];
    const last = timestamps[timestamps.length - 1];
    ctx.save();
    ctx.fillStyle = '#718096';
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.textBaseline = 'top';
    ctx.textAlign = 'left';
    const fmt = (seconds) => {
      const date = new Date(seconds * 1000);
      return Number.isNaN(date.getTime()) ? '—' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    };
    ctx.fillText(fmt(first), padding.left, padding.top + plotHeight + 7);
    ctx.textAlign = 'right';
    ctx.fillText(fmt(last), padding.left + plotWidth, padding.top + plotHeight + 7);
    ctx.restore();
  }

  _renderEmpty() {
    const { ctx, width, height } = this;
    ctx.clearRect(0, 0, width, height);
    ctx.save();
    ctx.fillStyle = '#718096';
    ctx.font = '12px "Inter", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('Awaiting real-time telemetry stream...', width / 2, height / 2);
    ctx.restore();
  }
}
