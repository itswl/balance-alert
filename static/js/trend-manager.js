// ==================== 余额趋势图表管理 ====================

let trendChart = null;

// MD5 哈希函数（用于生成项目 ID）
async function md5(str) {
    const encoder = new TextEncoder();
    const data = encoder.encode(str);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    return hashHex;
}

// 简单的 MD5 实现（因为 Web Crypto API 不支持 MD5，使用简单哈希代替或转换）
function simpleMD5(str) {
    // 使用简单的字符串哈希，与后端 MD5 不同但可以作为替代
    // 更好的方案是让后端 API 支持通过 provider:project_name 查询
    // 暂时先计算后端使用的格式
    return str;  // 占位符，下面会修正
}

// 显示项目趋势
async function showProjectTrend(projectName, provider) {
    const modal = document.getElementById('trend-modal');
    const title = document.getElementById('trend-modal-title');
    const statsContainer = document.getElementById('trend-stats-container');

    title.textContent = `余额趋势 - ${projectName}`;

    // 显示加载状态
    UI.setLoading(true);
    modal.classList.add('active');

    // 生成项目 ID（与后端一致：hashlib.md5(f"{provider_name}:{project_name}".encode()).hexdigest()）
    // 前端无法直接使用 MD5，改为通过 provider:project_name 格式让后端查询
    const projectId = `${provider}:${projectName}`;

    try {
        // 获取趋势数据（默认30天）
        const response = await fetch(`/api/history/trend/${encodeURIComponent(projectId)}?days=30`);
        const result = await response.json();

        if (!response.ok || result.status === 'error') {
            // 数据库未启用或无数据
            statsContainer.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: var(--text-secondary);">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width: 48px; height: 48px; margin: 0 auto 1rem;">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                    </svg>
                    <p>${result.message || '暂无历史数据'}</p>
                    <p style="font-size: 0.875rem; margin-top: 0.5rem;">
                        提示：需要启用数据库功能才能查看趋势图表<br>
                        请设置环境变量 ENABLE_DATABASE=true 并重启服务
                    </p>
                </div>
            `;

            // 清空图表
            if (trendChart) {
                trendChart.destroy();
                trendChart = null;
            }

            return;
        }

        const trendData = result.data;

        // 显示统计信息
        renderTrendStats(trendData, statsContainer);

        // 绘制趋势图表
        renderTrendChart(trendData);

    } catch (error) {
        console.error('加载趋势数据失败:', error);
        statsContainer.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: var(--danger);">
                <p>❌ 加载失败：${error.message}</p>
            </div>
        `;
    } finally {
        UI.setLoading(false);
    }
}

// 渲染趋势统计信息
function renderTrendStats(trendData, container) {
    // 计算变化趋势方向
    let trendDirection = 'stable';
    if (trendData.change > 0) {
        trendDirection = 'up';
    } else if (trendData.change < 0) {
        trendDirection = 'down';
    }

    const stats = [
        {
            label: '当前余额',
            value: Utils.formatCurrency(trendData.current_balance),
            class: ''
        },
        {
            label: '平均余额',
            value: Utils.formatCurrency(trendData.avg_balance),  // 后端返回 avg_balance
            class: ''
        },
        {
            label: '最高余额',
            value: Utils.formatCurrency(trendData.max_balance),
            class: ''
        },
        {
            label: '最低余额',
            value: Utils.formatCurrency(trendData.min_balance),
            class: ''
        },
        {
            label: '变化趋势',
            value: trendDirection === 'up' ? '↑ 上升' :
                   trendDirection === 'down' ? '↓ 下降' : '→ 稳定',
            class: trendDirection === 'up' ? 'positive' :
                   trendDirection === 'down' ? 'negative' : ''
        }
    ];

    container.innerHTML = stats.map(stat => `
        <div class="trend-stat-card">
            <div class="trend-stat-label">${stat.label}</div>
            <div class="trend-stat-value ${stat.class}">${stat.value}</div>
        </div>
    `).join('');
}

// 绘制趋势图表
function renderTrendChart(trendData) {
    const canvas = document.getElementById('trend-chart');
    const ctx = canvas.getContext('2d');

    // 销毁旧图表
    if (trendChart) {
        trendChart.destroy();
    }

    // 准备数据
    const labels = trendData.history.map(h => {
        const date = new Date(h.timestamp);
        return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
    });

    const balances = trendData.history.map(h => h.balance);
    const threshold = trendData.threshold;

    // 获取当前主题
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = isDark ? '#e5e7eb' : '#374151';
    const gridColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';

    // 创建图表
    trendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: '余额',
                    data: balances,
                    borderColor: '#6366f1',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                    pointHoverRadius: 6
                },
                {
                    label: '告警阈值',
                    data: Array(labels.length).fill(threshold),
                    borderColor: '#ef4444',
                    backgroundColor: 'transparent',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: textColor,
                        usePointStyle: true,
                        padding: 15
                    }
                },
                tooltip: {
                    backgroundColor: isDark ? '#1f2937' : '#ffffff',
                    titleColor: textColor,
                    bodyColor: textColor,
                    borderColor: gridColor,
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            label += Utils.formatCurrency(context.parsed.y);
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: gridColor,
                        drawBorder: false
                    },
                    ticks: {
                        color: textColor,
                        maxRotation: 45,
                        minRotation: 45
                    }
                },
                y: {
                    grid: {
                        color: gridColor,
                        drawBorder: false
                    },
                    ticks: {
                        color: textColor,
                        callback: function(value) {
                            return '¥' + value.toLocaleString();
                        }
                    }
                }
            }
        }
    });
}

// 关闭趋势模态框
function closeTrendModal() {
    const modal = document.getElementById('trend-modal');
    modal.classList.remove('active');

    // 销毁图表
    if (trendChart) {
        trendChart.destroy();
        trendChart = null;
    }
}

// 绑定事件
document.addEventListener('DOMContentLoaded', () => {
    // 模态框点击外部关闭
    const modal = document.getElementById('trend-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target.id === 'trend-modal') {
                closeTrendModal();
            }
        });
    }
});
