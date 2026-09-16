// ==================== 邮箱扫描页面 ====================
// 依赖 app.js 里的 AppState / API / UI / Utils；视图切换到 email 时由 App.switchView 调用 EmailManager.load()

const EmailManager = {
    state: {
        mailboxes: [],   // /api/config/emails，密码已脱敏
        scan: null,      // /api/email/scan，上次扫描结果
        history: [],     // /api/history/email-alerts，数据库里的历史告警邮件
        loaded: false,
    },

    async load(force = false) {
        if (this.state.loaded && !force) {
            this.renderAll();
            return;
        }
        try {
            UI.setLoading(true);
            await this.fetchAll();
            this.renderAll();
        } catch (error) {
            console.error('加载邮箱扫描数据失败:', error);
            UI.showToast(`❌ ${error.message || '加载邮箱扫描数据失败'}`, 'error');
        } finally {
            UI.setLoading(false);
        }
    },

    async fetchAll() {
        const [mailboxResult, scanState] = await Promise.all([
            API.getMailboxes(),
            API.getEmailScanState(),
        ]);
        this.state.mailboxes = mailboxResult.emails || [];
        this.state.scan = scanState || null;
        this.state.history = AppState.features.history ? await this.fetchHistory() : [];
        this.state.loaded = true;
    },

    async fetchHistory() {
        try {
            const result = await API.getEmailHistory(30, 100);
            return result.data || [];
        } catch (error) {
            // 数据库未启用等情况下历史接口返回 503，页面照常显示其它内容
            console.warn('邮件告警历史不可用:', error);
            return [];
        }
    },

    // ---------- 渲染 ----------

    renderAll() {
        this.renderSummary();
        this.renderMailboxes();
        this.renderAlerts();
        this.renderHistory();

        const addBtn = document.getElementById('add-email-btn');
        if (addBtn) {
            addBtn.style.display = AppState.features.dynamic_config ? 'inline-flex' : 'none';
        }
    },

    emptyState(title, text) {
        return `
            <div class="empty-state compact">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
                    <polyline points="22,6 12,13 2,6"></polyline>
                </svg>
                <h3>${Utils.escapeHTML(title)}</h3>
                <p>${Utils.escapeHTML(text)}</p>
            </div>
        `;
    },

    renderSummary() {
        const container = document.getElementById('email-scan-summary');
        const scan = this.state.scan;
        const scanned = Boolean(scan?.last_update);
        const summary = scan?.summary || {};
        const enabledCount = this.state.mailboxes.filter(m => m.enabled !== false).length;

        const chips = [
            { label: '启用邮箱', value: enabledCount },
            { label: '扫描邮件', value: scanned ? (summary.total_emails ?? 0) : '-' },
            { label: '告警邮件', value: scanned ? (summary.total_alerts ?? 0) : '-', cls: summary.total_alerts > 0 ? 'warning' : '' },
            { label: '已发通知', value: scanned ? (summary.alerts_sent ?? 0) : '-' },
            { label: '上次扫描', value: scanned ? Utils.getRelativeTime(scan.last_update) : '尚未扫描' },
        ];
        if (scanned) {
            chips.push({ label: '扫描范围', value: `最近 ${scan.days ?? '-'} 天` });
            chips.push({
                label: '告警模式',
                value: scan.dry_run ? '仅查询，不发通知' : '发送真实通知',
                cls: scan.dry_run ? '' : 'danger',
            });
            if (summary.failed_mailboxes > 0) {
                chips.push({ label: '连接失败', value: summary.failed_mailboxes, cls: 'danger' });
            }
        }

        container.innerHTML = chips.map(chip => `
            <div class="summary-chip ${chip.cls || ''}">
                <span class="summary-chip-label">${Utils.escapeHTML(chip.label)}</span>
                <span class="summary-chip-value">${Utils.escapeHTML(chip.value)}</span>
            </div>
        `).join('');
    },

    renderMailboxes() {
        const container = document.getElementById('mailboxes-container');
        const mailboxes = this.state.mailboxes;

        if (mailboxes.length === 0) {
            container.innerHTML = this.emptyState(
                '暂无邮箱',
                AppState.features.dynamic_config
                    ? '点击右上角「添加邮箱」配置要扫描的 IMAP 邮箱'
                    : '用 EMAIL_HOST / EMAIL_USERNAME / EMAIL_PASSWORD 配置邮箱；开启 ENABLE_DYNAMIC_CONFIG 后可在这里直接添加'
            );
            return;
        }

        const statsByName = new Map((this.state.scan?.mailboxes || []).map(m => [m.name, m]));
        container.innerHTML = mailboxes
            .map(mailbox => this.renderMailboxCard(mailbox, statsByName.get(mailbox.name)))
            .join('');
    },

    renderMailboxCard(mailbox, stat) {
        const name = mailbox.name || mailbox.username || '未命名';
        const nameAttr = Utils.escapeAttr(name);
        const port = mailbox.port || 993;
        const enabled = mailbox.enabled !== false;

        let statusHtml;
        if (!enabled) {
            statusHtml = '<span class="status-badge muted">已停用</span>';
        } else if (!stat) {
            statusHtml = '<span class="status-badge muted">未扫描</span>';
        } else if (stat.error) {
            statusHtml = `<span class="status-badge danger" title="${Utils.escapeAttr(stat.error)}">连接失败</span>`;
        } else if (stat.alert_count > 0) {
            statusHtml = `<span class="status-badge warning">${Utils.escapeHTML(stat.alert_count)} 封告警</span>`;
        } else {
            statusHtml = '<span class="status-badge success">正常</span>';
        }

        const actions = AppState.features.dynamic_config ? `
            <div class="subscription-actions">
                <button class="action-icon-btn js-edit-email" data-name="${nameAttr}" title="编辑">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                    </svg>
                </button>
                <button class="action-icon-btn danger js-delete-email" data-name="${nameAttr}" title="删除">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                </button>
            </div>` : '';

        const scannedMeta = stat && !stat.error
            ? `<span class="meta-item"><span class="k">上次扫描</span>${Utils.escapeHTML(stat.total_emails)} 封</span>`
            : '';
        const errorMeta = stat && stat.error
            ? `<span class="meta-item error-text">${Utils.escapeHTML(stat.error)}</span>`
            : '';

        return `
            <div class="subscription-card mailbox-card ${enabled ? '' : 'disabled'}">
                <div class="subscription-info">
                    <h3>${Utils.escapeHTML(name)}</h3>
                    <div class="subscription-meta">
                        <span class="meta-item">${Utils.escapeHTML(mailbox.username || '-')}</span>
                        <span class="meta-item">${Utils.escapeHTML(mailbox.host || '-')}:${Utils.escapeHTML(port)}</span>
                        <span class="meta-item">${mailbox.use_ssl === false ? '明文' : 'SSL'}</span>
                        ${scannedMeta}
                        ${errorMeta}
                    </div>
                </div>
                <div class="subscription-status">
                    ${actions}
                    ${statusHtml}
                </div>
            </div>
        `;
    },

    renderAlerts() {
        const container = document.getElementById('email-alerts-container');
        const scan = this.state.scan;

        if (!scan?.last_update) {
            container.innerHTML = this.emptyState('尚未扫描', '选择时间范围后点击「立即扫描」，结果会显示在这里');
            return;
        }

        const alerts = scan.alerts || [];
        if (alerts.length === 0) {
            container.innerHTML = this.emptyState('没有告警邮件', `最近 ${scan.days} 天的邮件里没有匹配到欠费 / 续费类关键词`);
            return;
        }

        container.innerHTML = alerts.map(alert => this.renderAlertCard(alert, { dryRun: scan.dry_run })).join('');
    },

    renderHistory() {
        const block = document.getElementById('email-history-block');
        const container = document.getElementById('email-history-container');
        if (!AppState.features.history) {
            block.style.display = 'none';
            return;
        }
        block.style.display = 'block';

        const history = this.state.history;
        if (history.length === 0) {
            container.innerHTML = this.emptyState('暂无历史记录', '定时任务或 Web 扫描发出过告警的邮件会记录在数据库里');
            return;
        }
        container.innerHTML = history.map(record => this.renderAlertCard(record, { history: true })).join('');
    },

    renderAlertCard(alert, options = {}) {
        let badge;
        if (alert.duplicate) {
            badge = '<span class="status-badge muted">已通知过，跳过</span>';
        } else if (alert.alert_sent) {
            badge = '<span class="status-badge success">已发送通知</span>';
        } else if (options.dryRun) {
            badge = '<span class="status-badge info">仅查询</span>';
        } else {
            badge = '<span class="status-badge danger">通知未发出</span>';
        }

        const keywords = alert.keywords || alert.matched_keywords || [];
        const keywordTags = (Array.isArray(keywords) ? keywords : [keywords])
            .map(kw => `<span class="keyword-tag">${Utils.escapeHTML(kw)}</span>`)
            .join('');

        const hasAmount = alert.amount !== null && alert.amount !== undefined && alert.amount !== '';
        const serviceName = alert.service_name && alert.service_name !== '未知服务' ? alert.service_name : '';

        return `
            <div class="email-alert-card ${options.history ? 'history' : ''}">
                <div class="email-alert-main">
                    <div class="email-alert-subject">${Utils.escapeHTML(alert.subject || '(无主题)')}</div>
                    <div class="subscription-meta">
                        <span class="meta-item project-meta">${Utils.escapeHTML(alert.mailbox || '-')}</span>
                        <span class="meta-item"><span class="k">发件人</span>${Utils.escapeHTML(alert.sender || '-')}</span>
                        <span class="meta-item">${Utils.escapeHTML(alert.date || '-')}</span>
                        ${serviceName ? `<span class="meta-item"><span class="k">服务</span>${Utils.escapeHTML(serviceName)}</span>` : ''}
                        ${hasAmount ? `<span class="meta-item"><span class="k">金额</span>${Utils.formatCurrency(alert.amount)}</span>` : ''}
                    </div>
                    ${keywordTags ? `<div class="keyword-tags">${keywordTags}</div>` : ''}
                </div>
                <div class="email-alert-side">
                    ${badge}
                    ${options.history && alert.timestamp ? `<span>记录于 ${Utils.escapeHTML(Utils.formatDate(alert.timestamp))}</span>` : ''}
                </div>
            </div>
        `;
    },

    // ---------- 扫描 ----------

    async runScan() {
        const btn = document.getElementById('email-scan-btn');
        const days = parseInt(document.getElementById('email-scan-days').value, 10) || 1;

        if (!this.state.mailboxes.some(m => m.enabled !== false)) {
            UI.showToast('还没有可用的邮箱，先配置邮箱再扫描', 'warning');
            return;
        }

        try {
            btn.disabled = true;
            UI.showToast(`正在扫描最近 ${days} 天的邮件，连接邮箱可能需要几十秒...`, 'info');

            const result = await API.runEmailScan(days);
            await this.fetchAll();
            this.renderAll();

            const summary = result.summary || {};
            const alerts = summary.total_alerts ?? 0;
            UI.showToast(
                `✅ 扫描完成：${summary.total_emails ?? 0} 封邮件，${alerts} 封告警${result.dry_run ? '（仅查询，未发通知）' : ''}`,
                alerts > 0 ? 'warning' : 'success'
            );
        } catch (error) {
            console.error('邮箱扫描失败:', error);
            UI.showToast(`❌ ${error.message || '扫描失败，请稍后重试'}`, 'error');
        } finally {
            btn.disabled = false;
        }
    },
};

