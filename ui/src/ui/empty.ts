/** 空Status。四个视图都要用，文案不同图标不同，其余结构一样。 */

import { escapeHTML } from '../format.js';
import { ICON_CALENDAR, ICON_INFO_CIRCLE, ICON_MAIL } from './icons.js';

export type EmptyIcon = 'info' | 'calendar' | 'mail';

const ICONS: Record<EmptyIcon, string> = {
  info: ICON_INFO_CIRCLE,
  calendar: ICON_CALENDAR,
  mail: ICON_MAIL,
};

export function emptyState(title: string, text: string, icon: EmptyIcon = 'info', compact = false): string {
  return `
            <div class="empty-state${compact ? ' compact' : ''}">
                ${ICONS[icon]}
                <h3>${escapeHTML(title)}</h3>
                <p>${escapeHTML(text)}</p>
            </div>
        `;
}
