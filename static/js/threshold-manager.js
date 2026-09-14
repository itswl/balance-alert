// ==================== 项目阈值管理功能 ====================

// 打开编辑阈值模态框
function editProjectThreshold(projectName, currentThreshold) {
    const modal = document.getElementById('threshold-modal');
    const title = document.getElementById('threshold-modal-title');

    // 设置项目名称和当前阈值
    document.getElementById('threshold-project-name').value = projectName;
    document.getElementById('threshold-value').value = currentThreshold;
    title.textContent = `编辑告警阈值 - ${projectName}`;

    modal.classList.add('active');
}

// 关闭阈值模态框
function closeThresholdModal() {
    const modal = document.getElementById('threshold-modal');
    modal.classList.remove('active');
}

// 保存阈值
async function saveThreshold(event) {
    event.preventDefault();

    const projectName = document.getElementById('threshold-project-name').value;
    const newThreshold = parseFloat(document.getElementById('threshold-value').value);

    if (isNaN(newThreshold) || newThreshold < 0) {
        UI.showToast('❌ 请输入有效的阈值（大于等于0）', 'error');
        return;
    }

    const result = await API.mutate(
        '/api/config/threshold',
        { project_name: projectName, new_threshold: newThreshold },
        { success: '阈值已更新', fail: '保存失败' }
    );
    if (result) {
        closeThresholdModal();
        await App.reloadProjects();
    }
}

// 绑定事件
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.js-close-threshold-modal').forEach((button) => {
        button.addEventListener('click', closeThresholdModal);
    });

    const saveBtn = document.querySelector('.js-save-threshold');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveThreshold);
    }

    const form = document.getElementById('threshold-form');
    if (form) {
        form.addEventListener('submit', saveThreshold);
    }

    // 模态框点击外部关闭
    const modal = document.getElementById('threshold-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target.id === 'threshold-modal') {
                closeThresholdModal();
            }
        });
    }
});
