/**
 * 看板的全局Status。
 *
 * 刻意保持成一个可变对象而不是引入Status库：这个看板的数据流只有
 * 「拉接口 → 写进来 → 重绘」一条，多一层抽象只会让排查变难。
 */

import type { CreditsResponse, Features, SubscriptionsResponse } from './api/types.js';

/** 四个视图；alerts 与 all 共用Project区，只是多一层筛选 */
export type ViewName = 'all' | 'alerts' | 'subscriptions' | 'email';

export const VIEW_NAMES: readonly ViewName[] = ['all', 'alerts', 'subscriptions', 'email'];

export type Theme = 'light' | 'dark';
export type ProjectViewStyle = 'grid' | 'list';

export interface AppStateShape {
  currentTheme: Theme;
  currentView: ViewName;
  projectViewStyle: ProjectViewStyle;
  /** Provider筛选，'all' 表示不筛 */
  currentFilter: string;
  searchQuery: string;
  balanceData: CreditsResponse | null;
  subscriptionData: SubscriptionsResponse | null;
  features: Features;
  lastUpdate: Date | null;
  autoRefreshTimer: ReturnType<typeof setInterval> | null;
}

/** localStorage 在隐私模式下会直接抛异常，读写都不能让它拖垮整个页面 */
export function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* 存不下就算了，只影响下次打开的默认值 */
  }
}

export const AppState: AppStateShape = {
  currentTheme: readStorage('theme') === 'dark' ? 'dark' : 'light',
  currentView: 'all',
  projectViewStyle: readStorage('projectViewStyle') === 'list' ? 'list' : 'grid',
  currentFilter: 'all',
  searchQuery: '',
  balanceData: null,
  subscriptionData: null,
  // 拿不到 /api/features 时按核心版降级：高级入口一律不显示
  features: { subscriptions: false, dynamic_config: false, history: false },
  lastUpdate: null,
  autoRefreshTimer: null,
};

export function isViewName(value: string): value is ViewName {
  return (VIEW_NAMES as readonly string[]).includes(value);
}
