/** 右上角的短提示。颜色由左侧色条表达，所以文案开头的 emoji 一律去掉。 */

import { byId } from '../dom.js';

export type ToastType = 'info' | 'success' | 'warning' | 'error';

const AUTO_DISMISS_MS = 3000;
const FADE_OUT_MS = 300;

export function showToast(message: unknown, type: ToastType = 'info'): void {
  const container = byId('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const text = document.createElement('div');
  text.style.flex = '1';
  text.textContent = String(message).replace(/^[\p{Extended_Pictographic}️\s]+/u, '');

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.textContent = '×';
  closeBtn.style.cssText =
    'background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 1.25rem; padding: 0; width: 24px; height: 24px;';
  closeBtn.addEventListener('click', () => toast.remove());

  toast.append(text, closeBtn);
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'slideIn 0.3s ease reverse';
    setTimeout(() => toast.remove(), FADE_OUT_MS);
  }, AUTO_DISMISS_MS);
}
