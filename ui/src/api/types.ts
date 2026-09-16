/**
 * HTTP 契约的类型定义。
 *
 * 字段逐个对照 docs/API.md 与 internal/model/model.go —— 后端把「没查到」序列化成 null
 * 而不是 0，所以这里也一律用 `| null` 而不是可选属性：漏判 null 会让失败的项目
 * 在看板上显示成「余额 0，状态正常」。
 */

// ==================== 枚举 ====================

/** 余额类型，对应 model.TypeBalance / TypeCredits / TypeQuota */
export type BalanceType = 'balance' | 'credits' | 'quota';

/** 跑道置信度，对应 model.Confidence*；none 时其余估算字段为空，low 不用于告警 */
export type Confidence = 'none' | 'low' | 'medium' | 'high';

/** 订阅周期，对应 model.Cycle* */
export type CycleType = 'weekly' | 'monthly' | 'yearly';

// ==================== 通用信封 ====================

/** 出错时的响应；参数校验失败还会带 errors */
export interface ErrorResponse {
  status: 'error';
  message: string;
  errors?: string[];
}

/** 写操作成功时的响应 */
export interface MutationResponse {
  status: 'success';
  message?: string;
}

/** 解析失败或非 JSON 响应时 data 为 null，调用方必须能处理 */
export type ApiPayload<T> = T | ErrorResponse | null;

// ==================== /api/features ====================

/** 可选能力开关；后端新增开关时这里补字段，未知字段被忽略不会报错 */
export interface Features {
  subscriptions: boolean;
  dynamic_config: boolean;
  history: boolean;
}

export interface FeaturesResponse {
  status: 'success';
  features: Features;
}

// ==================== /api/credits ====================

/** 跑道分析里按本地日期归集的消耗，对应 model.DailySpend */
export interface DailySpend {
  date: string; // YYYY-MM-DD
  consumed: number;
}

/** 一个账户的消耗画像，对应 model.Runway */
export interface Runway {
  project_id: string;
  project_name: string;
  provider: string;
  balance_type: BalanceType;
  current_balance: number | null;
  window_days: number;
  data_points: number;
  span_hours: number;
  consumed: number;
  topped_up: number;
  burn_per_day: number | null;
  runway_days: number | null;
  depletion_date: string | null; // YYYY-MM-DD
  confidence: Confidence;
  daily: DailySpend[];
  today_consumed: number | null;
  baseline_consumed: number | null;
  spike_ratio: number | null;
}

/**
 * 一次余额检查的结果，对应 model.CheckResult。
 * runway 带 omitempty：没开数据库或攒够历史之前整个字段不出现。
 */
export interface CheckResult {
  project: string;
  owner_project: string | null;
  provider: string;
  type: BalanceType;
  success: boolean;
  credits: number | null;
  threshold: number | null;
  need_alarm: boolean;
  alarm_sent: boolean;
  error: string | null;
  cached: boolean;
  runway?: Runway | null;
}

/** 看板顶部计数，对应 model.BalanceSummary */
export interface BalanceSummary {
  total: number;
  success: number;
  failed: number;
  need_alarm: number;
}

/** 进程刚起来还没检查过时 projects 为空、summary 为 {}，所以 summary 写成 Partial */
export interface CreditsResponse {
  last_update: string | null; // ISO，Z 结尾
  projects: CheckResult[];
  summary: Partial<BalanceSummary>;
}

// ==================== /api/refresh ====================

export interface RefreshResponse {
  status: 'success';
  message: string;
  refreshed_count: number;
  execution_time_seconds: number;
  dry_run: boolean;
}

// ==================== /api/subscriptions ====================

/** 一条订阅的检查结果，对应 model.SubscriptionResult */
export interface SubscriptionResult {
  name: string;
  owner_project: string | null;
  renewal_day: number;
  cycle_type: CycleType;
  days_until_renewal: number;
  next_renewal_date: string; // YYYY-MM-DD
  need_alert: boolean;
  alert_sent: boolean;
  amount: number;
  already_renewed: boolean;
  last_renewed_date: string | null;
}

export interface SubscriptionsResponse {
  last_update: string | null;
  subscriptions: SubscriptionResult[];
  summary: Partial<{ total: number; need_alert: number }>;
}

// ==================== /api/config/subscriptions ====================

/** 订阅配置（含 alert_days_before 等运行状态里没有的字段），对应 model.Subscription */
export interface SubscriptionConfig {
  name: string;
  owner_project: string | null;
  cycle_type: CycleType;
  renewal_day: number; // 周付 1-7，月付 1-31，年付 MMDD
  alert_days_before: number;
  amount: number;
  enabled: boolean;
  last_renewed_date: string | null;
}

export interface SubscriptionsConfigResponse {
  status: 'success';
  subscriptions: SubscriptionConfig[];
}

/** POST /api/config/subscription 的载荷：name 定位，new_name 改名，其余按需传 */
export interface SubscriptionPayload {
  name: string;
  new_name?: string;
  owner_project: string | null;
  amount: number;
  cycle_type: CycleType;
  renewal_day: number;
  alert_days_before: number;
  enabled: boolean;
  last_renewed_date?: string;
}

// ==================== /api/providers ====================

export interface ProviderOption {
  value: string;
  label: string;
  default_type: BalanceType;
}

