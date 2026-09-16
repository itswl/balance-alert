/** 订阅提醒区：一行一条，右侧是剩余天数。 */

import { requireById } from '../dom.js';
import { cycleLabel, escapeAttr, escapeHTML, formatCurrency, renewalUrgency } from '../format.js';
import type { SubscriptionResult, SubscriptionsResponse } from '../api/types.js';
import { emptyState } from './empty.js';
import { ICON_CHECK, ICON_DELETE, ICON_EDIT, ICON_UNDO } from './icons.js';

export function renderSubscriptionCard(sub: SubscriptionResult): string {
  const daysClass = renewalUrgency(sub.days_until_renewal);
  const amount = Number(sub.amount) || 0;
  const ownerProject = sub.owner_project || '未关联项目';
  const subName = sub.name || '未知订阅';
  const subNameAttr = escapeAttr(subName);

  // 已续费的给「取消标记」，没续费的给「标记已续费」，两者互斥
  const renewalAction = sub.already_renewed
    ? `
                        <button class="action-icon-btn js-clear-renewed" data-name="${subNameAttr}" title="取消续费标记">
                            ${ICON_UNDO}
                        </button>
                        `
    : `
                        <button class="action-icon-btn success js-mark-renewed" data-name="${subNameAttr}" title="标记已续费">
                            ${ICON_CHECK}
                        </button>
                        `;

  return `
            <div class="subscription-card">
                <div class="subscription-info">
                    <h3>${escapeHTML(subName)}</h3>
                    <div class="subscription-meta">
                        <span class="meta-item project-meta">${escapeHTML(ownerProject)}</span>
                        <span class="meta-item"><span class="k">金额</span>${formatCurrency(amount)}</span>
                        <span class="meta-item">${cycleLabel(sub.cycle_type)}</span>
                        ${sub.next_renewal_date ? `<span class="meta-item"><span class="k">下次续费</span>${escapeHTML(sub.next_renewal_date)}</span>` : ''}
                        ${sub.already_renewed ? '<span class="meta-item status-badge success">已续费</span>' : ''}
                    </div>
                </div>
                <div class="subscription-status">
                    <div class="subscription-actions">
                        ${renewalAction}
                        <button class="action-icon-btn js-edit-subscription" data-name="${subNameAttr}" title="编辑">
                            ${ICON_EDIT}
                        </button>
                        <button class="action-icon-btn danger js-delete-subscription" data-name="${subNameAttr}" title="删除">
                            ${ICON_DELETE}
                        </button>
                    </div>
                    <div class="days-remaining ${daysClass}">${sub.days_until_renewal}<span class="unit">天</span></div>
                </div>
            </div>
        `;
}

export function renderSubscriptions(data: SubscriptionsResponse): void {
  const container = requireById('subscriptions-container');
  const subscriptions = data.subscriptions || [];

  container.innerHTML =
    subscriptions.length === 0
      ? emptyState('暂无订阅', '还没有添加任何订阅提醒', 'calendar')
      : subscriptions.map((s) => renderSubscriptionCard(s)).join('');
}
