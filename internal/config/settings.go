// Package config 是配置的唯一入口。
//
// 只有两个来源，一个值只有一个家：
//
//   - 环境变量：密钥、连接、开关、调度参数，以及由 {PROVIDER}_API_KEY / EMAIL_HOST
//     自动发现出来的项目与邮箱
//   - 数据库动态配置：projects / subscriptions / email 三段业务清单，可在页面上增删改
//
// 没有配置文件这一层。数据库里的清单排在前面，环境变量发现的追加在后面，
// 已经声明过的不会重复添加。
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/itswl/balance-alert/internal/timeutil"
)

// Settings 是全部环境变量配置。
//
// 指针字段表示"未通过环境变量设置"，由取值方法回退到内置默认；
// 这样才能区分"没配"和"配成了 0"（例如冷却时间设 0 表示不冷却）。
type Settings struct {
	// 可选能力开关，默认全关，核心版只跑余额告警
	EnableDatabase      bool
	EnableDynamicConfig bool
	EnableHistoryAPI    bool
	EnableSubscriptions bool
	EnablePrometheus    bool
	EnableWebAlarm      bool

	// 调度与并发
	BalanceRefreshIntervalSeconds   *int
	MaxConcurrentChecks             *int
	AlertCooldownSeconds            *int
	SubscriptionAlertCooldownSecond *int

	// 告警通道
	WebhookURL    string
	WebhookType   string
	WebhookSource string

	// 进程内定时任务，时刻按进程本地时区（容器里由 TZ 决定）
	AlertSchedule          string
	EmailScanSchedule      string
	EmailScanDays          int
	WeeklyReportSchedule   string
	EmailAlertKeywords     string
	EmailExtraAlertKeyword string

	// 消耗与跑道分析，需要数据库历史；阈值设 0 关闭对应告警
	BurnRateWindowDays  int
	RunwayAlertDays     float64
	SpendSpikeRatio     float64
	SpendSpikeMinAmount float64

	// HTTP 与扫描
	RequestTimeout   int
	MaxEmailsToScan  int
	ResponseCacheTTL int

	// 日志
	LogLevel  string
	LogFormat string
	LogFile   string

	// 数据库
	DatabaseURL          string
	StrictDatabaseErrors bool
	AutoEncryptOnRead    bool
	ConfigEncryptionKey  string

	// Web 服务
	WebPort       int
	MetricsPort   int
	AppVersion    string
	WebEnableCORS bool
	CORSOrigins   string
	WebAPIKey     string
	// ShutdownDelaySeconds 收到 SIGTERM 后先继续服务这么久再关。
	// K8s 摘 endpoint 和发信号是并行的，不等一会儿会有几个请求打到正在关闭的 Pod 上。
	ShutdownDelaySeconds int

	// 解析好的调度表，启动时校验过
	AlertTimes           []timeutil.ClockTime
	EmailScanTimes       []timeutil.ClockTime
	WeeklyReportTimes    []timeutil.ClockTime
	WeeklyReportWeekdays map[int]bool
}

// Version 是构建时注入的版本号：
//
//	go build -ldflags "-X github.com/itswl/balance-alert/internal/config.Version=v1.2.3"
//
// 没注入时是 dev。/health 与 /live 都会报这个值，线上一眼能看出跑的是哪个构建，
// 而不是所有版本都显示同一个写死的数字。APP_VERSION 环境变量仍可覆盖它。
var Version = "dev"

// 默认值集中在这里，取值方法引用它们。
const (
	DefaultRefreshInterval = 3600
	DefaultMaxConcurrent   = 20
	MaxConcurrentUpper     = 50
	DefaultCooldownSeconds = 86400
)

