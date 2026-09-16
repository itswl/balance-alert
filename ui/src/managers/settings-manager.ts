/**
 * 系统设置弹窗：深色模式、自动刷新、API Key。
 *
 * 监听器只在初始化时绑一次。原生 JS 版是每次打开弹窗都 addEventListener，
 * 开五次就有五个监听器，改一下主题会连着跑五遍。
 */

import { getApiKey, setApiKey } from '../api/client.js';
import { byId, inputById, onClick } from '../dom.js';
import { startAutoRefresh, stopAutoRefresh } from '../data.js';
import { AppState } from '../state.js';
import { bindModalClose, openModal } from '../ui/modal.js';
import { showToast } from '../ui/toast.js';
import { toggleTheme } from '../views.js';

const MODAL_ID = 'settings-modal';

/** 每次打开时把控件状态同步成当前真实状态 */
function syncSettingsForm(): void {
  const darkMode = byId<HTMLInputElement>('setting-dark-mode');
  if (darkMode) darkMode.checked = AppState.currentTheme === 'dark';

  const autoRefresh = byId<HTMLInputElement>('setting-auto-refresh');
  if (autoRefresh) autoRefresh.checked = AppState.autoRefreshTimer !== null;

  const apiKeyInput = byId<HTMLInputElement>('setting-api-key');
  if (apiKeyInput) apiKeyInput.value = getApiKey();
}

export function openSettingsModal(): void {
  syncSettingsForm();
  openModal(MODAL_ID);
}

export function bindSettingsManager(): void {
  onClick('settings-btn', openSettingsModal);
  bindModalClose(MODAL_ID, '.js-close-settings-modal');

  byId('setting-dark-mode')?.addEventListener('change', (event) => {
    const wantDark = (event.target as HTMLInputElement).checked;
    if (wantDark !== (AppState.currentTheme === 'dark')) toggleTheme();
  });

  byId('setting-auto-refresh')?.addEventListener('change', (event) => {
    if ((event.target as HTMLInputElement).checked) {
      startAutoRefresh();
      showToast('已启用自动刷新', 'success');
    } else {
      stopAutoRefresh();
      showToast('已禁用自动刷新', 'info');
    }
  });

  byId('setting-api-key')?.addEventListener('change', (event) => {
    setApiKey((event.target as HTMLInputElement).value);
    showToast(getApiKey() ? 'API Key 已保存' : 'API Key 已清除', 'info');
  });

  // 设置里改完 key 后，弹窗里的输入框也同步一下，免得两处显示不一致
  byId('auth-form')?.addEventListener('submit', () => {
    const settingsInput = byId<HTMLInputElement>('setting-api-key');
    if (settingsInput) settingsInput.value = inputById('auth-api-key').value.trim();
  });
}
