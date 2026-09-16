/**
 * 项目管理：新增 / 编辑 / 删除。
 * 开了 ENABLE_DYNAMIC_CONFIG 后，项目清单可以完全在页面上维护。
 */

import { mutate, request } from '../api/client.js';
import { ENDPOINTS, getProviders } from '../api/endpoints.js';
import type { BalanceType, ProjectConfig, ProjectPayload, ProjectsConfigResponse, ProviderOption } from '../api/types.js';
import { byId, fillSelect, inputById, inputValue, isChecked, onClick, selectById, setChecked, setInputValue } from '../dom.js';
import { reloadProjects } from '../data.js';
import { bindModalClose, closeModal, openModal } from '../ui/modal.js';
import { showToast } from '../ui/toast.js';

const MODAL_ID = 'project-modal';

/** 平台清单基本不变，拉一次缓存住 */
let providers: ProviderOption[] = [];

async function loadProviders(): Promise<ProviderOption[]> {
  if (providers.length) return providers;
  try {
    const result = await getProviders();
    providers = result.providers || [];
  } catch (error) {
    console.warn('平台列表加载失败:', error);
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

/** 类型影响阈值的含义：配额型按剩余百分比填，不提示一句用户会填成金额 */
function syncTypeHint(): void {
  const provider = byId<HTMLSelectElement>('project-provider')?.value;
  const known = providers.find((p) => p.value === provider);
  const typeSelect = byId<HTMLSelectElement>('project-type');
  const hint = byId('project-threshold-hint');

  // 用户手动选过类型就不再跟着平台变
  if (known && typeSelect && !typeSelect.dataset['touched']) {
    typeSelect.value = known.default_type;
  }
  if (hint) {
    hint.textContent =
      typeSelect?.value === 'quota'
        ? '配额型平台按剩余百分比填，例如 10 表示不足 10% 时告警'
        : '余额低于此值时告警；留空则不告警';
  }
}

export async function openProjectModal(project: ProjectConfig | null = null): Promise<void> {
  await loadProviders();
  byId<HTMLFormElement>('project-form')?.reset();

  const typeSelect = selectById('project-type');
  typeSelect.dataset['touched'] = project ? 'true' : '';

  const isEdit = Boolean(project);
  const title = byId('project-modal-title');
  if (title) title.textContent = isEdit ? '编辑项目' : '添加项目';
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
  if (keyHint) keyHint.textContent = isEdit ? '留空则保持原密钥不变' : '';

  // 环境变量发现的项目在这里保存会被固化进数据库，得先说清楚
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
    showToast('项目名称不能为空', 'warning');
    return;
  }
  if (!isEdit && !apiKey) {
    showToast('新增项目需要填写密钥', 'warning');
    return;
  }

  const result = await mutate(ENDPOINTS.saveProject, data, {
    success: isEdit ? '项目已更新' : '项目已添加',
    fail: '保存失败',
  });
  if (result) {
    closeProjectModal();
    await reloadProjects();
  }
}

export async function deleteProject(name: string): Promise<void> {
  if (!confirm(`确定要删除项目"${name}"吗？\n\n历史记录会保留，但不再检查余额。`)) return;
  if (await mutate(ENDPOINTS.deleteProject, { name }, { success: '项目已删除', fail: '删除失败' })) {
    await reloadProjects();
  }
}

/** 看板状态里没有密钥、阈值这些配置字段，编辑前要单独拉一次项目配置 */
export async function editProject(name: string): Promise<void> {
  try {
    const result = await request<ProjectsConfigResponse>('/api/config/projects');
    const project = (result.projects || []).find((p) => p.name === name);
    if (!project) {
      showToast('未找到该项目的配置', 'error');
      return;
    }
    await openProjectModal(project);
  } catch (error) {
    console.error('加载项目配置失败:', error);
    showToast('加载失败', 'error');
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
