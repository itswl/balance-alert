// ==================== 全局状态管理 ====================
const AppState = {
    currentTheme: localStorage.getItem('theme') || 'light',
    currentView: 'all', // 'all', 'alerts', 'subscriptions'
    projectViewStyle: localStorage.getItem('projectViewStyle') || 'grid', // 'grid', 'list'
    currentFilter: 'all',
    searchQuery: '',
    balanceData: null,
    subscriptionData: null,
    features: {
        subscriptions: false,
        dynamic_config: false,
        history: false,
    },
    lastUpdate: null,
    autoRefreshInterval: null,
};

// ==================== 工具函数 ====================
const Utils = {
    // 格式化货币
    formatCurrency(value) {
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

    // HTML 文本转义
    escapeHTML(value) {
        return String(value ?? '').replace(/[&<>"']/g, (char) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[char]));
    },

    // HTML 属性转义
    escapeAttr(value) {
        return this.escapeHTML(value);
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
    storageKey: 'apiKey',
    _apiKeyPromptPromise: null,

    getApiKey() {
        return (localStorage.getItem(this.storageKey) || '').trim();
    },

    setApiKey(value) {
        const key = (value || '').trim();
        if (key) {
            localStorage.setItem(this.storageKey, key);
        } else {
            localStorage.removeItem(this.storageKey);
        }
    },

    getAuthHeaders() {
        const apiKey = this.getApiKey();
        return apiKey ? { 'X-API-Key': apiKey } : {};
    },

    async ensureApiKey(force = false, message = '') {
        const current = this.getApiKey();
        if (current && !force) {
            return current;
        }
        return this.promptForApiKey(message);
    },

    async promptForApiKey(message = '') {
        if (this._apiKeyPromptPromise) {
            return this._apiKeyPromptPromise;
        }

        this._apiKeyPromptPromise = new Promise((resolve) => {
            const modal = document.getElementById('auth-modal');
            const form = document.getElementById('auth-form');
            const input = document.getElementById('auth-api-key');
            const error = document.getElementById('auth-error');

            if (!modal || !form || !input) {
                const value = window.prompt(message || '请输入 API Key', this.getApiKey());
                if (value !== null) {
                    this.setApiKey(value);
                }
                resolve(this.getApiKey() || null);
                return;
            }

            error.textContent = message || '';
            error.style.display = message ? 'block' : 'none';
            input.value = this.getApiKey();
            modal.classList.add('active');
            input.focus();

            const onSubmit = (event) => {
                event.preventDefault();
                const value = input.value.trim();
                if (!value) {
                    error.textContent = '请输入 API Key';
                    error.style.display = 'block';
                    return;
                }
                this.setApiKey(value);
                modal.classList.remove('active');
                form.removeEventListener('submit', onSubmit);
                resolve(value);
            };

            form.addEventListener('submit', onSubmit);
        });

        const key = await this._apiKeyPromptPromise;
        this._apiKeyPromptPromise = null;
        return key;
    },

    async fetchJson(endpoint, options = {}, retried = false) {
        if (endpoint.startsWith('/api/')) {
            await this.ensureApiKey();
        }

        const url = endpoint.startsWith('http') ? endpoint : `${this.baseURL}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...this.getAuthHeaders(),
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

        if (response.status === 401 && endpoint.startsWith('/api/') && !retried) {
            const message = data?.message || 'API Key 无效，请更新后继续';
            const key = await this.promptForApiKey(message);
            if (key) {
                return this.fetchJson(endpoint, options, true);
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

    async getFeatures() {
        return this.request('/api/features');
    },
};

// ==================== UI 组件 ====================
const UI = {
    // 显示 Toast 通知
    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        const text = document.createElement('div');
        text.style.flex = '1';
        text.textContent = message;
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.textContent = '×';
        closeBtn.style.cssText = 'background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 1.25rem; padding: 0; width: 24px; height: 24px;';
        closeBtn.addEventListener('click', () => toast.remove());
        toast.append(text, closeBtn);
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
        const ownerProject = project.owner_project || '未关联项目';
        const projectName = project.project || project.name || '未知项目';
        const provider = project.provider || 'unknown';
        const projectNameEscaped = Utils.escapeHTML(projectName);
        const providerEscaped = Utils.escapeHTML(provider);
        const ownerProjectEscaped = Utils.escapeHTML(ownerProject);
        const projectNameAttr = Utils.escapeAttr(projectName);
        const providerAttr = Utils.escapeAttr(provider);

        const optionalActions = [];
        if (AppState.features.dynamic_config) {
            optionalActions.push(`
                        <button class="action-icon-btn js-edit-threshold" data-project="${projectNameAttr}" data-threshold="${Utils.escapeAttr(threshold)}" title="编辑阈值">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                            </svg>
                        </button>`);
        }

        return `
            <div class="project-card" data-provider="${providerAttr}" data-status="${projectStatus}">
                <div class="project-header">
                    <div class="project-info">
                        <h3>${projectNameEscaped}</h3>
                        <div class="project-meta-row">
                            <span class="project-provider">${providerEscaped}</span>
                            <span class="owner-project-badge">${ownerProjectEscaped}</span>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        ${optionalActions.join('')}
                        <div class="project-status ${projectStatus}"></div>
                    </div>
                </div>
                <div class="project-balance">
                    <div class="balance-label">${project.type === 'balance' ? '当前余额' : '当前余额'}</div>
                    <div class="balance-value">${Utils.formatCurrency(balance)}</div>
                    <div class="balance-progress">
                        <div class="balance-progress-bar ${status}" style="width: ${Math.min(100, percentage)}%"></div>
                    </div>
                </div>
                <div class="project-details">
                    <div class="detail-item">
                        <span class="detail-label">阈值</span>
                        <span class="detail-value">${Utils.formatCurrency(threshold)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">类型</span>
                        <span class="detail-value">API 调用</span>
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
                ${AppState.features.history ? `<div class="project-actions">
                    <button class="btn-link js-show-trend" data-project="${projectNameAttr}" data-provider="${providerAttr}">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width: 16px; height: 16px; margin-right: 4px;">
                            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                        </svg>
                        查看趋势
                    </button>
                </div>` : ''}
            </div>
        `;
    },

    // 渲染订阅卡片
    renderSubscriptionCard(sub) {
        const daysClass = sub.days_until_renewal <= 7 ? 'danger' : (sub.days_until_renewal <= 14 ? 'warning' : '');
        const cycleText = sub.cycle_type === 'monthly' ? '月付' : sub.cycle_type === 'yearly' ? '年付' : '周付';
        const amount = parseFloat(sub.amount) || 0;
        const ownerProject = sub.owner_project || '未关联项目';
        const subName = sub.name || '未知订阅';
        const subNameEscaped = Utils.escapeHTML(subName);
        const ownerProjectEscaped = Utils.escapeHTML(ownerProject);
        const subNameAttr = Utils.escapeAttr(subName);
        const nextRenewalEscaped = Utils.escapeHTML(sub.next_renewal_date || '');

        return `
            <div class="subscription-card">
                <div class="subscription-info">
                    <h3>${subNameEscaped}</h3>
                    <div class="subscription-meta">
                        <span class="meta-item project-meta">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect>
                                <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path>
                            </svg>
                            ${ownerProjectEscaped}
                        </span>
                        <span class="meta-item">💰 ${Utils.formatCurrency(amount)}</span>
                        <span class="meta-item">📅 ${cycleText}</span>
                        ${sub.next_renewal_date ? `<span class="meta-item">📆 下次续费: ${nextRenewalEscaped}</span>` : ''}
                        ${sub.already_renewed ? `<span class="meta-item">✅ 已续费</span>` : ''}
                    </div>
                </div>
                <div class="subscription-status">
                    <div class="subscription-actions">
                        ${!sub.already_renewed ? `
                        <button class="action-icon-btn success js-mark-renewed" data-name="${subNameAttr}" title="标记已续费">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <polyline points="20 6 9 17 4 12"></polyline>
                            </svg>
                        </button>
                        ` : `
                        <button class="action-icon-btn js-clear-renewed" data-name="${subNameAttr}" title="取消续费标记">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M3 3l18 18M18 6l-12 12"></path>
                            </svg>
                        </button>
                        `}
                        <button class="action-icon-btn js-edit-subscription" data-name="${subNameAttr}" title="编辑">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                            </svg>
                        </button>
                        <button class="action-icon-btn danger js-delete-subscription" data-name="${subNameAttr}" title="删除">
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
        
        // 应用视图样式类
        if (AppState.projectViewStyle === 'list') {
            container.className = 'projects-list';
            document.getElementById('view-list-btn').classList.add('active');
            document.getElementById('view-grid-btn').classList.remove('active');
        } else {
            container.className = 'projects-grid';
            document.getElementById('view-grid-btn').classList.add('active');
            document.getElementById('view-list-btn').classList.remove('active');
        }

        const projects = data.projects || [];

        // 应用筛选
        let filteredProjects = projects;

        // 搜索筛选
        if (AppState.searchQuery) {
            const query = AppState.searchQuery.toLowerCase();
            filteredProjects = filteredProjects.filter(p =>
                (p.project || '').toLowerCase().includes(query) ||
                (p.provider || '').toLowerCase().includes(query)
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

        select.innerHTML = '';
        const allOption = document.createElement('option');
        allOption.value = 'all';
        allOption.textContent = '全部平台';
        select.appendChild(allOption);

        providers.forEach(provider => {
            const option = document.createElement('option');
            option.value = provider;
            option.textContent = provider;
            select.appendChild(option);
        });
    },
};

// ==================== 应用逻辑 ====================
const App = {
    // 初始化
    async init() {
        // 初始化主题
        this.initTheme();

        // 绑定事件
        this.bindEvents();

        // 加载功能开关
        await this.loadFeatures();

        // 加载数据
        await this.loadData();

        // 启动自动刷新
        this.startAutoRefresh();
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
            if (!AppState.features.subscriptions) {
                UI.showToast('订阅功能未启用', 'info');
                return;
            }
            this.switchView('subscriptions');
        });

        // 视图切换 (网格/列表)
        document.getElementById('view-grid-btn').addEventListener('click', () => {
            AppState.projectViewStyle = 'grid';
            localStorage.setItem('projectViewStyle', 'grid');
            if (AppState.balanceData) {
                UI.renderProjects(AppState.balanceData);
            }
        });

        document.getElementById('view-list-btn').addEventListener('click', () => {
            AppState.projectViewStyle = 'list';
            localStorage.setItem('projectViewStyle', 'list');
            if (AppState.balanceData) {
                UI.renderProjects(AppState.balanceData);
            }
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

        document.addEventListener('click', (event) => {
            const editThresholdBtn = event.target.closest('.js-edit-threshold');
            if (editThresholdBtn) {
                editProjectThreshold(editThresholdBtn.dataset.project, parseFloat(editThresholdBtn.dataset.threshold || '0'));
                return;
            }

            const trendBtn = event.target.closest('.js-show-trend');
            if (trendBtn) {
                showProjectTrend(trendBtn.dataset.project, trendBtn.dataset.provider);
                return;
            }

            const markRenewedBtn = event.target.closest('.js-mark-renewed');
            if (markRenewedBtn) {
                markSubscriptionRenewed(markRenewedBtn.dataset.name);
                return;
            }

            const clearRenewedBtn = event.target.closest('.js-clear-renewed');
            if (clearRenewedBtn) {
                clearSubscriptionRenewed(clearRenewedBtn.dataset.name);
                return;
            }

            const editSubscriptionBtn = event.target.closest('.js-edit-subscription');
            if (editSubscriptionBtn) {
                editSubscription(editSubscriptionBtn.dataset.name);
                return;
            }

            const deleteSubscriptionBtn = event.target.closest('.js-delete-subscription');
            if (deleteSubscriptionBtn) {
                deleteSubscription(deleteSubscriptionBtn.dataset.name);
            }
        });
    },

    async loadFeatures() {
        try {
            const result = await API.getFeatures();
            AppState.features = {
                ...AppState.features,
                ...(result.features || {}),
            };
        } catch (error) {
            console.warn('功能开关加载失败，使用核心版默认设置:', error);
        }

        const subscriptionBtn = document.getElementById('view-subscriptions-btn');
        if (subscriptionBtn && !AppState.features.subscriptions) {
            subscriptionBtn.style.display = 'none';
        }

        const addSubscriptionBtn = document.getElementById('add-subscription-btn');
        if (addSubscriptionBtn && !AppState.features.subscriptions) {
            addSubscriptionBtn.style.display = 'none';
        }
    },

    // 加载数据
    async loadData() {
        try {
            UI.setLoading(true);

            const balanceData = await API.getCredits();
            const subscriptionData = AppState.features.subscriptions
                ? await API.getSubscriptions()
                : { subscriptions: [] };

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
            try {
                const balanceData = await API.getCredits();
                const subscriptionData = AppState.features.subscriptions
                    ? await API.getSubscriptions()
                    : { subscriptions: [] };

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
