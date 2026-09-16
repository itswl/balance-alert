/** 余额趋势弹窗：统计卡片 + 折线图，需 ENABLE_HISTORY_API。 */

import { getTrend } from '../api/endpoints.js';
import type { TrendData, TrendResponse } from '../api/types.js';
import { LineChart } from '../chart/line-chart.js';
import { byId, requireById } from '../dom.js';
import { escapeHTML, formatCurrency } from '../format.js';
import { bindModalClose, closeModal, openModal } from '../ui/modal.js';
import { setLoading } from '../ui/loading.js';

const MODAL_ID = 'trend-modal';
const TREND_DAYS = 30;

let chart: LineChart | null = null;

function destroyChart(): void {
  chart?.destroy();
  chart = null;
}

export async function showProjectTrend(projectName: string, provider: string): Promise<void> {
  const title = byId('trend-modal-title');
  const statsContainer = byId('trend-stats-container');
  if (title) title.textContent = `余额趋势 - ${projectName}`;

  setLoading(true);
  openModal(MODAL_ID);

  try {
    const { response, data } = await getTrend(provider, projectName, TREND_DAYS);

    // 数据库没开或这个项目还没历史，后端返回 404；这里不当异常，给一段说明
    if (!response.ok || !data || data.status !== 'success') {
      destroyChart();
      if (statsContainer) {
        const message = data && 'message' in data && data.message ? data.message : '暂无历史数据';
        statsContainer.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: var(--text-secondary);">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width: 48px; height: 48px; margin: 0 auto 1rem;">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                    </svg>
                    <p>${escapeHTML(message)}</p>
                    <p style="font-size: 0.875rem; margin-top: 0.5rem;">
                        提示：需要启用数据库功能才能查看趋势图表<br>
                        请设置环境变量 ENABLE_DATABASE=true 并重启服务
                    </p>
                </div>
            `;
      }
      return;
    }

    const trendData = (data as TrendResponse).data;
    if (statsContainer) statsContainer.innerHTML = renderTrendStats(trendData);
    renderTrendChart(trendData);
  } catch (error) {
    destroyChart();
    console.error('加载趋势数据失败:', error);
    if (statsContainer) {
      const message = error instanceof Error ? error.message : String(error);
      statsContainer.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: var(--danger);">
                <p>加载失败：${escapeHTML(message)}</p>
            </div>
        `;
    }
  } finally {
    setLoading(false);
  }
}

/** 数据点不足两个时后端不给 change，此时按「稳定」显示 */
export function trendDirection(change: number | undefined): 'up' | 'down' | 'stable' {
  if (change !== undefined && change > 0) return 'up';
  if (change !== undefined && change < 0) return 'down';
  return 'stable';
}

export function renderTrendStats(trendData: TrendData): string {
  const direction = trendDirection(trendData.change);
  const stats = [
    { label: '当前余额', value: formatCurrency(trendData.current_balance), cls: '' },
    { label: '平均余额', value: formatCurrency(trendData.avg_balance), cls: '' },
    { label: '最高余额', value: formatCurrency(trendData.max_balance), cls: '' },
    { label: '最低余额', value: formatCurrency(trendData.min_balance), cls: '' },
    {
      label: '变化趋势',
      value: direction === 'up' ? '↑ 上升' : direction === 'down' ? '↓ 下降' : '→ 稳定',
      cls: direction === 'up' ? 'positive' : direction === 'down' ? 'negative' : '',
    },
  ];

  return stats
    .map(
      (stat) => `
        <div class="trend-stat-card">
            <div class="trend-stat-label">${escapeHTML(stat.label)}</div>
            <div class="trend-stat-value ${stat.cls}">${escapeHTML(stat.value)}</div>
        </div>
    `,
    )
    .join('');
}

function renderTrendChart(trendData: TrendData): void {
  const canvas = requireById<HTMLCanvasElement>('trend-chart');
  const history = trendData.history || [];
  const labels = history.map((h) => new Date(h.timestamp).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }));
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';

  const options = {
    labels,
    dark,
    formatValue: (value: number): string => formatCurrency(value),
    series: [
      {
        label: '余额',
        values: history.map((h) => h.balance),
        color: '#6366f1',
        fill: 'rgba(99, 102, 241, 0.1)',
      },
      {
        label: '告警阈值',
        values: labels.map(() => trendData.threshold),
        color: '#ef4444',
        dashed: true,
        showPoints: false,
      },
    ],
  };

  // 同一个 canvas 反复开关弹窗，复用实例避免监听器越积越多
  if (chart) chart.update(options);
  else chart = new LineChart(canvas, options);
}

export function bindTrendManager(): void {
  bindModalClose(MODAL_ID, '.js-close-trend-modal', destroyChart);
}

export function closeTrendModal(): void {
  closeModal(MODAL_ID);
  destroyChart();
}
