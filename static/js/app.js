// Balance Alert - 前端应用

// 全局配置
const API_BASE_URL = window.location.origin;

// 工具函数
function formatCurrency(value, currency = 'USD') {
    return new Intl.NumberFormat('zh-CN', {
        style: 'currency',
        currency: currency
    }).format(value);
}

function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN');
}

// API 调用
async function fetchCredits() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/credits`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('获取余额失败:', error);
        throw error;
    }
}

async function refreshCredits() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/refresh`, {
            method: 'POST'
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('刷新失败:', error);
        throw error;
    }
}

// 页面初始化
document.addEventListener('DOMContentLoaded', () => {
    console.log('Balance Alert 已加载');
});
