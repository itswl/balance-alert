// ==================== 全局状态管理 ====================
const AppState = {
    currentTheme: localStorage.getItem('theme') || 'light',
    currentView: 'all', // 'all', 'alerts', 'subscriptions'
    currentFilter: 'all',
    searchQuery: '',
    balanceData: null,
    subscriptionData: null,
    lastUpdate: null,
    autoRefreshInterval: null,
};

// ==================== 工具函数 ====================
const Utils = {
    // 格式化货币
    formatCurrency(value, currency = 'CNY') {
        // 确保 value 是数字
        const numValue = parseFloat(value);
        if (isNaN(numValue)) {
            return '-';
        }

        return numValue.toFixed(2);
    },

    // 格式化数字（带千分位）
    formatNumber(num) {
        return new Intl.NumberFormat('zh-CN').format(num);
    },

    // 格式化日期
    formatDate(dateString) {
        if (!dateString) return '-';
        const date = new Date(dateString);
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    },

    // 计算相对时间
    getRelativeTime(dateString) {
        if (!dateString) return '未知';
        const date = new Date(dateString);
        const now = new Date();
        const diff = now - date;
        const minutes = Math.floor(diff / 60000);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (minutes < 1) return '刚刚';
        if (minutes < 60) return `${minutes}分钟前`;
        if (hours < 24) return `${hours}小时前`;
        if (days < 7) return `${days}天前`;
        return this.formatDate(dateString);
    },

    // 计算余额百分比（相对于阈值）
    getBalancePercentage(balance, threshold) {
        if (threshold === 0) return 100;
        // 不限制上限，允许超过 100%（表示余额充足）
        return (balance / threshold) * 100;
    },

    // 获取余额状态
    getBalanceStatus(balance, threshold) {
        const percentage = this.getBalancePercentage(balance, threshold);
        if (percentage >= 50) return 'normal';
        if (percentage >= 20) return 'warning';
        return 'danger';
    },

    // 防抖函数
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },
};

