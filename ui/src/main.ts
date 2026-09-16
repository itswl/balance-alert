/**
 * 应用入口：绑定事件、拉功能开关、加载数据、按 hash 进入对应视图。
 *
 * 原生 JS 版把绑定散在六个文件各自的 DOMContentLoaded 里，谁先谁后取决于
 * <script> 的顺序。打成一个包之后统一在这里按顺序装配，出问题好定位。
 */

import './styles/index.css';

import { byId, debounce, onClick, selectById } from './dom.js';
import { loadData, loadFeatures, refreshNow, startAutoRefresh, stopAutoRefresh } from './data.js';
import { bindEmailManager, deleteEmail, editEmail } from './managers/email-manager.js';
import { bindProjectManager, deleteProject, editProject } from './managers/project-manager.js';
import { bindSettingsManager } from './managers/settings-manager.js';
import {
  bindSubscriptionManager,
  clearSubscriptionRenewed,
  deleteSubscription,
  editSubscription,
  markSubscriptionRenewed,
} from './managers/subscription-manager.js';
import { bindTrendManager, showProjectTrend } from './managers/trend-manager.js';
import { AppState, isViewName, writeStorage, type ProjectViewStyle } from './state.js';
import { renderProjects } from './ui/projects.js';
import { showToast } from './ui/toast.js';
import { initTheme, switchView, toggleTheme } from './views.js';

const SEARCH_DEBOUNCE_MS = 300;

/**
 * 卡片是 innerHTML 整片重绘的，逐个绑事件会在重绘时全部失效，
 * 所以统一用事件委托：按 data-* 找到目标，交给对应的 manager。
 */
function bindCardActions(): void {
  document.addEventListener('click', (event) => {
    const target = event.target as HTMLElement | null;
    if (!target) return;

    const handlers: Array<[string, (el: HTMLElement) => void]> = [
      ['.js-edit-project', (el) => void editProject(el.dataset['project'] ?? '')],
      ['.js-delete-project', (el) => void deleteProject(el.dataset['project'] ?? '')],
      ['.js-show-trend', (el) => void showProjectTrend(el.dataset['project'] ?? '', el.dataset['provider'] ?? '')],
      ['.js-edit-email', (el) => editEmail(el.dataset['name'] ?? '')],
      ['.js-delete-email', (el) => void deleteEmail(el.dataset['name'] ?? '')],
      ['.js-mark-renewed', (el) => void markSubscriptionRenewed(el.dataset['name'] ?? '')],
      ['.js-clear-renewed', (el) => void clearSubscriptionRenewed(el.dataset['name'] ?? '')],
      ['.js-edit-subscription', (el) => void editSubscription(el.dataset['name'] ?? '')],
      ['.js-delete-subscription', (el) => void deleteSubscription(el.dataset['name'] ?? '')],
    ];

    for (const [selector, handler] of handlers) {
      const el = target.closest<HTMLElement>(selector);
      if (el) {
        handler(el);
        return;
      }
    }
  });
}

function setProjectViewStyle(style: ProjectViewStyle): void {
  AppState.projectViewStyle = style;
  writeStorage('projectViewStyle', style);
  if (AppState.balanceData) renderProjects(AppState.balanceData);
}

function bindEvents(): void {
  onClick('theme-toggle', toggleTheme);
  onClick('refresh-btn', () => void refreshNow());

  onClick('view-all-btn', () => switchView('all'));
  onClick('view-alerts-btn', () => switchView('alerts'));
  onClick('view-subscriptions-btn', () => {
    if (!AppState.features.subscriptions) {
      showToast('订阅功能未启用', 'info');
      return;
    }
    switchView('subscriptions');
  });
  onClick('view-email-btn', () => switchView('email'));

  onClick('view-grid-btn', () => setProjectViewStyle('grid'));
  onClick('view-list-btn', () => setProjectViewStyle('list'));

  byId('search-input')?.addEventListener(
    'input',
    debounce((event: Event) => {
      AppState.searchQuery = (event.target as HTMLInputElement).value;
      if (AppState.balanceData) renderProjects(AppState.balanceData);
    }, SEARCH_DEBOUNCE_MS) as EventListener,
  );

  byId('provider-filter')?.addEventListener('change', () => {
    AppState.currentFilter = selectById('provider-filter').value;
    if (AppState.balanceData) renderProjects(AppState.balanceData);
  });

  bindCardActions();
  bindProjectManager();
  bindSubscriptionManager();
  bindEmailManager();
  bindSettingsManager();
  bindTrendManager();

  window.addEventListener('beforeunload', stopAutoRefresh);
}

async function init(): Promise<void> {
  initTheme();
  bindEvents();

  await loadFeatures();
  await loadData();

  // 地址栏带 #alerts / #subscriptions / #email 时直接进对应视图
  const initialView = window.location.hash.slice(1);
  if (isViewName(initialView) && initialView !== 'all') {
    switchView(initialView);
  }

  startAutoRefresh();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => void init());
} else {
  void init();
}
