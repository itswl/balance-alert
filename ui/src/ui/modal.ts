/* Implementation note. */

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
 * Implementation note.
 * Implementation note.
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