// ==================== API 服务 ====================
const API = {
    baseURL: window.location.origin,
    _apiKeyPromptPromise: null,

    getApiKey() {
        return (localStorage.getItem('apiKey') || '').trim();
    },

    setApiKey(value) {
        const key = (value || '').trim();
        if (key) {
            localStorage.setItem('apiKey', key);
        } else {
            localStorage.removeItem('apiKey');
        }
    },

    getAuthHeaders() {
        const apiKey = this.getApiKey();
        return apiKey ? { 'Authorization': `Bearer ${apiKey}` } : {};
    },

    async promptForApiKey() {
        if (this._apiKeyPromptPromise) {
            return this._apiKeyPromptPromise;
        }
        this._apiKeyPromptPromise = (async () => {
            const current = this.getApiKey();
            const value = window.prompt('需要 API Key 才能继续访问，请输入 API Key：', current);
            if (value === null) {
                return null;
            }
            this.setApiKey(value);
            return this.getApiKey() || null;
        })();
        const key = await this._apiKeyPromptPromise;
        this._apiKeyPromptPromise = null;
        return key;
    },

    async fetchJson(endpoint, options = {}, retried = false) {
        const authHeaders = this.getAuthHeaders();
        const url = endpoint.startsWith('http') ? endpoint : `${this.baseURL}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...authHeaders,
            ...(options.headers || {}),
        };
        const response = await fetch(url, {
            ...options,
            headers,
        });
        let data = null;
        try {
            data = await response.json();
        } catch (e) {
            data = null;
        }
        if (response.status === 401) {
            if (retried) {
                this.setApiKey('');
            } else {
                const key = await this.promptForApiKey();
                if (key) {
                    return this.fetchJson(endpoint, options, true);
                }
            }
        }
        return { response, data };
    },

    async request(endpoint, options = {}) {
        try {
            const { response, data } = await this.fetchJson(endpoint, options);

            if (!response.ok) {
                // 如果响应包含错误消息，抛出带消息的错误
                let errorMsg = data.message || data.error || response.statusText;
                if (response.status === 401) {
                    errorMsg = '未授权访问，API Key 无效或未提供';
                }
                throw new Error(errorMsg);
            }

            return data;
        } catch (error) {
            console.error('API 请求失败:', error);
            throw error;
        }
    },

    // 获取余额数据
    async getCredits() {
        return this.request('/api/credits');
    },

    // 获取订阅数据
    async getSubscriptions(noCache = false) {
        const headers = {};
        if (noCache) {
            // 禁用缓存，强制获取最新数据
            headers['Cache-Control'] = 'no-cache';
            headers['Pragma'] = 'no-cache';
        }
        return this.request('/api/subscriptions', { headers });
    },

    // 刷新数据
    async refresh() {
        return this.request('/api/refresh', {
            method: 'POST',
            body: JSON.stringify({})
        });
    },

    // 获取健康状态
    async getHealth() {
        return this.request('/health');
    },
};

// ==================== UI 组件 ====================
const UI = {
    // 显示 Toast 通知
    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <div style="flex: 1;">${message}</div>
            <button onclick="this.parentElement.remove()" style="background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 1.25rem; padding: 0; width: 24px; height: 24px;">×</button>
        `;
        container.appendChild(toast);

        // 3秒后自动移除
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    },

    // 显示/隐藏加载状态
    setLoading(show) {
        const overlay = document.getElementById('loading-overlay');
        if (show) {
            overlay.classList.add('active');
        } else {
            overlay.classList.remove('active');
        }
    },

    // 更新统计卡片
    updateStats(data) {
        const projects = data.projects || [];
        const total = projects.length;
        // 根据 need_alarm 字段判断状态
        const normal = projects.filter(p => !p.need_alarm && p.success).length;
        const alert = projects.filter(p => p.need_alarm).length;

        document.getElementById('total-projects').textContent = total;
        document.getElementById('normal-projects').textContent = normal;
        document.getElementById('alert-projects').textContent = alert;
        document.getElementById('last-update').textContent = Utils.getRelativeTime(data.last_update);
    },

    // 渲染项目卡片
    renderProjectCard(project) {
        // 使用 credits 字段而不是 balance
        const balance = project.credits || 0;
        const threshold = project.threshold || 0;
        const status = Utils.getBalanceStatus(balance, threshold);
        const percentage = Utils.getBalancePercentage(balance, threshold);
        const projectStatus = project.need_alarm ? 'alert' : 'normal';
        const currency = 'CNY'; // 默认使用人民币

        return `
            <div class="project-card" data-provider="${project.provider}" data-status="${projectStatus}">
                <div class="project-header">
                    <div class="project-info">
                        <h3>${project.project}</h3>
                        <span class="project-provider">${project.provider}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <button class="action-icon-btn" onclick="editProjectThreshold('${project.project}', ${threshold})" title="编辑阈值">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                            </svg>
                        </button>
                        <div class="project-status ${projectStatus}"></div>
                    </div>
                </div>
                <div class="project-balance">
                    <div class="balance-label">${project.type === 'balance' ? '当前余额' : '当前余额'}</div>
                    <div class="balance-value">${Utils.formatCurrency(balance, currency)}</div>
                    <div class="balance-progress">
                        <div class="balance-progress-bar ${status}" style="width: ${Math.min(100, percentage)}%"></div>
                    </div>
                </div>
                <div class="project-details">
                    <div class="detail-item">
                        <span class="detail-label">阈值</span>
                        <span class="detail-value">${Utils.formatCurrency(threshold, currency)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">类型</span>
                        <span class="detail-value">${project.type === 'balance' ? '余额' : '余额'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">充足度</span>
                        <span class="detail-value">${percentage.toFixed(0)}%</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">状态</span>
                        <span class="detail-value">${projectStatus === 'normal' ? '✅ 正常' : '⚠️ 告警'}</span>
                    </div>
                </div>
                <div class="project-actions">
                    <button class="btn-link" onclick="showProjectTrend('${project.project}', '${project.provider}')">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width: 16px; height: 16px; margin-right: 4px;">
                            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                        </svg>
                        查看趋势
                    </button>
                </div>
            </div>
        `;
    },

    // 渲染订阅卡片
    renderSubscriptionCard(sub) {
        const daysClass = sub.days_until_renewal <= 7 ? 'danger' : (sub.days_until_renewal <= 14 ? 'warning' : '');
        const cycleText = sub.cycle_type === 'monthly' ? '月付' : sub.cycle_type === 'yearly' ? '年付' : '周付';
        const amount = parseFloat(sub.amount) || 0;

        return `
            <div class="subscription-card">
                <div class="subscription-info">
                    <h3>${sub.name}</h3>
                    <div class="subscription-meta">
                        <span class="meta-item">💰 ${Utils.formatCurrency(amount, sub.currency || 'CNY')}</span>
                        <span class="meta-item">📅 ${cycleText}</span>
                        ${sub.next_renewal_date ? `<span class="meta-item">📆 下次续费: ${sub.next_renewal_date}</span>` : ''}
                        ${sub.already_renewed ? `<span class="meta-item">✅ 已续费</span>` : ''}
                    </div>
                </div>
                <div class="subscription-status">
                    <div class="subscription-actions">
                        ${!sub.already_renewed ? `
                        <button class="action-icon-btn success" onclick="markSubscriptionRenewed('${sub.name}')" title="标记已续费">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <polyline points="20 6 9 17 4 12"></polyline>
                            </svg>
                        </button>
                        ` : `
                        <button class="action-icon-btn" onclick="clearSubscriptionRenewed('${sub.name}')" title="取消续费标记">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M3 3l18 18M18 6l-12 12"></path>
                            </svg>
                        </button>
                        `}
                        <button class="action-icon-btn" onclick="editSubscription('${sub.name}')" title="编辑">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                            </svg>
                        </button>
                        <button class="action-icon-btn danger" onclick="deleteSubscription('${sub.name}')" title="删除">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                            </svg>
                        </button>
                    </div>
                    <div class="days-remaining ${daysClass}">
                        ${sub.days_until_renewal}天
                    </div>
                </div>
            </div>
        `;
    },

    // 渲染项目列表
    renderProjects(data) {
        const container = document.getElementById('projects-container');
        const projects = data.projects || [];

        // 应用筛选
        let filteredProjects = projects;

        // 搜索筛选
        if (AppState.searchQuery) {
            const query = AppState.searchQuery.toLowerCase();
            filteredProjects = filteredProjects.filter(p =>
                p.project.toLowerCase().includes(query) ||
                p.provider.toLowerCase().includes(query)
            );
        }

        // 平台筛选
        if (AppState.currentFilter !== 'all') {
            filteredProjects = filteredProjects.filter(p =>
                p.provider === AppState.currentFilter
            );
        }

        // 视图筛选
        if (AppState.currentView === 'alerts') {
            filteredProjects = filteredProjects.filter(p => p.need_alarm);
        }

        if (filteredProjects.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                    </svg>
                    <h3>暂无数据</h3>
                    <p>没有找到符合条件的项目</p>
                </div>
            `;
            return;
        }

        container.innerHTML = filteredProjects.map(p => this.renderProjectCard(p)).join('');
    },

    // 渲染订阅列表
    renderSubscriptions(data) {
        const container = document.getElementById('subscriptions-container');
        const subscriptions = data.subscriptions || [];

        if (subscriptions.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="16" y1="2" x2="16" y2="6"></line>
                        <line x1="8" y1="2" x2="8" y2="6"></line>
                        <line x1="3" y1="10" x2="21" y2="10"></line>
                    </svg>
                    <h3>暂无订阅</h3>
                    <p>还没有添加任何订阅提醒</p>
                </div>
            `;
            return;
        }

        container.innerHTML = subscriptions.map(s => this.renderSubscriptionCard(s)).join('');
    },

    // 更新平台筛选器选项
    updateProviderFilter(data) {
        const select = document.getElementById('provider-filter');
        const providers = [...new Set((data.projects || []).map(p => p.provider))];

        const options = ['<option value="all">全部平台</option>'];
        providers.forEach(provider => {
            options.push(`<option value="${provider}">${provider}</option>`);
        });

        select.innerHTML = options.join('');
    },
};

