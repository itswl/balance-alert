/** 模态框：开、关、点遮罩关闭。五个弹窗的开关逻辑完全一样，没必要各写一遍。 */

import { byId, onClickAll } from '../dom.js';

export function openModal(id: string): void {
  byId(id)?.classList.add('active');
}

export function closeModal(id: string): void {
  byId(id)?.classList.remove('active');
}

export function isModalOpen(id: string): boolean {
  return byId(id)?.classList.contains('active') ?? false;
}

/**
 * 绑定一个弹窗的关闭方式：关闭按钮 + 点击遮罩。
 * 点击判定用 `event.target === modal`，点在内容区上不会误关。
 */
export function bindModalClose(id: string, closeButtonSelector: string, onClose?: () => void): void {
  const close = (): void => {
    closeModal(id);
    onClose?.();
  };

  onClickAll(closeButtonSelector, close);

  byId(id)?.addEventListener('click', (event) => {
    if ((event.target as HTMLElement | null)?.id === id) close();
  });
}
