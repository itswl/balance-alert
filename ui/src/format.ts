/**
 * 纯格式化与Status判定。
 *
 * 这个模块不碰 DOM、不碰 fetch，是冒烟测试唯一需要直接调用的地方 ——
 * 看板上所有「这个数字该显示成什么」的判断都收在这里，改了就一定有测试兜底。
 */

import type { BalanceType, Runway } from './api/types.js';

/** 跑道的展示档位，与 CSS 里的 .runway-* 一一对应 */
export type RunwayLevel = 'danger' | 'warning' | 'normal' | 'unknown';

/** Balance相对阈值的健康度，与 CSS 里进度条的 .normal/.warning/.danger 对应 */
export type BalanceStatus = 'normal' | 'warning' | 'danger';

export interface RunwayDisplay {
  text: string;
  level: RunwayLevel;
  /** 鼠标悬停时的解释，没有可解释的内容时是空串 */
  hint: string;
}

/** 后端可能给 null，也可能在旧数据里留下字符串，统一按 parseFloat 的语义收口 */
function toNumber(value: unknown): number {
  if (typeof value === 'number') return value;
  return Number.parseFloat(String(value ?? ''));
}

/** Amount：两位小数，解析不出数字时给 '-' 而不是 0 */
export function formatCurrency(value: unknown): string {
  const num = toNumber(value);
  if (Number.isNaN(num)) return '-';
  return num.toFixed(2);
}

/** 千分位整数 */
export function formatNumber(num: number): string {
  return new Intl.NumberFormat('en-US').format(num);
}

/** Balance类型 → 展示名 */
export function typeLabel(type: string | null | undefined): string {
  const labels: Record<string, string> = { credits: 'Credits', balance: 'Balance', quota: 'Quota' };
  return (type ? labels[type] : undefined) ?? (type || 'Balance');
}

/**
 * 按类型格式化Balance，返回的是 HTML 片段：Quota型带一个 `<span class="unit">%</span>`。
 * 这里不转义，因为输入已经被 parseFloat 过滤成纯数字。
 */
export function formatBalance(value: unknown, type: BalanceType | string | null | undefined): string {
  const num = toNumber(value);
  if (Number.isNaN(num)) return '-';
  if (type === 'quota') {
    return `${num.toFixed(1)}<span class="unit">%</span>`;
  }
  return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/**
 * 跑道：按当前消耗速率还能用多久。
 * 数据不足、没有消耗这两种情况都要说得清楚，绝不能显示成 0 —— 那会被读成「马上耗尽」。
 */
export function formatRunway(runway: Runway | null | undefined): RunwayDisplay {
  if (!runway || runway.confidence === 'none') {
    return { text: 'Accumulating data', level: 'unknown', hint: 'Estimates appear after several hours of balance history' };
  }
  if (!runway.burn_per_day) {
    return { text: 'No spending', level: 'normal', hint: `Balance did not decrease in the last ${runway.window_days} days` };
  }
  const days = runway.runway_days;
  if (days === null || days === undefined) {
    return { text: '—', level: 'unknown', hint: '' };
  }
  const hint = runway.depletion_date
    ? `At an average daily spend of ${formatCurrency(runway.burn_per_day)}, estimated to deplete around ${runway.depletion_date}`
    : '';
  if (days > 365) {
    return { text: 'More than 1 year', level: 'normal', hint };
  }
  const text = days < 1 ? 'Less than 1 day' : `${days < 10 ? days.toFixed(1) : Math.round(days)} days`;
  // 前端只用固定档位上色，真正触发Alert的阈值由后端 RUNWAY_ALERT_DAYS 决定
  const level: RunwayLevel = days <= 3 ? 'danger' : days <= 7 ? 'warning' : 'normal';
  return { text, level, hint };
}

/** HTML 文本转义 */
export function escapeHTML(value: unknown): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };
  return String(value ?? '').replace(/[&<>"']/g, (char) => map[char] ?? char);
}

/** HTML 属性转义；属性一律用双引号包，转义规则与文本相同 */
export function escapeAttr(value: unknown): string {
  return escapeHTML(value);
}

/** 绝对时间，精确到分钟 */
export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '-';
  const date = new Date(dateString);
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** 相对时间；超过一周就退回绝对时间，「8 days ago」这种说法没有信息量 */
export function getRelativeTime(dateString: string | null | undefined, now: Date = new Date()): string {
  if (!dateString) return 'Unknown';
  const date = new Date(dateString);
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes} min ago`;
  if (hours < 24) return `${hours} hr ago`;
  if (days < 7) return `${days} days ago`;
  return formatDate(dateString);
}

/** Balance相对阈值的百分比；不设上限，超过 100% 表示Balance充足 */
export function getBalancePercentage(balance: number, threshold: number): number {
  if (threshold === 0) return 100;
  return (balance / threshold) * 100;
}

/** Balance健康度：进度条与Status色都看它 */
export function getBalanceStatus(balance: number, threshold: number): BalanceStatus {
  const percentage = getBalancePercentage(balance, threshold);
  if (percentage >= 50) return 'normal';
  if (percentage >= 20) return 'warning';
  return 'danger';
}

/** Subscription周期 → 展示名 */
export function cycleLabel(cycle: string | null | undefined): string {
  if (cycle === 'monthly') return 'Monthly';
  if (cycle === 'yearly') return 'Yearly';
  return 'Weekly';
}

/** 续费剩余 days数的紧迫度，空串表示不特殊上色 */
export function renewalUrgency(daysUntilRenewal: number): '' | 'warning' | 'danger' {
  if (daysUntilRenewal <= 7) return 'danger';
  if (daysUntilRenewal <= 14) return 'warning';
  return '';
}
