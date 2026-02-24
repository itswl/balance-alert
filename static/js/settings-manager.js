// ==================== 设置管理功能 ====================

// 打开设置模态框
function openSettingsModal() {
    const modal = document.getElementById('settings-modal');

    // 加载当前设置
    const darkModeCheckbox = document.getElementById('setting-dark-mode');
    const autoRefreshCheckbox = document.getElementById('setting-auto-refresh');

    // 深色模式
    if (darkModeCheckbox) {
        darkModeCheckbox.checked = AppState.currentTheme === 'dark';
        darkModeCheckbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                if (AppState.currentTheme !== 'dark') {
                    App.toggleTheme();
                }
            } else {
                if (AppState.currentTheme === 'dark') {
                    App.toggleTheme();
                }
            }
        });
    }

    // 自动刷新
    if (autoRefreshCheckbox) {
        autoRefreshCheckbox.checked = AppState.autoRefreshInterval !== null;
        autoRefreshCheckbox.addEventListener('change', (e) => {
            if (e.target.checked) {
                if (!AppState.autoRefreshInterval) {
                    App.startAutoRefresh();
                    UI.showToast('✅ 已启用自动刷新', 'success');
                }
            } else {
                if (AppState.autoRefreshInterval) {
                    clearInterval(AppState.autoRefreshInterval);
                    AppState.autoRefreshInterval = null;
                    UI.showToast('⏸️ 已禁用自动刷新', 'info');
                }
            }
        });
    }

    modal.classList.add('active');
}

// 关闭设置模态框
function closeSettingsModal() {
    const modal = document.getElementById('settings-modal');
    modal.classList.remove('active');
}

// 绑定事件
document.addEventListener('DOMContentLoaded', () => {
    // 设置按钮
    const settingsBtn = document.getElementById('settings-btn');
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
            openSettingsModal();
        });
    }

    // 模态框点击外部关闭
    const modal = document.getElementById('settings-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target.id === 'settings-modal') {
                closeSettingsModal();
            }
        });
    }
});
