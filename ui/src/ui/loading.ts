/**
 * 全屏加载遮罩。
 *
 * 用计数而不是布尔：邮箱扫描会在一次操作里套娃调用 setLoading(true)，
 * 原来内层先结束就把遮罩撤了，外层还在跑却看不出来。
 */

import { byId } from '../dom.js';

let depth = 0;

export function setLoading(show: boolean): void {
  depth = show ? depth + 1 : Math.max(0, depth - 1);
  const overlay = byId('loading-overlay');
  if (!overlay) return;
  overlay.classList.toggle('active', depth > 0);
}

/** 出错兜底：把遮罩强制收掉，避免页面卡在加载态 */
export function resetLoading(): void {
  depth = 0;
  byId('loading-overlay')?.classList.remove('active');
}
