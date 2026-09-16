/** 项目余额区：卡片渲染、搜索 / 平台 / 视图三重筛选、平台下拉框。 */

import { byId, requireById, selectById } from '../dom.js';
import {
  escapeAttr,
  escapeHTML,
  formatBalance,
  formatRunway,
  getBalancePercentage,
  getBalanceStatus,
  typeLabel,
} from '../format.js';
import { AppState } from '../state.js';
import type { CheckResult, CreditsResponse, Features } from '../api/types.js';
import { emptyState } from './empty.js';
import { ICON_ARROW_RIGHT, ICON_DELETE, ICON_EDIT } from './icons.js';

/**
 * 一张项目卡片。
 *
 * features 作为参数传进来而不是直接读 AppState：这样这个函数是纯的，
 * 冒烟测试可以直接喂数据比对输出。
 */
export function renderProjectCard(project: CheckResult, features: Features): string {
  const balance = project.credits || 0;
  const threshold = project.threshold || 0;
  const status = getBalanceStatus(balance, threshold);
  const percentage = getBalancePercentage(balance, threshold);
  const projectStatus = project.need_alarm ? 'alert' : 'normal';
  const ownerProject = project.owner_project || '未关联项目';
  const projectName = project.project || '未知项目';
  const provider = project.provider || 'unknown';
  const type = project.type || 'balance';
  const label = typeLabel(type);
  const runway = formatRunway(project.runway);
  const burn = project.runway ? project.runway.burn_per_day : null;

  const projectNameAttr = escapeAttr(projectName);
  const providerAttr = escapeAttr(provider);

  // 项目的增删改依赖 ENABLE_DYNAMIC_CONFIG，关掉时连按钮都不该出现
  const optionalActions = features.dynamic_config
    ? `
                        <button class="action-icon-btn js-edit-project" data-project="${projectNameAttr}" title="编辑项目">
                            ${ICON_EDIT}
                        </button>
                        <button class="action-icon-btn danger js-delete-project" data-project="${projectNameAttr}" title="删除项目">
                            ${ICON_DELETE}
                        </button>`
    : '';

  const trendAction = features.history
    ? `<div class="project-actions">
                    <button class="btn-link js-show-trend" data-project="${projectNameAttr}" data-provider="${providerAttr}">
                        查看趋势
                        ${ICON_ARROW_RIGHT}
                    </button>
                </div>`
    : '';

  return `
            <div class="project-card" data-provider="${providerAttr}" data-status="${projectStatus}">
                <div class="project-header">
                    <div class="project-info">
                        <h3>${escapeHTML(projectName)}</h3>
                        <div class="project-meta-row">
                            <span class="project-provider">${escapeHTML(provider)}</span>
                            <span class="owner-project-badge">${escapeHTML(ownerProject)}</span>
                            <span class="owner-project-badge">${escapeHTML(label)}</span>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        ${optionalActions}
                        <div class="project-status ${projectStatus}"></div>
                    </div>
                </div>
                <div class="project-balance">
                    <div class="balance-label">${type === 'quota' ? '剩余配额' : `当前${label}`}</div>
                    <div class="balance-value">${formatBalance(balance, type)}</div>
                    <div class="balance-progress">
                        <div class="balance-progress-bar ${status}" style="width: ${Math.min(100, percentage)}%"></div>
                    </div>
                </div>
                <div class="project-details">
                    <div class="detail-item">
                        <span class="detail-label">告警阈值</span>
                        <span class="detail-value">${formatBalance(threshold, type)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">日均消耗</span>
                        <span class="detail-value">${burn === null || burn === undefined ? '—' : formatBalance(burn, type)}</span>
                    </div>
                    <div class="detail-item" title="${escapeAttr(runway.hint)}">
                        <span class="detail-label">还可用</span>
                        <span class="detail-value runway-${runway.level}">${escapeHTML(runway.text)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">状态</span>
                        <span class="detail-value status-text ${projectStatus}">${projectStatus === 'normal' ? '正常' : '告警'}</span>
                    </div>
                </div>
                ${trendAction}
            </div>
        `;
}

/** 搜索词 / 平台 / 当前视图三重筛选，顺序与原版一致 */
export function filterProjects(
  projects: CheckResult[],
  { search, provider, alertsOnly }: { search: string; provider: string; alertsOnly: boolean },
): CheckResult[] {
  let result = projects;
  if (search) {
    const query = search.toLowerCase();
    result = result.filter(
      (p) => (p.project || '').toLowerCase().includes(query) || (p.provider || '').toLowerCase().includes(query),
    );
  }
  if (provider !== 'all') {
    result = result.filter((p) => p.provider === provider);
  }
  if (alertsOnly) {
    result = result.filter((p) => p.need_alarm);
  }
  return result;
}

export function renderProjects(data: CreditsResponse): void {
  const container = requireById('projects-container');

  const isList = AppState.projectViewStyle === 'list';
  container.className = isList ? 'projects-list' : 'projects-grid';
  byId('view-list-btn')?.classList.toggle('active', isList);
  byId('view-grid-btn')?.classList.toggle('active', !isList);

  const filtered = filterProjects(data.projects || [], {
    search: AppState.searchQuery,
    provider: AppState.currentFilter,
    alertsOnly: AppState.currentView === 'alerts',
  });

  container.innerHTML =
    filtered.length === 0
      ? emptyState('暂无数据', '没有找到符合条件的项目')
      : filtered.map((p) => renderProjectCard(p, AppState.features)).join('');
}

/** 重建平台下拉框；会把已选平台重置成「全部平台」，所以只在首次加载时调 */
export function updateProviderFilter(data: CreditsResponse): void {
  const select = selectById('provider-filter');
  const providers = [...new Set((data.projects || []).map((p) => p.provider))];

  select.innerHTML = '';
  const allOption = document.createElement('option');
  allOption.value = 'all';
  allOption.textContent = '全部平台';
  select.appendChild(allOption);

  for (const provider of providers) {
    const option = document.createElement('option');
    option.value = provider;
    option.textContent = provider;
    select.appendChild(option);
  }
}
