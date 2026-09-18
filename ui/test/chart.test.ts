/**
 * Implementation note.
 *
 * Implementation note.
 * Implementation note.
 */

import './stub-dom.js';

import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { LineChart, type LineChartOptions } from '../src/chart/line-chart.js';

interface DrawLog {
  arcs: number;
  strokes: number;
  fills: number;
  texts: string[];
  dashes: number[][];
  transform: number[] | null;
}

/* Implementation note. */
function stubCanvas(width = 800, height = 360): { canvas: HTMLCanvasElement; log: DrawLog } {
  const log: DrawLog = { arcs: 0, strokes: 0, fills: 0, texts: [], dashes: [], transform: null };

  const ctx = {
    setTransform: (...args: number[]) => {
      log.transform = args;
    },
    clearRect: () => {},
    save: () => {},
    restore: () => {},
    beginPath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    bezierCurveTo: () => {},
    closePath: () => {},
    translate: () => {},
    rotate: () => {},
    roundRect: () => {},
    arc: () => {
      log.arcs += 1;
    },
    stroke: () => {
      log.strokes += 1;
    },
    fill: () => {
      log.fills += 1;
    },
    fillText: (text: string) => {
      log.texts.push(text);
    },
    measureText: (text: string) => ({ width: text.length * 7 }),
    setLineDash: (dash: number[]) => {
      log.dashes.push(dash);
    },
    font: '',
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1,
    textAlign: '',
    textBaseline: '',
  };

  const canvas = {
    width: 0,
    height: 0,
    style: {} as Record<string, string>,
    parentElement: { clientWidth: width, clientHeight: height },
    getContext: () => ctx,
    getBoundingClientRect: () => ({ width, height, left: 0, top: 0 }),
    addEventListener: () => {},
    removeEventListener: () => {},
  };

  return { canvas: canvas as unknown as HTMLCanvasElement, log };
}

function options(overrides: Partial<LineChartOptions> = {}): LineChartOptions {
  return {
    labels: ['09-08', '09-09', '09-10'],
    dark: false,
    formatValue: (v) => v.toFixed(2),
    series: [
      { label: 'Balance', values: [100, 80, 60], color: '#6366f1', fill: 'rgba(99,102,241,0.1)' },
      { label: 'Alert threshold', values: [50, 50, 50], color: '#ef4444', dashed: true, showPoints: false },
    ],
    ...overrides,
  };
}

describe('LineChart', () => {
  it('按 CSS 尺寸乘以像素比设置画布，高分屏下不糊', () => {
    const { canvas, log } = stubCanvas(800, 360);
    new LineChart(canvas, options());

    assert.equal(canvas.width, 800);
    assert.equal(canvas.height, 360);
    assert.equal(canvas.style['width'], '800px');
    assert.deepEqual(log.transform, [1, 0, 0, 1, 0, 0]);
  });

  it('Balance线每个点画一个圆，阈值线一个都不画', () => {
    const { canvas, log } = stubCanvas();
    new LineChart(canvas, options());

    // Implementation note.
    assert.equal(log.arcs, 5);
  });

  it('阈值线用虚线，Balance线是实线', () => {
    const { canvas, log } = stubCanvas();
    new LineChart(canvas, options());

    assert.ok(log.dashes.some((d) => d.length === 2 && d[0] === 5 && d[1] === 5), '阈值线应该是 5/5 虚线');
    assert.ok(log.dashes.some((d) => d.length === 0), 'Balance线应该是实线');
  });

  it('画出图例文字和 y 轴刻度', () => {
    const { canvas, log } = stubCanvas();
    new LineChart(canvas, options());

    assert.ok(log.texts.includes('Balance'));
    assert.ok(log.texts.includes('Alert threshold'));
    assert.ok(log.texts.includes('09-08'));
    assert.ok(log.texts.length > 5, 'y 轴刻度也要画出来');
  });

  it('Balance一直没变也不会除零，仍然画出线', () => {
    const { canvas, log } = stubCanvas();
    new LineChart(canvas, options({ series: [{ label: 'Balance', values: [100, 100, 100], color: '#000' }] }));

    assert.ok(log.strokes > 0);
    assert.ok(log.texts.every((t) => t !== 'NaN' && !t.includes('NaN')), '刻度不能出现 NaN');
  });

  it('只有一个数据点时画在正中间，不崩', () => {
    const { canvas, log } = stubCanvas();
    new LineChart(canvas, options({ labels: ['09-08'], series: [{ label: 'Balance', values: [42], color: '#000' }] }));

    assert.ok(log.arcs >= 1);
  });

  it('没有数据时直接返回，不画任何东西', () => {
    const { canvas, log } = stubCanvas();
    new LineChart(canvas, options({ labels: [], series: [{ label: 'Balance', values: [], color: '#000' }] }));

    assert.equal(log.strokes, 0);
    assert.equal(log.texts.length, 0);
  });

  it('values 里的 null 被跳过，不会画成 0', () => {
    const { canvas, log } = stubCanvas();
    new LineChart(canvas, options({ series: [{ label: 'Balance', values: [100, null, 60], color: '#000' }] }));

    // Implementation note.
    assert.equal(log.arcs, 3);
  });

  it('update 换数据后重画，destroy 后清空画布', () => {
    const { canvas, log } = stubCanvas();
    const chart = new LineChart(canvas, options());
    const before = log.arcs;

    chart.update(options({ labels: ['09-08'], series: [{ label: 'Balance', values: [1], color: '#000' }] }));
    assert.ok(log.arcs > before);

    chart.destroy(); // 不抛即可
  });
});
