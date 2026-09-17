/**
 * Project管理：新增 / Edit / Delete。
 * 开了 ENABLE_DYNAMIC_CONFIG 后，Project清单可以完全在页面上维护。
 */

import { mutate, request } from '../api/client.js';
import { ENDPOINTS, getProviders } from '../api/endpoints.js';
import type { BalanceType, ProjectConfig, ProjectPayload, ProjectsConfigResponse, ProviderOption } from '../api/types.js';
import { byId, fillSelect, inputById, inputValue, isChecked, onClick, selectById, setChecked, setInputValue } from '../dom.js';
import { reloadProjects } from '../data.js';
import { bindModalClose, closeModal, openModal } from '../ui/modal.js';
import { showToast } from '../ui/toast.js';

const MODAL_ID = 'project-modal';

/** Provider清单基本不变，拉一次缓存住 */
let providers: ProviderOption[] = [];

async function loadProviders(): Promise<ProviderOption[]> {
  if (providers.length) return providers;
  try {
    const result = await getProviders();
    providers = result.providers || [];
  } catch (error) {
    console.warn('Failed to load provider list:', error);
  }
  return providers;
}

function fillProviderOptions(selected = ''): void {
  const select = byId<HTMLSelectElement>('project-provider');
  if (!select) return;
  fillSelect(
    select,
    providers.map(({ value, label }) => ({ value, label: `${label}（${value}）` })),
    selected,
  );
}

/** 类型影响阈值的含义：Quota型按剩余百分比填，不提示一句用户会填成Amount */
function syncTypeHint(): void {
  const provider = byId<HTMLSelectElement>('project-provider')?.value;
  const known = providers.find((p) => p.value === provider);
  const typeSelect = byId<HTMLSelectElement>('project-type');
  const hint = byId('project-threshold-hint');

  // 用户手动选过类型就不再跟着Provider变
  if (known && typeSelect && !typeSelect.dataset['touched']) {
    typeSelect.value = known.default_type;
  }
  if (hint) {
    hint.textContent =
      typeSelect?.value === 'quota'
        ? 'Enter a remaining percentage for quota providers; for example, 10 alerts below 10%.'
        : 'Alert when the balance is below this value; leave empty to disable alerts.';
  }
}

export async function openProjectModal(project: ProjectConfig | null = null): Promise<void> {
  await loadProviders();
  byId<HTMLFormElement>('project-form')?.reset();

  const typeSelect = selectById('project-type');
  typeSelect.dataset['touched'] = project ? 'true' : '';

  const isEdit = Boolean(project);
  const title = byId('project-modal-title');
  if (title) title.textContent = isEdit ? 'Edit project' : 'Add project';
  setInputValue('project-edit-mode', String(isEdit));

  const nameInput = inputById('project-name');
  nameInput.value = project?.name ?? '';
  nameInput.readOnly = isEdit; // 名称是唯一键，改名请删掉重建
  fillProviderOptions(project?.provider ?? '');
  selectById('project-provider').disabled = isEdit;
  setInputValue('project-threshold', project?.threshold ?? '');
  typeSelect.value = project?.type ?? '';
  setInputValue('project-owner', project?.owner_project ?? '');
  setChecked('project-enabled', project ? project.enabled !== false : true);
  setInputValue('project-api-key', '');

  const keyHint = byId('project-api-key-hint');
  if (keyHint) keyHint.textContent = isEdit ? 'Leave empty to keep the existing API key' : '';

  // 环境变量发现的Project在这里Save会被固化进数据库，得先说清楚
  const envNote = byId('project-env-note');
  if (envNote) envNote.style.display = project?.from_env ? 'block' : 'none';

  syncTypeHint();
  openModal(MODAL_ID);
}

function closeProjectModal(): void {
  closeModal(MODAL_ID);
}

async function saveProject(event: Event): Promise<void> {
  event.preventDefault();

  const isEdit = inputById('project-edit-mode').value === 'true';
  const threshold = inputById('project-threshold').value;
  const typeValue = selectById('project-type').value;

  const data: ProjectPayload = {
    name: inputValue('project-name'),
    provider: selectById('project-provider').value,
    type: (typeValue || null) as BalanceType | null,
    owner_project: inputValue('project-owner') || null,
    enabled: isChecked('project-enabled'),
  };
  if (threshold !== '') data.threshold = Number.parseFloat(threshold);
  const apiKey = inputValue('project-api-key');
  if (apiKey) data.api_key = apiKey;

  if (!data.name) {
    showToast('Project name is required', 'warning');
    return;
  }
  if (!isEdit && !apiKey) {
    showToast('An API key is required for a new project', 'warning');
    return;
  }

  const result = await mutate(ENDPOINTS.saveProject, data, {
    success: isEdit ? 'Project updated' : 'Project added',
    fail: 'Save failed',
  });
  if (result) {
    closeProjectModal();
    await reloadProjects();
  }
}

export async function deleteProject(name: string): Promise<void> {
  if (!confirm(`Delete project "${name}"?\n\nHistory is retained, but the balance will no longer be checked.`)) return;
  if (await mutate(ENDPOINTS.deleteProject, { name }, { success: 'Project deleted', fail: 'Delete failed' })) {
    await reloadProjects();
  }
}

/** 看板Status里没有密钥、阈值这些配置字段，Edit前要单独拉一次Project配置 */
export async function editProject(name: string): Promise<void> {
  try {
    const result = await request<ProjectsConfigResponse>('/api/config/projects');
    const project = (result.projects || []).find((p) => p.name === name);
    if (!project) {
      showToast('Project configuration not found', 'error');
      return;
    }
    await openProjectModal(project);
  } catch (error) {
    console.error('Failed to load project configuration:', error);
    showToast('Load failed', 'error');
  }
}

export function bindProjectManager(): void {
  onClick('add-project-btn', () => void openProjectModal());
  bindModalClose(MODAL_ID, '.js-close-project-modal');
  document.querySelector('.js-save-project')?.addEventListener('click', (e) => void saveProject(e));
  byId('project-form')?.addEventListener('submit', (e) => void saveProject(e));
  byId('project-provider')?.addEventListener('change', syncTypeHint);
  byId('project-type')?.addEventListener('change', (e) => {
    (e.target as HTMLSelectElement).dataset['touched'] = 'true';
    syncTypeHint();
  });
}
