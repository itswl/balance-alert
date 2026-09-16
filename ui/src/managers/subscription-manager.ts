/** 订阅管理：新增 / 编辑 / 删除 / 标记已续费。 */

import { mutate } from '../api/client.js';
import { ENDPOINTS, getSubscriptionsConfig } from '../api/endpoints.js';
import type { CycleType, SubscriptionConfig, SubscriptionPayload, SubscriptionResult } from '../api/types.js';
import { byId, inputById, inputValue, isChecked, onClick, selectById, setChecked, setInputValue } from '../dom.js';
import { reloadSubscriptions } from '../data.js';
import { AppState } from '../state.js';
import { bindModalClose, closeModal, openModal } from '../ui/modal.js';
import { showToast } from '../ui/toast.js';

const MODAL_ID = 'subscription-modal';

/** 可选的「所属项目」取自当前看板里出现过的分组名 */
function populateProjectOptions(selectedProject = ''): void {
  const select = byId<HTMLSelectElement>('sub-owner-project');
  if (!select) return;

  const known = [...new Set((AppState.balanceData?.projects || []).map((p) => p.owner_project).filter(Boolean))] as string[];

  select.innerHTML = '';
  const emptyOption = document.createElement('option');
  emptyOption.value = '';
  emptyOption.textContent = '未关联项目';
  select.appendChild(emptyOption);

  for (const project of known) {
    const option = document.createElement('option');
    option.value = project;
    option.textContent = project;
    option.selected = project === selectedProject;
    select.appendChild(option);
  }

  // 已有订阅关联的项目可能已经不在看板里了，补一个选项免得编辑时被悄悄清空
  if (selectedProject && !known.includes(selectedProject)) {
    const option = document.createElement('option');
    option.value = selectedProject;
    option.textContent = selectedProject;
    option.selected = true;
    select.appendChild(option);
  }
}

/** 续费日的取值范围随周期变：周付 1-7，月付 1-31，年付 MMDD */
function updateRenewalDayInputForCycle(): void {
  const cycle = byId<HTMLSelectElement>('sub-cycle')?.value || 'monthly';
  const input = byId<HTMLInputElement>('sub-renewal-day');
  if (!input) return;

  if (cycle === 'weekly') {
    input.min = '1';
    input.max = '7';
    input.placeholder = '1-7';
  } else if (cycle === 'yearly') {
    input.min = '101';
    input.max = '1231';
    input.placeholder = 'MMDD，例如 315';
  } else {
    input.min = '1';
    input.max = '31';
    input.placeholder = '1-31';
  }
}

type EditableSubscription = SubscriptionConfig | SubscriptionResult;

export function openSubscriptionModal(subscription: EditableSubscription | null = null): void {
  byId<HTMLFormElement>('subscription-form')?.reset();
  populateProjectOptions(subscription?.owner_project ?? '');

  const title = byId('modal-title');
  if (subscription) {
    if (title) title.textContent = '编辑订阅';
    setInputValue('edit-mode', 'true');
    setInputValue('original-name', subscription.name);
    setInputValue('sub-name', subscription.name);
    selectById('sub-owner-project').value = subscription.owner_project ?? '';
    setInputValue('sub-amount', subscription.amount || '');
    selectById('sub-cycle').value = subscription.cycle_type || 'monthly';
    setInputValue('sub-renewal-day', subscription.renewal_day || 1);
    setInputValue('sub-alert-days', 'alert_days_before' in subscription ? subscription.alert_days_before || 7 : 7);
    if (subscription.last_renewed_date) {
      setInputValue('sub-last-renewed', subscription.last_renewed_date);
    }
    setChecked('sub-enabled', 'enabled' in subscription ? subscription.enabled !== false : true);
  } else {
    if (title) title.textContent = '添加订阅';
    setInputValue('edit-mode', 'false');
    setChecked('sub-enabled', true);
  }

  updateRenewalDayInputForCycle();
  openModal(MODAL_ID);
}

function closeSubscriptionModal(): void {
  closeModal(MODAL_ID);
}

async function saveSubscription(event: Event): Promise<void> {
  event.preventDefault();

  const isEdit = inputById('edit-mode').value === 'true';
  const originalName = inputById('original-name').value;

  const data: SubscriptionPayload = {
    name: inputValue('sub-name'),
    owner_project: selectById('sub-owner-project').value || null,
    amount: Number.parseFloat(inputById('sub-amount').value) || 0,
    cycle_type: selectById('sub-cycle').value as CycleType,
    renewal_day: Number.parseInt(inputById('sub-renewal-day').value, 10),
    alert_days_before: Number.parseInt(inputById('sub-alert-days').value, 10),
    enabled: isChecked('sub-enabled'),
  };

  const lastRenewed = inputById('sub-last-renewed').value;
  if (lastRenewed) data.last_renewed_date = lastRenewed;

  let endpoint: string = ENDPOINTS.addSubscription;
  if (isEdit) {
    endpoint = ENDPOINTS.updateSubscription;
    // 名称是定位键：改名时 name 传旧名用于查找，new_name 才是新名字
    if (data.name !== originalName) {
      data.new_name = data.name;
      data.name = originalName;
    }
  }

  const result = await mutate(endpoint, data, { success: isEdit ? '订阅已更新' : '订阅已添加', fail: '保存失败' });
  if (result) {
    closeSubscriptionModal();
    await reloadSubscriptions();
  }
}

/** 看板上的订阅状态不含 alert_days_before，编辑前要拿一次完整配置 */
export async function editSubscription(name: string): Promise<void> {
  try {
    const current = (AppState.subscriptionData?.subscriptions || []).find((s) => s.name === name);
    if (!current) {
      showToast('未找到该订阅', 'error');
      return;
    }
    const result = await getSubscriptionsConfig();
    const full = (result.subscriptions || []).find((s) => s.name === name);
    openSubscriptionModal(full ?? current);
  } catch (error) {
    console.error('加载订阅失败:', error);
    showToast('加载失败', 'error');
  }
}

export async function deleteSubscription(name: string): Promise<void> {
  if (!confirm(`确定要删除订阅"${name}"吗？\n\n此操作不可恢复。`)) return;
  if (await mutate(ENDPOINTS.deleteSubscription, { name }, { success: '订阅已删除', fail: '删除失败' })) {
    await reloadSubscriptions();
  }
}

export async function markSubscriptionRenewed(name: string): Promise<void> {
  if (await mutate(ENDPOINTS.markRenewed, { name }, { success: '已标记为已续费' })) {
    await reloadSubscriptions();
  }
}

export async function clearSubscriptionRenewed(name: string): Promise<void> {
  if (await mutate(ENDPOINTS.clearRenewed, { name }, { success: '已取消续费标记' })) {
    await reloadSubscriptions();
  }
}

export function bindSubscriptionManager(): void {
  onClick('add-subscription-btn', () => openSubscriptionModal());
  bindModalClose(MODAL_ID, '.js-close-subscription-modal');
  document.querySelector('.js-save-subscription')?.addEventListener('click', (e) => void saveSubscription(e));
  byId('subscription-form')?.addEventListener('submit', (e) => void saveSubscription(e));
  byId('sub-cycle')?.addEventListener('change', updateRenewalDayInputForCycle);
}
