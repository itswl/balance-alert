/**
 * 邮箱扫描页：扫描概览、邮箱账号、本次告警邮件、历史告警邮件，外加邮箱配置的增删改。
 *
 * 扫描结果存在后端进程内存里，重启就没了，所以「尚未扫描」和「扫了但没命中」
 * 要用不同文案区分 —— 都显示成 0 会让人以为扫描没生效。
 */

import { mutate } from '../api/client.js';
import { ENDPOINTS, getEmailHistory, getEmailScanState, getMailboxes, runEmailScan } from '../api/endpoints.js';
import type { EmailAlert, EmailAlertRecord, EmailScanState, MailboxConfig, MailboxPayload, MailboxResult } from '../api/types.js';
import { byId, inputById, inputValue, isChecked, onClick, setChecked, setInputValue, toggleDisplay } from '../dom.js';
import { escapeAttr, escapeHTML, formatCurrency, formatDate, getRelativeTime } from '../format.js';
import { AppState } from '../state.js';
import { emptyState } from '../ui/empty.js';
import { ICON_DELETE, ICON_EDIT } from '../ui/icons.js';
import { setLoading } from '../ui/loading.js';
import { bindModalClose, closeModal, openModal } from '../ui/modal.js';
import { showToast } from '../ui/toast.js';

const MODAL_ID = 'email-modal';
const DEFAULT_PORT = 993;

interface EmailManagerState {
  mailboxes: MailboxConfig[];
  scan: EmailScanState | null;
  history: EmailAlertRecord[];
  loaded: boolean;
}

interface AlertCardOptions {
  dryRun?: boolean;
  history?: boolean;
}

/** 实时扫描结果和数据库历史记录长得几乎一样，只有关键词字段名和 timestamp 不同 */
type AnyAlert = (EmailAlert | EmailAlertRecord) & { keywords?: string[]; matched_keywords?: string[]; timestamp?: string };