// ==================== 应用逻辑 ====================
const App = {
    // 初始化
    async init() {
        console.log('🚀 Balance Alert 初始化...');

        // 初始化主题
        this.initTheme();

        // 绑定事件
        this.bindEvents();

        // 加载数据
        await this.loadData();

        // 启动自动刷新
        this.startAutoRefresh();

        console.log('✅ 初始化完成');
    },

    // 初始化主题
    initTheme() {
        document.documentElement.setAttribute('data-theme', AppState.currentTheme);
    },

    // 切换主题
    toggleTheme() {
        AppState.currentTheme = AppState.currentTheme === 'light' ? 'dark' : 'light';
        localStorage.setItem('theme', AppState.currentTheme);
        document.documentElement.setAttribute('data-theme', AppState.currentTheme);
    },

    // 绑定事件
    bindEvents() {
        // 主题切换
        document.getElementById('theme-toggle').addEventListener('click', () => {
            this.toggleTheme();
        });

        // 刷新按钮
        document.getElementById('refresh-btn').addEventListener('click', async () => {
            await this.refresh();
        });

        // 视图切换
        document.getElementById('view-all-btn').addEventListener('click', () => {
            this.switchView('all');
        });

        document.getElementById('view-alerts-btn').addEventListener('click', () => {
            this.switchView('alerts');
        });

        document.getElementById('view-subscriptions-btn').addEventListener('click', () => {
            this.switchView('subscriptions');
        });

        // 搜索
        document.getElementById('search-input').addEventListener('input', Utils.debounce((e) => {
            AppState.searchQuery = e.target.value;
            if (AppState.balanceData) {
                UI.renderProjects(AppState.balanceData);
            }
        }, 300));

        // 平台筛选
        document.getElementById('provider-filter').addEventListener('change', (e) => {
            AppState.currentFilter = e.target.value;
            if (AppState.balanceData) {
                UI.renderProjects(AppState.balanceData);
            }
        });
    },

    // 加载数据
    async loadData() {
        try {
            UI.setLoading(true);

            // 并行加载余额和订阅数据
            const [balanceData, subscriptionData] = await Promise.all([
                API.getCredits(),
                API.getSubscriptions()
            ]);

            AppState.balanceData = balanceData;
            AppState.subscriptionData = subscriptionData;
            AppState.lastUpdate = new Date();

            // 更新 UI
            UI.updateStats(balanceData);
            UI.updateProviderFilter(balanceData);

            if (AppState.currentView === 'subscriptions') {
                UI.renderSubscriptions(subscriptionData);
            } else {
                UI.renderProjects(balanceData);
            }

        } catch (error) {
            console.error('加载数据失败:', error);
            UI.showToast('加载数据失败，请稍后重试', 'error');
        } finally {
            UI.setLoading(false);
        }
    },

    // 刷新数据
    async refresh() {
        const btn = document.getElementById('refresh-btn');
        try {
            btn.classList.add('rotating');
            UI.showToast('正在刷新数据...', 'info');

            const result = await API.refresh();

            // 刷新成功后重新加载所有数据
            await this.loadData();

            UI.showToast('✨ 数据刷新成功！', 'success');

        } catch (error) {
            console.error('刷新失败:', error);
            const errorMsg = error.message || '刷新失败，请稍后重试';
            UI.showToast(`❌ ${errorMsg}`, 'error');
        } finally {
            btn.classList.remove('rotating');
        }
    },

    // 切换视图
    switchView(view) {
        AppState.currentView = view;

        // 更新按钮状态
        document.querySelectorAll('.action-btn').forEach(btn => {
            btn.classList.remove('active');
        });

        if (view === 'all') {
            document.getElementById('view-all-btn').classList.add('active');
            document.querySelector('.content-section').style.display = 'block';
            document.getElementById('subscriptions-section').style.display = 'none';
            if (AppState.balanceData) {
                UI.renderProjects(AppState.balanceData);
            }
        } else if (view === 'alerts') {
            document.getElementById('view-alerts-btn').classList.add('active');
            document.querySelector('.content-section').style.display = 'block';
            document.getElementById('subscriptions-section').style.display = 'none';
            if (AppState.balanceData) {
                UI.renderProjects(AppState.balanceData);
            }
        } else if (view === 'subscriptions') {
            document.getElementById('view-subscriptions-btn').classList.add('active');
            document.querySelector('.content-section').style.display = 'none';
            document.getElementById('subscriptions-section').style.display = 'block';
            if (AppState.subscriptionData) {
                UI.renderSubscriptions(AppState.subscriptionData);
            }
        }
    },

    // 启动自动刷新
    startAutoRefresh() {
        // 每5分钟自动刷新一次数据（不调用 API refresh，只 reload）
        AppState.autoRefreshInterval = setInterval(async () => {
            console.log('🔄 自动刷新数据...');
            try {
                const [balanceData, subscriptionData] = await Promise.all([
                    API.getCredits(),
                    API.getSubscriptions()
                ]);

                AppState.balanceData = balanceData;
                AppState.subscriptionData = subscriptionData;

                UI.updateStats(balanceData);
                if (AppState.currentView === 'subscriptions') {
                    UI.renderSubscriptions(subscriptionData);
                } else {
                    UI.renderProjects(balanceData);
                }
            } catch (error) {
                console.error('自动刷新失败:', error);
            }
        }, 5 * 60 * 1000); // 5分钟
    },
};

// ==================== 页面加载 ====================
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});

// 页面卸载时清理
window.addEventListener('beforeunload', () => {
    if (AppState.autoRefreshInterval) {
        clearInterval(AppState.autoRefreshInterval);
    }
});
