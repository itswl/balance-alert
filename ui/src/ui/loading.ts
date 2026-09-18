/**
 * Implementation note.
 *
 * Implementation note.
 * Implementation note.
 */

import { byId } from '../dom.js';

let depth = 0;

export function setLoading(show: boolean): void {
  depth = show ? depth + 1 : Math.max(0, depth - 1);
  const overlay = byId('loading-overlay');
  if (!overlay) return;
  overlay.classList.toggle('active', depth > 0);
}

/* Implementation note. */
export function resetLoading(): void {
  depth = 0;
  byId('loading-overlay')?.classList.remove('active');
}
