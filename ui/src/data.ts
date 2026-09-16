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
    console.warn('功能开关加载失败，使用核心版默认设置:', error);
  }

  if (!AppState.features.subscriptions) {
    toggleDisplay('view-subscriptions-btn', false);
    toggleDisplay('add-subscription-btn', false);
  }
  // 项目的增删改依赖数据库动态配置
  toggleDisplay('add-project-btn', AppState.features.dynamic_config);
}

/** 拉余额与订阅并重绘当前视图；rebuildFilter=true 时同时重建平台筛选项（会重置已选平台） */
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

/** 只重拉余额并重绘项目区（项目增删改后用） */
export async function reloadProjects(): Promise<void> {
  const balanceData = await getCredits();
  AppState.balanceData = balanceData;
  updateStats(balanceData);
  renderProjects(balanceData);
}

/** 只重拉订阅并重绘订阅区（订阅增删改后用），绕开 ETag 缓存 */
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
    console.error('加载数据失败:', error);
    showToast('加载数据失败，请稍后重试', 'error');
  } finally {
    setLoading(false);
  }
}

/** 顶栏刷新按钮：先让后端真去查一遍余额，再重拉看板 */
export async function refreshNow(): Promise<void> {
  const btn = byId('refresh-btn');
  try {
    btn?.classList.add('rotating');
    showToast('正在刷新数据...', 'info');
    await refreshApi();
    await loadData();
    showToast('数据已刷新', 'success');
  } catch (error) {
    console.error('刷新失败:', error);
    showToast(error instanceof Error && error.message ? error.message : '刷新失败，请稍后重试', 'error');
  } finally {
    btn?.classList.remove('rotating');
  }
}

/** 每 5 分钟重拉一次（不触发后端刷新，也不重置平台筛选） */
export function startAutoRefresh(): void {
  if (AppState.autoRefreshTimer) return;
  AppState.autoRefreshTimer = setInterval(() => {
    fetchAndRender().catch((error: unknown) => console.error('自动刷新失败:', error));
  }, AUTO_REFRESH_MS);
}

export function stopAutoRefresh(): void {
  if (!AppState.autoRefreshTimer) return;
  clearInterval(AppState.autoRefreshTimer);
  AppState.autoRefreshTimer = null;
}
