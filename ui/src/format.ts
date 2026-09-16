/**
 * 纯格式化与状态判定。
 *
 * 这个模块不碰 DOM、不碰 fetch，是冒烟测试唯一需要直接调用的地方 ——
 * 看板上所有「这个数字该显示成什么」的判断都收在这里，改了就一定有测试兜底。
 */

import type { BalanceType, Runway } from './api/types.js';

/** 跑道的展示档位，与 CSS 里的 .runway-* 一一对应 */
export type RunwayLevel = 'danger' | 'warning' | 'normal' | 'unknown';

/** 余额相对阈值的健康度，与 CSS 里进度条的 .normal/.warning/.danger 对应 */
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

/** 金额：两位小数，解析不出数字时给 '-' 而不是 0 */
export function formatCurrency(value: unknown): string {
  const num = toNumber(value);
  if (Number.isNaN(num)) return '-';
  return num.toFixed(2);
}

/** 千分位整数 */
export function formatNumber(num: number): string {
  return new Intl.NumberFormat('zh-CN').format(num);
}

/** 余额类型 → 展示名 */
export function typeLabel(type: string | null | undefined): string {
  const labels: Record<string, string> = { credits: 'Credits', balance: '余额', quota: '配额' };
  return (type ? labels[type] : undefined) ?? (type || '余额');
}

/**
 * 按类型格式化余额，返回的是 HTML 片段：配额型带一个 `<span class="unit">%</span>`。
 * 这里不转义，因为输入已经被 parseFloat 过滤成纯数字。
 */
export function formatBalance(value: unknown, type: BalanceType | string | null | undefined): string {
  const num = toNumber(value);
  if (Number.isNaN(num)) return '-';
  if (type === 'quota') {
    return `${num.toFixed(1)}<span class="unit">%</span>`;
  }
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/**
 * 跑道：按当前消耗速率还能用多久。
 * 数据不足、没有消耗这两种情况都要说得清楚，绝不能显示成 0 —— 那会被读成「马上耗尽」。
 */
export function formatRunway(runway: Runway | null | undefined): RunwayDisplay {
  if (!runway || runway.confidence === 'none') {
    return { text: '数据积累中', level: 'unknown', hint: '攒够几小时的余额历史后给出估算' };
  }
  if (!runway.burn_per_day) {
    return { text: '无消耗', level: 'normal', hint: `最近 ${runway.window_days} 天余额没有下降` };
  }
  const days = runway.runway_days;
  if (days === null || days === undefined) {
    return { text: '—', level: 'unknown', hint: '' };
  }
  const hint = runway.depletion_date
    ? `按日均 ${formatCurrency(runway.burn_per_day)} 估算，约 ${runway.depletion_date} 耗尽`
    : '';
  if (days > 365) {
    return { text: '超过 1 年', level: 'normal', hint };
  }
  const text = days < 1 ? '不足 1 天' : `${days < 10 ? days.toFixed(1) : Math.round(days)} 天`;
  // 前端只用固定档位上色，真正触发告警的阈值由后端 RUNWAY_ALERT_DAYS 决定
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
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** 相对时间；超过一周就退回绝对时间，「8天前」这种说法没有信息量 */
export function getRelativeTime(dateString: string | null | undefined, now: Date = new Date()): string {
  if (!dateString) return '未知';
  const date = new Date(dateString);
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  if (hours < 24) return `${hours}小时前`;
  if (days < 7) return `${days}天前`;
  return formatDate(dateString);
}

/** 余额相对阈值的百分比；不设上限，超过 100% 表示余额充足 */
export function getBalancePercentage(balance: number, threshold: number): number {
  if (threshold === 0) return 100;
  return (balance / threshold) * 100;
}

/** 余额健康度：进度条与状态色都看它 */
export function getBalanceStatus(balance: number, threshold: number): BalanceStatus {
  const percentage = getBalancePercentage(balance, threshold);
  if (percentage >= 50) return 'normal';
  if (percentage >= 20) return 'warning';
  return 'danger';
}

/** 订阅周期 → 展示名 */
export function cycleLabel(cycle: string | null | undefined): string {
  if (cycle === 'monthly') return '月付';
  if (cycle === 'yearly') return '年付';
  return '周付';
}

/** 续费剩余天数的紧迫度，空串表示不特殊上色 */
export function renewalUrgency(daysUntilRenewal: number): '' | 'warning' | 'danger' {
  if (daysUntilRenewal <= 7) return 'danger';
  if (daysUntilRenewal <= 14) return 'warning';
  return '';
}
