// ==================== 订阅管理功能 ====================

// 打开订阅模态框
function openSubscriptionModal(subscription = null) {
    const modal = document.getElementById('subscription-modal');
    const form = document.getElementById('subscription-form');
    const title = document.getElementById('modal-title');

    // 重置表单
    form.reset();

    if (subscription) {
        // 编辑模式
        title.textContent = '编辑订阅';
        document.getElementById('edit-mode').value = 'true';
        document.getElementById('original-name').value = subscription.name;
        document.getElementById('sub-name').value = subscription.name;
        document.getElementById('sub-amount').value = subscription.amount || 0;
        document.getElementById('sub-currency').value = subscription.currency || 'CNY';
        document.getElementById('sub-cycle').value = subscription.cycle_type || 'monthly';
        document.getElementById('sub-renewal-day').value = subscription.renewal_day || 1;
        document.getElementById('sub-alert-days').value = subscription.alert_days_before || 7;
        if (subscription.last_renewed_date) {
            document.getElementById('sub-last-renewed').value = subscription.last_renewed_date;
        }
        document.getElementById('sub-enabled').checked = subscription.enabled !== false;
    } else {
        // 添加模式
        title.textContent = '添加订阅';
        document.getElementById('edit-mode').value = 'false';
        document.getElementById('sub-enabled').checked = true;
    }

    modal.classList.add('active');
}

// 关闭订阅模态框
function closeSubscriptionModal() {
    const modal = document.getElementById('subscription-modal');
    modal.classList.remove('active');
}

// 保存订阅
async function saveSubscription(event) {
    event.preventDefault();

    const isEdit = document.getElementById('edit-mode').value === 'true';
    const originalName = document.getElementById('original-name').value;

    const data = {
        name: document.getElementById('sub-name').value.trim(),
        amount: parseFloat(document.getElementById('sub-amount').value),
        currency: document.getElementById('sub-currency').value,
        cycle_type: document.getElementById('sub-cycle').value,
        renewal_day: parseInt(document.getElementById('sub-renewal-day').value),
        alert_days_before: parseInt(document.getElementById('sub-alert-days').value),
        enabled: document.getElementById('sub-enabled').checked,
    };

    const lastRenewed = document.getElementById('sub-last-renewed').value;
    if (lastRenewed) {
        data.last_renewed_date = lastRenewed;
    }

    try {
        UI.setLoading(true);

        let endpoint, method;
        if (isEdit) {
            endpoint = '/api/config/subscription';
            method = 'POST';
            // 如果名称改变了，需要传递新名称
            if (data.name !== originalName) {
                data.new_name = data.name;
                data.name = originalName;
            }
        } else {
            endpoint = '/api/subscription/add';
            method = 'POST';
        }

        const response = await fetch(endpoint, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            UI.showToast(isEdit ? '✅ 订阅已更新' : '✅ 订阅已添加', 'success');
            closeSubscriptionModal();

            // 重新加载订阅数据
            const subscriptionData = await API.getSubscriptions();
            AppState.subscriptionData = subscriptionData;
            UI.renderSubscriptions(subscriptionData);
        } else {
            UI.showToast(`❌ ${result.message || '操作失败'}`, 'error');
        }
    } catch (error) {
        console.error('保存订阅失败:', error);
        UI.showToast('❌ 保存失败，请稍后重试', 'error');
    } finally {
        UI.setLoading(false);
    }
}

// 编辑订阅
async function editSubscription(name) {
    try {
        // 从当前数据中找到订阅
        const subscription = AppState.subscriptionData.subscriptions.find(s => s.name === name);
        if (subscription) {
            // 需要获取完整配置（包括 alert_days_before）
            const response = await fetch('/api/config/subscriptions');
            const result = await response.json();
            const fullSub = result.subscriptions.find(s => s.name === name);
            openSubscriptionModal(fullSub || subscription);
        } else {
            UI.showToast('❌ 未找到该订阅', 'error');
        }
    } catch (error) {
        console.error('加载订阅失败:', error);
        UI.showToast('❌ 加载失败', 'error');
    }
}

// 删除订阅
async function deleteSubscription(name) {
    if (!confirm(`确定要删除订阅"${name}"吗？\n\n此操作不可恢复。`)) {
        return;
    }

    try {
        UI.setLoading(true);

        const response = await fetch('/api/subscription/delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name })
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            UI.showToast('✅ 订阅已删除', 'success');

            // 重新加载订阅数据
            const subscriptionData = await API.getSubscriptions();
            AppState.subscriptionData = subscriptionData;
            UI.renderSubscriptions(subscriptionData);
        } else {
            UI.showToast(`❌ ${result.message || '删除失败'}`, 'error');
        }
    } catch (error) {
        console.error('删除订阅失败:', error);
        UI.showToast('❌ 删除失败，请稍后重试', 'error');
    } finally {
        UI.setLoading(false);
    }
}

// 标记订阅已续费
async function markSubscriptionRenewed(name) {
    try {
        UI.setLoading(true);

        const response = await fetch('/api/subscription/mark_renewed', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name })
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            UI.showToast('✅ 已标记为已续费', 'success');

            // 重新加载订阅数据
            const subscriptionData = await API.getSubscriptions();
            AppState.subscriptionData = subscriptionData;
            UI.renderSubscriptions(subscriptionData);
        } else {
            UI.showToast(`❌ ${result.message || '操作失败'}`, 'error');
        }
    } catch (error) {
        console.error('标记续费失败:', error);
        UI.showToast('❌ 操作失败，请稍后重试', 'error');
    } finally {
        UI.setLoading(false);
    }
}

// 取消订阅续费标记
async function clearSubscriptionRenewed(name) {
    try {
        UI.setLoading(true);

        const response = await fetch('/api/subscription/clear_renewed', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name })
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            UI.showToast('✅ 已取消续费标记', 'success');

            // 重新加载订阅数据
            const subscriptionData = await API.getSubscriptions();
            AppState.subscriptionData = subscriptionData;
            UI.renderSubscriptions(subscriptionData);
        } else {
            UI.showToast(`❌ ${result.message || '操作失败'}`, 'error');
        }
    } catch (error) {
        console.error('取消续费标记失败:', error);
        UI.showToast('❌ 操作失败，请稍后重试', 'error');
    } finally {
        UI.setLoading(false);
    }
}

// 绑定事件
document.addEventListener('DOMContentLoaded', () => {
    // 添加订阅按钮
    const addBtn = document.getElementById('add-subscription-btn');
    if (addBtn) {
        addBtn.addEventListener('click', () => openSubscriptionModal());
    }

    // 模态框点击外部关闭
    const modal = document.getElementById('subscription-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target.id === 'subscription-modal') {
                closeSubscriptionModal();
            }
        });
    }
});