// Load 从环境变量读出配置，顺带校验。配置写错就让进程起不来，而不是静默跑成别的行为。
func Load() (*Settings, error) {
	e := &envReader{}
	s := &Settings{
		EnableDatabase:      e.boolean("ENABLE_DATABASE", false),
		EnableDynamicConfig: e.boolean("ENABLE_DYNAMIC_CONFIG", false),
		EnableHistoryAPI:    e.boolean("ENABLE_HISTORY_API", false),
		EnableSubscriptions: e.boolean("ENABLE_SUBSCRIPTIONS", false),
		EnablePrometheus:    e.boolean("ENABLE_PROMETHEUS", false),
		EnableWebAlarm:      e.boolean("ENABLE_WEB_ALARM", false),

		BalanceRefreshIntervalSeconds:   e.optionalInt("BALANCE_REFRESH_INTERVAL_SECONDS"),
		MaxConcurrentChecks:             e.optionalInt("MAX_CONCURRENT_CHECKS"),
		AlertCooldownSeconds:            e.optionalInt("ALERT_COOLDOWN_SECONDS"),
		SubscriptionAlertCooldownSecond: e.optionalInt("SUBSCRIPTION_ALERT_COOLDOWN_SECONDS"),

		WebhookURL:    e.text("WEBHOOK_URL", ""),
		WebhookType:   e.text("WEBHOOK_TYPE", ""),
		WebhookSource: e.text("WEBHOOK_SOURCE", ""),

		AlertSchedule:          e.text("ALERT_SCHEDULE", "09:00,15:00"),
		EmailScanSchedule:      e.text("EMAIL_SCAN_SCHEDULE", "10:00"),
		EmailScanDays:          e.integer("EMAIL_SCAN_DAYS", 1),
		WeeklyReportSchedule:   e.text("WEEKLY_REPORT_SCHEDULE", "Mon 09:00"),
		EmailAlertKeywords:     e.text("EMAIL_ALERT_KEYWORDS", ""),
		EmailExtraAlertKeyword: e.text("EMAIL_EXTRA_ALERT_KEYWORDS", ""),

		BurnRateWindowDays:  e.integer("BURN_RATE_WINDOW_DAYS", 7),
		RunwayAlertDays:     e.number("RUNWAY_ALERT_DAYS", 7),
		SpendSpikeRatio:     e.number("SPEND_SPIKE_RATIO", 3),
		SpendSpikeMinAmount: e.number("SPEND_SPIKE_MIN_AMOUNT", 1),

		RequestTimeout:   e.integer("REQUEST_TIMEOUT", 10),
		MaxEmailsToScan:  e.integer("MAX_EMAILS_TO_SCAN", 1000),
		ResponseCacheTTL: e.integer("RESPONSE_CACHE_TTL", 300),

		LogLevel:  e.text("LOG_LEVEL", "INFO"),
		LogFormat: e.text("LOG_FORMAT", "text"),
		LogFile:   e.text("LOG_FILE", ""),

		DatabaseURL:          e.text("DATABASE_URL", "sqlite:///./data/balance_alert.db"),
		StrictDatabaseErrors: e.boolean("STRICT_DATABASE_ERRORS", false),
		AutoEncryptOnRead:    e.boolean("AUTO_ENCRYPT_ON_READ", true),
		ConfigEncryptionKey:  e.text("CONFIG_ENCRYPTION_KEY", ""),

		WebPort:       e.integer("WEB_PORT", 8080),
		MetricsPort:   e.integer("METRICS_PORT", 9100),
		AppVersion:    e.text("APP_VERSION", Version),
		WebEnableCORS: e.boolean("WEB_ENABLE_CORS", false),
		CORSOrigins:   e.text("CORS_ORIGINS", ""),
		WebAPIKey:     strings.TrimSpace(e.text("WEB_API_KEY", "")),

		ShutdownDelaySeconds: e.integer("SHUTDOWN_DELAY_SECONDS", 0),
	}
	if err := e.err(); err != nil {
		return nil, err
	}
	if err := s.parseSchedules(); err != nil {
		return nil, err
	}
	if s.EmailScanDays < 1 || s.EmailScanDays > 30 {
		return nil, fmt.Errorf("EMAIL_SCAN_DAYS 必须在 1-30 之间，当前 %d", s.EmailScanDays)
	}
	if s.BurnRateWindowDays < 1 || s.BurnRateWindowDays > 90 {
		return nil, fmt.Errorf("BURN_RATE_WINDOW_DAYS 必须在 1-90 之间，当前 %d", s.BurnRateWindowDays)
	}
	return s, nil
}

func (s *Settings) parseSchedules() error {
	var err error
	if s.AlertTimes, err = timeutil.ParseDailyTimes(s.AlertSchedule); err != nil {
		return fmt.Errorf("ALERT_SCHEDULE: %w", err)
	}
	if s.EmailScanTimes, err = timeutil.ParseDailyTimes(s.EmailScanSchedule); err != nil {
		return fmt.Errorf("EMAIL_SCAN_SCHEDULE: %w", err)
	}
	if s.WeeklyReportWeekdays, s.WeeklyReportTimes, err = timeutil.ParseWeeklySchedule(s.WeeklyReportSchedule); err != nil {
		return fmt.Errorf("WEEKLY_REPORT_SCHEDULE: %w", err)
	}
	return nil
}

