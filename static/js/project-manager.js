// ==================== 项目管理：新增 / 编辑 / 删除 ====================
// 开了 ENABLE_DYNAMIC_CONFIG 后，项目清单可以完全在页面上维护，不需要 config.json

const ProjectManager = {
    providers: [],

    async loadProviders() {
        if (this.providers.length) return this.providers;
        try {
            const result = await API.request('/api/providers');
            this.providers = result.providers || [];
        } catch (error) {
            console.warn('平台列表加载失败:', error);
        }
        return this.providers;
    },

    fillProviderOptions(selected = '') {
        const select = document.getElementById('project-provider');
        if (!select) return;
        select.innerHTML = '';
        this.providers.forEach(({ value, label }) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = `${label}（${value}）`;
            option.selected = value === selected;
            select.appendChild(option);
        });
    },

    // 类型影响阈值的含义：配额型按百分比填
    syncTypeHint() {
        const provider = document.getElementById('project-provider')?.value;
        const known = this.providers.find(p => p.value === provider);
        const typeSelect = document.getElementById('project-type');
        const hint = document.getElementById('project-threshold-hint');
        if (known && typeSelect && !typeSelect.dataset.touched) {
            typeSelect.value = known.default_type;
        }
        if (hint) {
            hint.textContent = typeSelect?.value === 'quota'
                ? '配额型平台按剩余百分比填，例如 10 表示不足 10% 时告警'
                : '余额低于此值时告警；留空则不告警';
        }
    },
};

async function openProjectModal(project = null) {
    await ProjectManager.loadProviders();
    const form = document.getElementById('project-form');
    form.reset();
    document.getElementById('project-type').dataset.touched = project ? 'true' : '';

    const isEdit = Boolean(project);
    document.getElementById('project-modal-title').textContent = isEdit ? '编辑项目' : '添加项目';
    document.getElementById('project-edit-mode').value = String(isEdit);

    const nameInput = document.getElementById('project-name');
    nameInput.value = project?.name || '';
    nameInput.readOnly = isEdit;          // 名称是唯一键，改名请删掉重建
    ProjectManager.fillProviderOptions(project?.provider || '');
    document.getElementById('project-provider').disabled = isEdit;
    document.getElementById('project-threshold').value = project?.threshold ?? '';
    document.getElementById('project-type').value = project?.type || '';
    document.getElementById('project-owner').value = project?.owner_project || '';
    document.getElementById('project-enabled').checked = project ? project.enabled !== false : true;
    document.getElementById('project-api-key').value = '';
    document.getElementById('project-api-key-hint').textContent = isEdit ? '留空则保持原密钥不变' : '';

    const envNote = document.getElementById('project-env-note');
    envNote.style.display = project?.from_env ? 'block' : 'none';

    ProjectManager.syncTypeHint();
    document.getElementById('project-modal').classList.add('active');
}

function closeProjectModal() {
    document.getElementById('project-modal').classList.remove('active');
}

async function saveProject(event) {
    event.preventDefault();

    const isEdit = document.getElementById('project-edit-mode').value === 'true';
    const threshold = document.getElementById('project-threshold').value;
    const data = {
        name: document.getElementById('project-name').value.trim(),
        provider: document.getElementById('project-provider').value,
        type: document.getElementById('project-type').value || null,
        owner_project: document.getElementById('project-owner').value.trim() || null,
        enabled: document.getElementById('project-enabled').checked,
    };
    if (threshold !== '') data.threshold = parseFloat(threshold);
    const apiKey = document.getElementById('project-api-key').value.trim();
    if (apiKey) data.api_key = apiKey;

    if (!data.name) {
        UI.showToast('项目名称不能为空', 'warning');
        return;
    }
    if (!isEdit && !apiKey) {
        UI.showToast('新增项目需要填写密钥', 'warning');
        return;
    }

    const result = await API.mutate('/api/config/project', data, {
        success: isEdit ? '项目已更新' : '项目已添加',
        fail: '保存失败',
    });
    if (result) {
        closeProjectModal();
        await App.reloadProjects();
    }
}

async function deleteProject(name) {
    if (!confirm(`确定要删除项目"${name}"吗？\n\n历史记录会保留，但不再检查余额。`)) return;
    if (await API.mutate('/api/config/project/delete', { name }, { success: '项目已删除', fail: '删除失败' })) {
        await App.reloadProjects();
    }
}

// 从看板数据里取出这个项目的完整配置再打开弹窗（看板状态不含密钥等字段）
async function editProject(name) {
    try {
        const result = await API.request('/api/config/projects');
        const project = (result.projects || []).find(p => p.name === name);
        if (!project) {
            UI.showToast('未找到该项目的配置', 'error');
            return;
        }
        await openProjectModal(project);
    } catch (error) {
        console.error('加载项目配置失败:', error);
        UI.showToast('加载失败', 'error');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('add-project-btn')?.addEventListener('click', () => openProjectModal());
    document.querySelectorAll('.js-close-project-modal').forEach(b => b.addEventListener('click', closeProjectModal));
    document.querySelector('.js-save-project')?.addEventListener('click', saveProject);
    document.getElementById('project-form')?.addEventListener('submit', saveProject);
    document.getElementById('project-provider')?.addEventListener('change', () => ProjectManager.syncTypeHint());
    document.getElementById('project-type')?.addEventListener('change', (e) => {
        e.target.dataset.touched = 'true';
        ProjectManager.syncTypeHint();
    });
    document.getElementById('project-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'project-modal') closeProjectModal();
    });
});