// ---------- 邮箱配置增删改（需 ENABLE_DYNAMIC_CONFIG） ----------

function openEmailModal(mailbox = null) {
    const modal = document.getElementById('email-modal');
    const form = document.getElementById('email-form');
    const title = document.getElementById('email-modal-title');
    const nameInput = document.getElementById('email-name');
    const passwordHint = document.getElementById('email-password-hint');

    form.reset();
    document.getElementById('email-port').value = 993;
    document.getElementById('email-use-ssl').checked = true;
    document.getElementById('email-enabled').checked = true;

    if (mailbox) {
        title.textContent = '编辑邮箱';
        document.getElementById('email-edit-mode').value = 'true';
        nameInput.value = mailbox.name || '';
        nameInput.readOnly = true; // 名称是唯一键，改名请删掉重建
        document.getElementById('email-host').value = mailbox.host || '';
        document.getElementById('email-port').value = mailbox.port || 993;
        document.getElementById('email-username').value = mailbox.username || '';
        document.getElementById('email-use-ssl').checked = mailbox.use_ssl !== false;
        document.getElementById('email-enabled').checked = mailbox.enabled !== false;
        passwordHint.textContent = '留空则保持原密码不变';
    } else {
        title.textContent = '添加邮箱';
        document.getElementById('email-edit-mode').value = 'false';
        nameInput.readOnly = false;
        passwordHint.textContent = '';
    }

    modal.classList.add('active');
}