// RefreshInterval 是看板刷新间隔；未设置或非正数时用默认值。
func (s *Settings) RefreshInterval() int {
	if s.BalanceRefreshIntervalSeconds == nil || *s.BalanceRefreshIntervalSeconds <= 0 {
		return DefaultRefreshInterval
	}
	return *s.BalanceRefreshIntervalSeconds
}

// Concurrency 是并发检查数，钳制在 [1, 50]。
func (s *Settings) Concurrency() int {
	n := DefaultMaxConcurrent
	if s.MaxConcurrentChecks != nil {
		n = *s.MaxConcurrentChecks
	}
	return max(1, min(n, MaxConcurrentUpper))
}

// CooldownSeconds 是某类告警的冷却时长。
// 订阅优先读 SUBSCRIPTION_ALERT_COOLDOWN_SECONDS，未设置时回退到 ALERT_COOLDOWN_SECONDS。
func (s *Settings) CooldownSeconds(kind string) int {
	var value *int
	if kind == "subscription" {
		value = s.SubscriptionAlertCooldownSecond
	}
	if value == nil {
		value = s.AlertCooldownSeconds
	}
	if value == nil {
		return DefaultCooldownSeconds
	}
	return max(0, *value)
}

// AlertKeywordOverride 整体替换默认关键词表，为空表示不替换。
func (s *Settings) AlertKeywordOverride() []string { return splitList(s.EmailAlertKeywords) }

// AlertKeywordExtras 在默认词表之上追加。
func (s *Settings) AlertKeywordExtras() []string { return splitList(s.EmailExtraAlertKeyword) }

// CORSOriginList 是逗号分隔的白名单。
func (s *Settings) CORSOriginList() []string { return splitList(s.CORSOrigins) }

func splitList(text string) []string {
	var out []string
	for _, item := range strings.Split(text, ",") {
		if item = strings.TrimSpace(item); item != "" {
			out = append(out, item)
		}
	}
	return out
}

// ---------- 环境变量读取 ----------

// envReader 收集所有解析错误，一次性报出来，而不是第一个就退出。
type envReader struct{ problems []string }

func (e *envReader) err() error {
	if len(e.problems) == 0 {
		return nil
	}
	return fmt.Errorf("环境变量配置有误：\n  %s", strings.Join(e.problems, "\n  "))
}

// raw 读取环境变量；空白值一律视为未设置（.env 里常见的 KEY= 写法）。
func raw(key string) (string, bool) {
	value, ok := os.LookupEnv(key)
	if !ok {
		return "", false
	}
	if value = strings.TrimSpace(value); value == "" {
		return "", false
	}
	return value, true
}

func (e *envReader) text(key, fallback string) string {
	if value, ok := raw(key); ok {
		return value
	}
	return fallback
}

var truthy = map[string]bool{"1": true, "true": true, "yes": true, "on": true, "y": true, "t": true}
var falsy = map[string]bool{"0": true, "false": true, "no": true, "off": true, "n": true, "f": true}

func (e *envReader) boolean(key string, fallback bool) bool {
	value, ok := raw(key)
	if !ok {
		return fallback
	}
	lowered := strings.ToLower(value)
	if truthy[lowered] {
		return true
	}
	if falsy[lowered] {
		return false
	}
	e.problems = append(e.problems, fmt.Sprintf("%s=%q 不是布尔值，可写 true / false", key, value))
	return fallback
}

func (e *envReader) integer(key string, fallback int) int {
	value, ok := raw(key)
	if !ok {
		return fallback
	}
	n, err := strconv.Atoi(value)
	if err != nil {
		e.problems = append(e.problems, fmt.Sprintf("%s=%q 不是整数", key, value))
		return fallback
	}
	return n
}

func (e *envReader) optionalInt(key string) *int {
	value, ok := raw(key)
	if !ok {
		return nil
	}
	n, err := strconv.Atoi(value)
	if err != nil {
		e.problems = append(e.problems, fmt.Sprintf("%s=%q 不是整数", key, value))
		return nil
	}
	return &n
}

func (e *envReader) number(key string, fallback float64) float64 {
	value, ok := raw(key)
	if !ok {
		return fallback
	}
	f, err := strconv.ParseFloat(value, 64)
	if err != nil {
		e.problems = append(e.problems, fmt.Sprintf("%s=%q 不是数字", key, value))
		return fallback
	}
	return f
}