export const EmailManager = {
  state: {
    mailboxes: [],
    scan: null,
    history: [],
    loaded: false,
  } as EmailManagerState,

  async load(force = false): Promise<void> {
    if (this.state.loaded && !force) {
      this.renderAll();
      return;
    }
    try {
      setLoading(true);
      await this.fetchAll();
      this.renderAll();
    } catch (error) {
      console.error('加载邮箱扫描数据失败:', error);
      showToast(error instanceof Error && error.message ? error.message : '加载邮箱扫描数据失败', 'error');
    } finally {
      setLoading(false);
    }
  },

  async fetchAll(): Promise<void> {
    const [mailboxResult, scanState] = await Promise.all([getMailboxes(), getEmailScanState()]);
    this.state.mailboxes = mailboxResult.emails || [];
    this.state.scan = scanState ?? null;
    this.state.history = AppState.features.history ? await this.fetchHistory() : [];
    this.state.loaded = true;
  },

  async fetchHistory(): Promise<EmailAlertRecord[]> {
    try {
      const result = await getEmailHistory(30, 100);
      return result.data || [];
    } catch (error) {
      // 数据库未启用等情况下历史接口返回 503，页面照常显示其它内容
      console.warn('邮件告警历史不可用:', error);
      return [];
    }
  },

  // ---------- 渲染 ----------

  renderAll(): void {
    this.renderSummary();
    this.renderMailboxes();
    this.renderAlerts();
    this.renderHistory();
    toggleDisplay('add-email-btn', AppState.features.dynamic_config);
  },

  renderSummary(): void {
    const container = byId('email-scan-summary');
    if (!container) return;

    const scan = this.state.scan;
    const scanned = Boolean(scan?.last_update);
    const summary = scan?.summary ?? {};
    const enabledCount = this.state.mailboxes.filter((m) => m.enabled !== false).length;

    const chips: Array<{ label: string; value: string | number; cls?: string }> = [
      { label: '启用邮箱', value: enabledCount },
      { label: '扫描邮件', value: scanned ? summary.total_emails ?? 0 : '-' },
      {
        label: '告警邮件',
        value: scanned ? summary.total_alerts ?? 0 : '-',
        cls: (summary.total_alerts ?? 0) > 0 ? 'warning' : '',
      },
      { label: '已发通知', value: scanned ? summary.alerts_sent ?? 0 : '-' },
      { label: '上次扫描', value: scanned ? getRelativeTime(scan?.last_update) : '尚未扫描' },
    ];

    if (scanned && scan) {
      chips.push({ label: '扫描范围', value: `最近 ${scan.days ?? '-'} 天` });
      chips.push({
        label: '告警模式',
        value: scan.dry_run ? '仅查询，不发通知' : '发送真实通知',
        cls: scan.dry_run ? '' : 'danger',
      });
      if ((summary.failed_mailboxes ?? 0) > 0) {
        chips.push({ label: '连接失败', value: summary.failed_mailboxes ?? 0, cls: 'danger' });
      }
    }

    container.innerHTML = chips
      .map(
        (chip) => `
            <div class="summary-chip ${chip.cls || ''}">
                <span class="summary-chip-label">${escapeHTML(chip.label)}</span>
                <span class="summary-chip-value">${escapeHTML(chip.value)}</span>
            </div>
        `,
      )
      .join('');
  },

  renderMailboxes(): void {
    const container = byId('mailboxes-container');
    if (!container) return;

    const mailboxes = this.state.mailboxes;
    if (mailboxes.length === 0) {
      container.innerHTML = emptyState(
        '暂无邮箱',
        AppState.features.dynamic_config
          ? '点击右上角「添加邮箱」配置要扫描的 IMAP 邮箱'
          : '用 EMAIL_HOST / EMAIL_USERNAME / EMAIL_PASSWORD 配置邮箱；开启 ENABLE_DYNAMIC_CONFIG 后可在这里直接添加',
        'mail',
        true,
      );
      return;
    }

    const statsByName = new Map((this.state.scan?.mailboxes ?? []).map((m) => [m.name, m]));
    container.innerHTML = mailboxes.map((mailbox) => renderMailboxCard(mailbox, statsByName.get(mailbox.name))).join('');
  },

  renderAlerts(): void {
    const container = byId('email-alerts-container');
    if (!container) return;

    const scan = this.state.scan;
    if (!scan?.last_update) {
      container.innerHTML = emptyState('尚未扫描', '选择时间范围后点击「立即扫描」，结果会显示在这里', 'mail', true);
      return;
    }

    const alerts = scan.alerts || [];
    if (alerts.length === 0) {
      container.innerHTML = emptyState(
        '没有告警邮件',
        `最近 ${scan.days} 天的邮件里没有匹配到欠费 / 续费类关键词`,
        'mail',
        true,
      );
      return;
    }

    container.innerHTML = alerts.map((alert) => renderAlertCard(alert, { dryRun: scan.dry_run ?? false })).join('');
  },

  renderHistory(): void {
    const block = byId('email-history-block');
    const container = byId('email-history-container');
    if (!block || !container) return;

    if (!AppState.features.history) {
      block.style.display = 'none';
      return;
    }
    block.style.display = 'block';

    const history = this.state.history;
    container.innerHTML =
      history.length === 0
        ? emptyState('暂无历史记录', '定时任务或 Web 扫描发出过告警的邮件会记录在数据库里', 'mail', true)
        : history.map((record) => renderAlertCard(record, { history: true })).join('');
  },

  // ---------- 扫描 ----------

  async runScan(): Promise<void> {
    const btn = byId<HTMLButtonElement>('email-scan-btn');
    const days = Number.parseInt(byId<HTMLSelectElement>('email-scan-days')?.value ?? '', 10) || 1;

    if (!this.state.mailboxes.some((m) => m.enabled !== false)) {
      showToast('还没有可用的邮箱，先配置邮箱再扫描', 'warning');
      return;
    }

    try {
      if (btn) btn.disabled = true;
      showToast(`正在扫描最近 ${days} 天的邮件，连接邮箱可能需要几十秒...`, 'info');

      const result = await runEmailScan(days);
      await this.fetchAll();
      this.renderAll();

      const summary = result.summary ?? {};
      const alerts = summary.total_alerts ?? 0;
      showToast(
        `扫描完成：${summary.total_emails ?? 0} 封邮件，${alerts} 封告警${result.dry_run ? '（仅查询，未发通知）' : ''}`,
        alerts > 0 ? 'warning' : 'success',
      );
    } catch (error) {
      console.error('邮箱扫描失败:', error);
      showToast(error instanceof Error && error.message ? error.message : '扫描失败，请稍后重试', 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  },
};

// ---------- 卡片 ----------

export function renderMailboxCard(mailbox: MailboxConfig, stat: MailboxResult | undefined): string {
  const name = mailbox.name || mailbox.username || '未命名';
  const nameAttr = escapeAttr(name);
  const port = mailbox.port || DEFAULT_PORT;
  const enabled = mailbox.enabled !== false;

  let statusHtml: string;
  if (!enabled) {
    statusHtml = '<span class="status-badge muted">已停用</span>';
  } else if (!stat) {
    statusHtml = '<span class="status-badge muted">未扫描</span>';
  } else if (stat.error) {
    statusHtml = `<span class="status-badge danger" title="${escapeAttr(stat.error)}">连接失败</span>`;
  } else if (stat.alert_count > 0) {
    statusHtml = `<span class="status-badge warning">${escapeHTML(stat.alert_count)} 封告警</span>`;
  } else {
    statusHtml = '<span class="status-badge success">正常</span>';
  }

  const actions = AppState.features.dynamic_config
    ? `
            <div class="subscription-actions">
                <button class="action-icon-btn js-edit-email" data-name="${nameAttr}" title="编辑">
                    ${ICON_EDIT}
                </button>
                <button class="action-icon-btn danger js-delete-email" data-name="${nameAttr}" title="删除">
                    ${ICON_DELETE}
                </button>
            </div>`
    : '';

  const scannedMeta =
    stat && !stat.error ? `<span class="meta-item"><span class="k">上次扫描</span>${escapeHTML(stat.total_emails)} 封</span>` : '';
  const errorMeta = stat && stat.error ? `<span class="meta-item error-text">${escapeHTML(stat.error)}</span>` : '';

  return `
            <div class="subscription-card mailbox-card ${enabled ? '' : 'disabled'}">
                <div class="subscription-info">
                    <h3>${escapeHTML(name)}</h3>
                    <div class="subscription-meta">
                        <span class="meta-item">${escapeHTML(mailbox.username || '-')}</span>
                        <span class="meta-item">${escapeHTML(mailbox.host || '-')}:${escapeHTML(port)}</span>
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
}

export function renderAlertCard(alert: AnyAlert, options: AlertCardOptions = {}): string {
  let badge: string;
  if ('duplicate' in alert && alert.duplicate) {
    badge = '<span class="status-badge muted">已通知过，跳过</span>';
  } else if (alert.alert_sent) {
    badge = '<span class="status-badge success">已发送通知</span>';
  } else if (options.dryRun) {
    badge = '<span class="status-badge info">仅查询</span>';
  } else {
    badge = '<span class="status-badge danger">通知未发出</span>';
  }

  // 实时扫描给 keywords，数据库历史给 matched_keywords
  const keywords = alert.keywords ?? alert.matched_keywords ?? [];
  const keywordTags = (Array.isArray(keywords) ? keywords : [keywords])
    .map((kw) => `<span class="keyword-tag">${escapeHTML(kw)}</span>`)
    .join('');

  const hasAmount = alert.amount !== null && alert.amount !== undefined;
  const serviceName = alert.service_name && alert.service_name !== '未知服务' ? alert.service_name : '';

  return `
            <div class="email-alert-card ${options.history ? 'history' : ''}">
                <div class="email-alert-main">
                    <div class="email-alert-subject">${escapeHTML(alert.subject || '(无主题)')}</div>
                    <div class="subscription-meta">
                        <span class="meta-item project-meta">${escapeHTML(alert.mailbox || '-')}</span>
                        <span class="meta-item"><span class="k">发件人</span>${escapeHTML(alert.sender || '-')}</span>
                        <span class="meta-item">${escapeHTML(alert.date || '-')}</span>
                        ${serviceName ? `<span class="meta-item"><span class="k">服务</span>${escapeHTML(serviceName)}</span>` : ''}
                        ${hasAmount ? `<span class="meta-item"><span class="k">金额</span>${formatCurrency(alert.amount)}</span>` : ''}
                    </div>
                    ${keywordTags ? `<div class="keyword-tags">${keywordTags}</div>` : ''}
                </div>
                <div class="email-alert-side">
                    ${badge}
                    ${options.history && alert.timestamp ? `<span>记录于 ${escapeHTML(formatDate(alert.timestamp))}</span>` : ''}
                </div>
            </div>
        `;
}

// ---------- 邮箱配置增删改（需 ENABLE_DYNAMIC_CONFIG） ----------

export function openEmailModal(mailbox: MailboxConfig | null = null): void {
  byId<HTMLFormElement>('email-form')?.reset();
  setInputValue('email-port', DEFAULT_PORT);
  setChecked('email-use-ssl', true);
  setChecked('email-enabled', true);

  const title = byId('email-modal-title');
  const nameInput = inputById('email-name');
  const passwordHint = byId('email-password-hint');

  if (mailbox) {
    if (title) title.textContent = '编辑邮箱';
    setInputValue('email-edit-mode', 'true');
    nameInput.value = mailbox.name || '';
    nameInput.readOnly = true; // 名称是唯一键，改名请删掉重建
    setInputValue('email-host', mailbox.host || '');
    setInputValue('email-port', mailbox.port || DEFAULT_PORT);
    setInputValue('email-username', mailbox.username || '');
    setChecked('email-use-ssl', mailbox.use_ssl !== false);
    setChecked('email-enabled', mailbox.enabled !== false);
    if (passwordHint) passwordHint.textContent = '留空则保持原密码不变';
  } else {
    if (title) title.textContent = '添加邮箱';
    setInputValue('email-edit-mode', 'false');
    nameInput.readOnly = false;
    if (passwordHint) passwordHint.textContent = '';
  }

  openModal(MODAL_ID);
}

function closeEmailModal(): void {
  closeModal(MODAL_ID);
}

async function saveEmail(event: Event): Promise<void> {
  event.preventDefault();

  const isEdit = inputById('email-edit-mode').value === 'true';
  const data: MailboxPayload = {
    name: inputValue('email-name'),
    host: inputValue('email-host'),
    port: Number.parseInt(inputById('email-port').value, 10) || DEFAULT_PORT,
    username: inputValue('email-username'),
    use_ssl: isChecked('email-use-ssl'),
    enabled: isChecked('email-enabled'),
  };
  // 密码留空表示不改，不能传空串覆盖掉原值
  const password = inputById('email-password').value;
  if (password) data.password = password;

  if (!data.name || !data.host || !data.username) {
    showToast('显示名称、IMAP 服务器、邮箱账号都要填', 'warning');
    return;
  }
  if (!isEdit && !password) {
    showToast('新邮箱需要填写密码 / 授权码', 'warning');
    return;
  }

  const result = await mutate(ENDPOINTS.saveEmail, data, { success: isEdit ? '邮箱已更新' : '邮箱已添加', fail: '保存失败' });
  if (result) {
    closeEmailModal();
    await EmailManager.load(true);
  }
}

export function editEmail(name: string): void {
  const mailbox = EmailManager.state.mailboxes.find((m) => m.name === name);
  if (!mailbox) {
    showToast('未找到该邮箱', 'error');
    return;
  }
  openEmailModal(mailbox);
}

export async function deleteEmail(name: string): Promise<void> {
  if (!confirm(`确定要删除邮箱"${name}"吗？\n\n此操作不可恢复。`)) return;
  if (await mutate(ENDPOINTS.deleteEmail, { name }, { success: '邮箱已删除', fail: '删除失败' })) {
    await EmailManager.load(true);
  }
}

export function bindEmailManager(): void {
  onClick('email-scan-btn', () => void EmailManager.runScan());
  onClick('add-email-btn', () => openEmailModal());
  bindModalClose(MODAL_ID, '.js-close-email-modal');
  document.querySelector('.js-save-email')?.addEventListener('click', (e) => void saveEmail(e));
  byId('email-form')?.addEventListener('submit', (e) => void saveEmail(e));
}
