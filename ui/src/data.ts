/**
 * 数据加载与重绘。
 *
 * 单独成一个模块是为了打破循环依赖：视图切换和各个 manager 改完数据都要重拉，
 * 如果这些函数挂在「应用入口」上，入口就会被所有 manager 反向依赖。
 */

import { byId, toggleDisplay } from './dom.js';
import { getCredits, getFeatures, getSubscriptions, refresh as refreshApi } from './api/endpoints.js';
import { AppState } from './state.js';
import { setLoading } from './ui/loading.js';
import { renderProjects, updateProviderFilter } from './ui/projects.js';
import { renderSubscriptions } from './ui/subscriptions.js';
import { updateStats } from './ui/stats.js';
import { showToast } from './ui/toast.js';

const AUTO_REFRESH_MS = 5 * 60 * 1000;

/** 拉功能开关并按开关隐藏高级入口；拿不到就按核心版降级，页面照常可用 */
export async function loadFeatures(): Promise<void> {
  try {
    const result = await getFeatures();
    AppState.features = { ...AppState.features, ...(result.features || {}) };
  } catch (error) {
    console.warn('Feature flag loading failed; using core defaults:', error);
  }

  if (!AppState.features.subscriptions) {
    toggleDisplay('view-subscriptions-btn', false);
    toggleDisplay('add-subscription-btn', false);
  }
  // Project的增删改依赖数据库动态配置
  toggleDisplay('add-project-btn', AppState.features.dynamic_config);
}

/** 拉Balance与Subscription并重绘当前视图；rebuildFilter=true 时同时重建Provider筛选项（会重置已选Provider） */
export async function fetchAndRender(rebuildFilter = false): Promise<void> {
  const balanceData = await getCredits();
  const subscriptionData = AppState.features.subscriptions
    ? await getSubscriptions()
    : { last_update: null, subscriptions: [], summary: {} };

  AppState.balanceData = balanceData;
  AppState.subscriptionData = subscriptionData;
  AppState.lastUpdate = new Date();

  updateStats(balanceData);
  if (rebuildFilter) {
    updateProviderFilter(balanceData);
  }
  if (AppState.currentView === 'subscriptions') {
    renderSubscriptions(subscriptionData);
  } else {
    renderProjects(balanceData);
  }
}

/** 只重拉Balance并重绘Project区（Project增删改后用） */
export async function reloadProjects(): Promise<void> {
  const balanceData = await getCredits();
  AppState.balanceData = balanceData;
  updateStats(balanceData);
  renderProjects(balanceData);
}

/** 只重拉Subscription并重绘Subscription区（Subscription增删改后用），绕开 ETag 缓存 */
export async function reloadSubscriptions(): Promise<void> {
  const subscriptionData = await getSubscriptions(true);
  AppState.subscriptionData = subscriptionData;
  renderSubscriptions(subscriptionData);
}

export async function loadData(): Promise<void> {
  try {
    setLoading(true);
    await fetchAndRender(true);
  } catch (error) {
    console.error('Failed to load data:', error);
    showToast('Failed to load data; please try again', 'error');
  } finally {
    setLoading(false);
  }
}

/** 顶栏刷新按钮：先让后端真去查一遍Balance，再重拉看板 */
export async function refreshNow(): Promise<void> {
  const btn = byId('refresh-btn');
  try {
    btn?.classList.add('rotating');
    showToast('Refreshing data...', 'info');
    await refreshApi();
    await loadData();
    showToast('Data refreshed', 'success');
  } catch (error) {
    console.error('Refresh failed:', error);
    showToast(error instanceof Error && error.message ? error.message : 'Refresh failed; please try again', 'error');
  } finally {
    btn?.classList.remove('rotating');
  }
}

/** 每 5 分钟重拉一次（不触发后端刷新，也不重置Provider筛选） */
export function startAutoRefresh(): void {
  if (AppState.autoRefreshTimer) return;
  AppState.autoRefreshTimer = setInterval(() => {
    fetchAndRender().catch((error: unknown) => console.error('Auto-refresh failed:', error));
  }, AUTO_REFRESH_MS);
}

export function stopAutoRefresh(): void {
  if (!AppState.autoRefreshTimer) return;
  clearInterval(AppState.autoRefreshTimer);
  AppState.autoRefreshTimer = null;
}