export interface ProvidersResponse {
  status: 'success';
  providers: ProviderOption[];
}

// ==================== /api/config/projects ====================

/** 项目配置，对应 model.Project；api_key 已脱敏，from_env 的项目不可删 */
export interface ProjectConfig {
  name: string;
  provider: string;
  api_key: string;
  threshold: number;
  type: BalanceType;
  owner_project: string | null;
  enabled: boolean;
  from_env?: boolean;
}

export interface ProjectsConfigResponse {
  status: 'success';
  projects: ProjectConfig[];
}

/** POST /api/config/project 的载荷：新增需 provider + api_key，更新时密钥留空不改 */
export interface ProjectPayload {
  name: string;
  provider: string;
  type: BalanceType | null;
  owner_project: string | null;
  enabled: boolean;
  threshold?: number;
  api_key?: string;
}

// ==================== /api/config/emails ====================

/** 邮箱配置，对应 model.Mailbox；password 已脱敏成 '***' 或 '' */
export interface MailboxConfig {
  name: string;
  host: string;
  port: number;
  username: string;
  password: string;
  use_ssl: boolean;
  enabled: boolean;
  from_env?: boolean;
}

export interface EmailsConfigResponse {
  status: 'success';
  emails: MailboxConfig[];
}

/** POST /api/config/email 的载荷：新增需 host / username / password，更新时密码留空不改 */
export interface MailboxPayload {
  name: string;
  host: string;
  port: number;
  username: string;
  use_ssl: boolean;
  enabled: boolean;
  password?: string;
}

// ==================== /api/email/scan ====================

/** 一个邮箱本次扫描的连接与统计情况，对应 model.MailboxResult */
export interface MailboxResult {
  name: string;
  host: string;
  port: number;
  username: string;
  total_emails: number;
  alert_count: number;
  success: boolean;
  error: string | null;
}

/** 一封命中关键词的邮件，对应 model.EmailAlert */
export interface EmailAlert {
  mailbox: string;
  subject: string;
  sender: string;
  date: string;
  keywords: string[];
  service_name: string | null;
  amount: number | null;
  alert_sent: boolean;
  /**
   * 冷却期内重复命中、没再发通知时才出现。Python 版在 email_scanner 里写这个字段，
   * 但 model.EmailAlert 还没有对应成员 —— Go 版补上之前，「已通知过，跳过」这个状态显示不出来。
   */
  duplicate?: boolean;
}

export interface EmailScanSummary {
  total_mailboxes: number;
  failed_mailboxes: number;
  total_emails: number;
  total_alerts: number;
  alerts_sent: number;
}

/**
 * 扫描结果存在进程内存里，重启后清空：此时 last_update 为 null、
 * days / dry_run 也是 null，页面据此区分「没扫过」和「扫过但没命中」。
 */
export interface EmailScanState {
  last_update: string | null;
  days: number | null;
  dry_run: boolean | null;
  mailboxes: MailboxResult[];
  alerts: EmailAlert[];
  summary: Partial<EmailScanSummary>;
}

// ==================== /api/history/* ====================

export interface HistoryListResponse<T> {
  status: 'success';
  count: number;
  data: T[];
}

/** 数据库里的一条余额快照 */
export interface BalanceHistoryRecord {
  id: number;
  project_id: string;
  project_name: string;
  provider: string;
  balance: number;
  threshold: number | null;
  balance_type: BalanceType;
  need_alarm: boolean;
  timestamp: string;
}

/** 历史告警邮件；入库列名是 matched_keywords，与实时扫描的 keywords 不同名 */
export interface EmailAlertRecord {
  id: number;
  mailbox: string;
  sender: string;
  subject: string;
  date: string;
  service_name: string | null;
  amount: number | null;
  matched_keywords: string[];
  alert_sent: boolean;
  timestamp: string;
}

/** 趋势弹窗里的一个数据点 */
export interface TrendPoint {
  timestamp: string;
  balance: number;
  need_alarm: boolean;
}

/** GET /api/history/trend/<project_id>；不足两个点时没有 change / change_percent */
export interface TrendData {
  project_id: string;
  project_name: string;
  days: number;
  data_points: number;
  current_balance: number;
  min_balance: number;
  max_balance: number;
  avg_balance: number;
  threshold: number;
  first_timestamp: string;
  last_timestamp: string;
  history: TrendPoint[];
  change?: number;
  change_percent?: number;
}

export interface TrendResponse {
  status: 'success';
  data: TrendData;
}

// ==================== /health ====================

export interface HealthResponse {
  status: 'healthy' | 'degraded';
  has_data: boolean;
  is_stale: boolean;
  jobs_healthy: boolean;
  failed_jobs: string[];
  last_update: string | null;
  uptime_seconds: number;
  version: string;
}

// ==================== /api/jobs ====================

export interface JobState {
  name: string;
  description: string;
  schedule: string;
  enabled: boolean;
  next_run: string | null;
  last_run: string | null;
  last_success: string | null;
  last_error: string | null;
  last_duration_seconds: number | null;
  last_detail: Record<string, unknown> | null;
  runs: number;
  failures: number;
}

export interface JobsResponse {
  healthy: boolean;
  jobs: JobState[];
}
