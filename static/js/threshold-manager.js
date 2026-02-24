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

    try {
        UI.setLoading(true);

        const response = await fetch('/api/config/threshold', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                project_name: projectName,
                new_threshold: newThreshold
            })
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            UI.showToast('✅ 阈值已更新', 'success');
            closeThresholdModal();

            // 重新加载项目数据（强制不使用缓存）
            console.log('重新加载项目数据...');
            const balanceData = await API.getCredits();
            console.log('获取到项目数据:', balanceData);
            AppState.balanceData = balanceData;
            UI.updateStats(balanceData);
            UI.renderProjects(balanceData);
            console.log('渲染完成');
        } else {
            UI.showToast(`❌ ${result.message || '操作失败'}`, 'error');
        }
    } catch (error) {
        console.error('保存阈值失败:', error);
        UI.showToast('❌ 保存失败，请稍后重试', 'error');
    } finally {
        UI.setLoading(false);
    }
}

// 绑定事件
document.addEventListener('DOMContentLoaded', () => {
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
