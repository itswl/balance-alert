/**
 * Implementation note.
 *
 * Implementation note.
 * Implementation note.
 * Implementation note.
 * Implementation note.
 */

export interface Series {
  label: string;
  values: Array<number | null>;
  color: string;
  /* Implementation note. */
  fill?: string;
  dashed?: boolean;
  /* Implementation note. */
  showPoints?: boolean;
}

export interface LineChartOptions {
  labels: string[];
  series: Series[];
  /* Implementation note. */
  formatValue: (value: number) => string;
  dark: boolean;
}

interface Layout {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

const PADDING: Layout = { left: 64, right: 16, top: 34, bottom: 52 };
const Y_TICKS = 5;
const POINT_RADIUS = 3;
const HOVER_RADIUS = 6;
/* Implementation note. */
const TENSION = 0.4;

export class LineChart {
  private readonly canvas: HTMLCanvasElement;
  private readonly ctx: CanvasRenderingContext2D;
  private options: LineChartOptions;
  private hoverIndex = -1;
  private readonly onMove: (event: MouseEvent) => void;
  private readonly onLeave: () => void;
  private readonly resizeObserver: ResizeObserver | null;

  constructor(canvas: HTMLCanvasElement, options: LineChartOptions) {
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('This browser does not support 2D canvas');
    this.canvas = canvas;
    this.ctx = ctx;
    this.options = options;

    this.onMove = (event: MouseEvent): void => {
      const index = this.indexAt(event);
      if (index !== this.hoverIndex) {
        this.hoverIndex = index;
        this.draw();
      }
    };
    this.onLeave = (): void => {
      if (this.hoverIndex !== -1) {
        this.hoverIndex = -1;
        this.draw();
      }
    };
    canvas.addEventListener('mousemove', this.onMove);
    canvas.addEventListener('mouseleave', this.onLeave);

    // Implementation note.
    this.resizeObserver =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => this.draw());
    this.resizeObserver?.observe(canvas.parentElement ?? canvas);

    this.draw();
  }

  update(options: LineChartOptions): void {
    this.options = options;
    this.hoverIndex = -1;
    this.draw();
  }

  destroy(): void {
    this.canvas.removeEventListener('mousemove', this.onMove);
    this.canvas.removeEventListener('mouseleave', this.onLeave);
    this.resizeObserver?.disconnect();
    const { width, height } = this.canvas;
    this.ctx.clearRect(0, 0, width, height);
  }

  // Implementation note.

  /* Implementation note. */
  private size(): { width: number; height: number } {
    const rect = this.canvas.getBoundingClientRect();
    const parent = this.canvas.parentElement;
    return {
      width: Math.max(1, Math.round(rect.width || parent?.clientWidth || 0)),
      height: Math.max(1, Math.round(rect.height || parent?.clientHeight || 0)),
    };
  }

  /* Implementation note. */
  private range(): { min: number; max: number } {
    const values: number[] = [];
    for (const s of this.options.series) {
      for (const v of s.values) {
        if (typeof v === 'number' && Number.isFinite(v)) values.push(v);
      }
    }
    if (values.length === 0) return { min: 0, max: 1 };

    let min = Math.min(...values);
    let max = Math.max(...values);
    if (min === max) {
      // Implementation note.
      const pad = Math.abs(min) * 0.1 || 1;
      min -= pad;
      max += pad;
    } else {
      const pad = (max - min) * 0.1;
      min -= pad;
      max += pad;
    }
    return { min, max };
  }

  private xAt(index: number, width: number): number {
    const count = this.options.labels.length;
    const span = width - PADDING.left - PADDING.right;
    if (count <= 1) return PADDING.left + span / 2;
    return PADDING.left + (span * index) / (count - 1);
  }

  private yAt(value: number, height: number, min: number, max: number): number {
    const span = height - PADDING.top - PADDING.bottom;
    const ratio = (value - min) / (max - min || 1);
    return PADDING.top + span * (1 - ratio);
  }