function closeEmailModal() {
    document.getElementById('email-modal').classList.remove('active');
}

async function saveEmail(event) {
    event.preventDefault();

    const isEdit = document.getElementById('email-edit-mode').value === 'true';
    const data = {
        name: document.getElementById('email-name').value.trim(),
        host: document.getElementById('email-host').value.trim(),
        port: parseInt(document.getElementById('email-port').value, 10) || 993,
        username: document.getElementById('email-username').value.trim(),
        use_ssl: document.getElementById('email-use-ssl').checked,
        enabled: document.getElementById('email-enabled').checked,
    };
    const password = document.getElementById('email-password').value;
    if (password) {
        data.password = password;
    }

    if (!data.name || !data.host || !data.username) {
        UI.showToast('显示名称、IMAP 服务器、邮箱账号都要填', 'warning');
        return;
    }
    if (!isEdit && !password) {
        UI.showToast('新邮箱需要填写密码 / 授权码', 'warning');
        return;
    }

    const result = await API.mutate('/api/config/email', data, { success: isEdit ? '邮箱已更新' : '邮箱已添加', fail: '保存失败' });
    if (result) {
        closeEmailModal();
        await EmailManager.load(true);
    }
}

function editEmail(name) {
    const mailbox = EmailManager.state.mailboxes.find(m => m.name === name);
    if (!mailbox) {
        UI.showToast('❌ 未找到该邮箱', 'error');
        return;
    }
    openEmailModal(mailbox);
}

async function deleteEmail(name) {
    if (!confirm(`确定要删除邮箱"${name}"吗？\n\n此操作不可恢复。`)) {
        return;
    }

    if (await API.mutate('/api/config/email/delete', { name }, { success: '邮箱已删除', fail: '删除失败' })) {
        await EmailManager.load(true);
    }
}

// ---------- 事件绑定 ----------

document.addEventListener('DOMContentLoaded', () => {
    const scanBtn = document.getElementById('email-scan-btn');
    if (scanBtn) {
        scanBtn.addEventListener('click', () => EmailManager.runScan());
    }

    const addBtn = document.getElementById('add-email-btn');
    if (addBtn) {
        addBtn.addEventListener('click', () => openEmailModal());
    }

    document.querySelectorAll('.js-close-email-modal').forEach((button) => {
        button.addEventListener('click', closeEmailModal);
    });

    const saveBtn = document.querySelector('.js-save-email');
    if (saveBtn) {
        saveBtn.addEventListener('click', saveEmail);
    }

    const form = document.getElementById('email-form');
    if (form) {
        form.addEventListener('submit', saveEmail);
    }

    const modal = document.getElementById('email-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target.id === 'email-modal') {
                closeEmailModal();
            }
        });
    }
});
