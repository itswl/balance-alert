/** 顶部概览数字：总数、正常、告警、最短跑道、最后更新。 */

import { byId, setText } from '../dom.js';
import { formatRunway, getRelativeTime } from '../format.js';
import type { CheckResult, CreditsResponse } from '../api/types.js';

/** 所有账户里最先见底的那个；没有可估算的就返回 null */
export function shortestRunway(projects: CheckResult[]): CheckResult | null {
  const ranked = projects
    .filter((p) => p.success && p.runway && p.runway.runway_days !== null && p.runway.runway_days !== undefined)
    .sort((a, b) => (a.runway?.runway_days ?? 0) - (b.runway?.runway_days ?? 0));
  return ranked[0] ?? null;
}

export function updateStats(data: CreditsResponse): void {
  const projects = data.projects || [];

  setText('total-projects', String(projects.length));
  setText('normal-projects', String(projects.filter((p) => !p.need_alarm && p.success).length));
  setText('alert-projects', String(projects.filter((p) => p.need_alarm).length));
  setText('last-update', getRelativeTime(data.last_update));
  updateFailedHint(projects);
  updateRunwayStat(projects);
}

/**
 * 查询失败的项目既不算正常也不算告警，总数对不上时得有个说法。
 * 挂在告警卡片的标签上，不用为此多占一格。
 */
export function updateFailedHint(projects: CheckResult[]): void {
  const label = byId('alert-projects-label');
  if (!label) return;

  const failed = projects.filter((p) => !p.success);
  if (failed.length === 0) {
    label.textContent = '告警项目';
    label.title = '';
    return;
  }
  label.textContent = `告警项目 · ${failed.length} 个查不到`;
  label.title = `查不到余额：${failed.map((p) => p.project).join('、')}`;
}

export function updateRunwayStat(projects: CheckResult[]): void {
  const value = byId('shortest-runway');
  const label = byId('shortest-runway-label');
  if (!value || !label) return;

  const first = shortestRunway(projects);
  if (!first) {
    value.textContent = '—';
    value.className = 'stat-value';
    label.textContent = '最短跑道';
    label.title = '开启数据库后，攒够余额历史即可估算';
    return;
  }

  const runway = formatRunway(first.runway);
  value.textContent = runway.text;
  value.className = `stat-value runway-${runway.level}`;
  label.textContent = `最短跑道 · ${first.project}`;
  label.title = runway.hint;
}