  private indexAt(event: MouseEvent): number {
    const rect = this.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const { width } = this.size();
    if (this.options.labels.length === 0) return -1;
    if (x < PADDING.left - 8 || x > width - PADDING.right + 8) return -1;

    let best = -1;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (let i = 0; i < this.options.labels.length; i += 1) {
      const distance = Math.abs(this.xAt(i, width) - x);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = i;
      }
    }
    return best;
  }

  // Implementation note.

  draw(): void {
    const { width, height } = this.size();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(width * dpr);
    this.canvas.height = Math.round(height * dpr);
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;

    const ctx = this.ctx;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    if (this.options.labels.length === 0) return;

    const { dark } = this.options;
    const textColor = dark ? '#e5e7eb' : '#374151';
    const gridColor = dark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
    const { min, max } = this.range();

    this.drawGrid(width, height, min, max, gridColor, textColor);
    this.drawXLabels(width, height, textColor);

    for (const series of this.options.series) {
      this.drawSeries(series, width, height, min, max);
    }

    this.drawLegend(width, textColor);

    if (this.hoverIndex >= 0) {
      this.drawHover(width, height, min, max, dark, textColor, gridColor);
    }
  }

  private drawGrid(width: number, height: number, min: number, max: number, gridColor: string, textColor: string): void {
    const ctx = this.ctx;
    ctx.save();
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    ctx.fillStyle = textColor;
    ctx.font = '11px var(--mono, monospace)';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';

    for (let i = 0; i <= Y_TICKS; i += 1) {
      const value = min + ((max - min) * i) / Y_TICKS;
      const y = Math.round(this.yAt(value, height, min, max)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(PADDING.left, y);
      ctx.lineTo(width - PADDING.right, y);
      ctx.stroke();
      ctx.fillText(value.toLocaleString('zh-CN', { maximumFractionDigits: 2 }), PADDING.left - 8, y);
    }
    ctx.restore();
  }

  /* Implementation note. */
  private drawXLabels(width: number, height: number, textColor: string): void {
    const ctx = this.ctx;
    const labels = this.options.labels;
    const usable = width - PADDING.left - PADDING.right;
    const step = Math.max(1, Math.ceil(labels.length / Math.max(1, Math.floor(usable / 46))));

    ctx.save();
    ctx.fillStyle = textColor;
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < labels.length; i += step) {
      const x = this.xAt(i, width);
      ctx.save();
      ctx.translate(x, height - PADDING.bottom + 14);
      ctx.rotate(-Math.PI / 4);
      ctx.fillText(labels[i] ?? '', 0, 0);
      ctx.restore();
    }
    ctx.restore();
  }

  /* Implementation note. */
  private tracePath(points: Array<{ x: number; y: number }>): void {
    const ctx = this.ctx;
    ctx.beginPath();
    if (points.length === 0) return;
    ctx.moveTo(points[0]!.x, points[0]!.y);
    for (let i = 0; i < points.length - 1; i += 1) {
      const p0 = points[i - 1] ?? points[i]!;
      const p1 = points[i]!;
      const p2 = points[i + 1]!;
      const p3 = points[i + 2] ?? p2;
      ctx.bezierCurveTo(
        p1.x + ((p2.x - p0.x) / 6) * TENSION * 1.5,
        p1.y + ((p2.y - p0.y) / 6) * TENSION * 1.5,
        p2.x - ((p3.x - p1.x) / 6) * TENSION * 1.5,
        p2.y - ((p3.y - p1.y) / 6) * TENSION * 1.5,
        p2.x,
        p2.y,
      );
    }
  }

  private drawSeries(series: Series, width: number, height: number, min: number, max: number): void {
    const ctx = this.ctx;
    const points: Array<{ x: number; y: number }> = [];
    series.values.forEach((value, index) => {
      if (typeof value === 'number' && Number.isFinite(value)) {
        points.push({ x: this.xAt(index, width), y: this.yAt(value, height, min, max) });
      }
    });
    if (points.length === 0) return;

    ctx.save();

    if (series.fill) {
      this.tracePath(points);
      ctx.lineTo(points[points.length - 1]!.x, height - PADDING.bottom);
      ctx.lineTo(points[0]!.x, height - PADDING.bottom);
      ctx.closePath();
      ctx.fillStyle = series.fill;
      ctx.fill();
    }

    this.tracePath(points);
    ctx.strokeStyle = series.color;
    ctx.lineWidth = 2;
    ctx.setLineDash(series.dashed ? [5, 5] : []);
    ctx.stroke();
    ctx.setLineDash([]);

    if (series.showPoints !== false) {
      ctx.fillStyle = series.color;
      for (const point of points) {
        ctx.beginPath();
        ctx.arc(point.x, point.y, POINT_RADIUS, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }

  private drawLegend(width: number, textColor: string): void {
    const ctx = this.ctx;
    ctx.save();
    ctx.font = '12px sans-serif';
    ctx.textBaseline = 'middle';

    const entries = this.options.series.map((s) => ({ series: s, width: ctx.measureText(s.label).width + 24 }));
    const total = entries.reduce((sum, e) => sum + e.width, 0) + (entries.length - 1) * 15;
    let x = (width - total) / 2;
    const y = 14;

    for (const { series, width: entryWidth } of entries) {
      ctx.fillStyle = series.color;
      ctx.beginPath();
      ctx.arc(x + 5, y, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = textColor;
      ctx.textAlign = 'left';
      ctx.fillText(series.label, x + 16, y);
      x += entryWidth + 15;
    }
    ctx.restore();
  }

  /* Implementation note. */
  private drawHover(
    width: number,
    height: number,
    min: number,
    max: number,
    dark: boolean,
    textColor: string,
    gridColor: string,
  ): void {
    const ctx = this.ctx;
    const index = this.hoverIndex;
    const x = this.xAt(index, width);

    ctx.save();
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(Math.round(x) + 0.5, PADDING.top);
    ctx.lineTo(Math.round(x) + 0.5, height - PADDING.bottom);
    ctx.stroke();

    const lines: string[] = [];
    for (const series of this.options.series) {
      const value = series.values[index];
      if (typeof value !== 'number' || !Number.isFinite(value)) continue;
      lines.push(`${series.label}: ${this.options.formatValue(value)}`);
      if (series.showPoints !== false) {
        ctx.fillStyle = series.color;
        ctx.beginPath();
        ctx.arc(x, this.yAt(value, height, min, max), HOVER_RADIUS, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    const title = this.options.labels[index] ?? '';
    ctx.font = '12px sans-serif';
    const boxWidth = Math.max(ctx.measureText(title).width, ...lines.map((l) => ctx.measureText(l).width)) + 24;
    const boxHeight = 24 + lines.length * 18;
    const boxX = Math.min(Math.max(x + 12, PADDING.left), width - PADDING.right - boxWidth);
    const boxY = PADDING.top + 8;

    ctx.fillStyle = dark ? '#1f2937' : '#ffffff';
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(boxX, boxY, boxWidth, boxHeight, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = textColor;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(title, boxX + 12, boxY + 8);
    lines.forEach((line, i) => {
      ctx.fillText(line, boxX + 12, boxY + 26 + i * 18);
    });
    ctx.restore();
  }
}
