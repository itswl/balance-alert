// Package model 定义跨模块共用的领域类型。
//
// 这些类型同时是 HTTP API 的响应结构，JSON tag 必须与既有前端约定一致：
// 可能缺失的数值一律用指针，序列化成 null 而不是 0，避免前端把"没查到"当成"余额为零"。
package model

import (
	"crypto/md5"
	"encoding/hex"
	"strings"
)

// 余额类型：展示单位不同，跨项目比较要看比例而不是绝对值。
const (
	TypeBalance = "balance" // 货币余额
	TypeCredits = "credits" // 平台点数
	TypeQuota   = "quota"   // 套餐剩余百分比
)

// Project 一个受监控的账户。
type Project struct {
	Name         string  `json:"name"`
	Provider     string  `json:"provider"`
	APIKey       string  `json:"api_key"`
	Threshold    float64 `json:"threshold"`
	Type         string  `json:"type"`
	OwnerProject *string `json:"owner_project"`
	Enabled      bool    `json:"enabled"`
	FromEnv      bool    `json:"from_env,omitempty"` // 环境变量自动发现，页面上只读
}

// ID 是项目在历史表与告警冷却里的稳定标识。
// 库里的历史记录都是按这个算法存的，换算法等于把既有数据全部认成另一批项目：
// 余额曲线断掉、跑道重新从零开始算、冷却状态全部失效。
func (p Project) ID() string { return ProjectID(p.Provider, p.Name) }

// ProjectID = md5("provider:name")。
func ProjectID(provider, name string) string {
	sum := md5.Sum([]byte(provider + ":" + name))
	return hex.EncodeToString(sum[:])
}

// SubscriptionID = md5("subscription:name")，同样是既有数据的稳定标识，改不得。
func SubscriptionID(name string) string {
	sum := md5.Sum([]byte("subscription:" + name))
	return hex.EncodeToString(sum[:])
}

// Subscription 一条续费提醒。
type Subscription struct {
	Name            string  `json:"name"`
	OwnerProject    *string `json:"owner_project"`
	CycleType       string  `json:"cycle_type"`  // weekly / monthly / yearly
	RenewalDay      int     `json:"renewal_day"` // 周付 1-7，月付 1-31，年付 MMDD
	AlertDaysBefore int     `json:"alert_days_before"`
	Amount          float64 `json:"amount"`
	Enabled         bool    `json:"enabled"`
	LastRenewedDate *string `json:"last_renewed_date"` // YYYY-MM-DD
}

// 订阅周期类型。
const (
	CycleWeekly  = "weekly"
	CycleMonthly = "monthly"
	CycleYearly  = "yearly"
)

// Mailbox 一个被扫描的 IMAP 邮箱。
type Mailbox struct {
	Name     string `json:"name"`
	Host     string `json:"host"`
	Port     int    `json:"port"`
	Username string `json:"username"`
	Password string `json:"password"`
	UseSSL   bool   `json:"use_ssl"`
	Enabled  bool   `json:"enabled"`
	FromEnv  bool   `json:"from_env,omitempty"`
}

// Config 是三段业务清单，由环境变量自动发现与数据库动态配置合并而成。
type Config struct {
	Projects      []Project      `json:"projects"`
	Subscriptions []Subscription `json:"subscriptions"`
	Mailboxes     []Mailbox      `json:"email"`
}

// EnabledProjects 等过滤器只留下 Enabled 为真的条目，关掉的配置项照样留在清单里供页面展示。
func (c Config) EnabledProjects() []Project {
	out := make([]Project, 0, len(c.Projects))
	for _, p := range c.Projects {
		if p.Enabled {
			out = append(out, p)
		}
	}
	return out
}

func (c Config) EnabledSubscriptions() []Subscription {
	out := make([]Subscription, 0, len(c.Subscriptions))
	for _, s := range c.Subscriptions {
		if s.Enabled {
			out = append(out, s)
		}
	}
	return out
}

func (c Config) EnabledMailboxes() []Mailbox {
	out := make([]Mailbox, 0, len(c.Mailboxes))
	for _, m := range c.Mailboxes {
		if m.Enabled {
			out = append(out, m)
		}
	}
	return out
}

// CheckResult 一次余额检查的结果，也是 /api/credits 里 projects[] 的元素。
//
// 失败时 Credits / Threshold / NeedAlarm / Cached 为 nil，序列化成 null。
type CheckResult struct {
	Project      string   `json:"project"`
	OwnerProject *string  `json:"owner_project"`
	Provider     string   `json:"provider"`
	Type         string   `json:"type"`
	Success      bool     `json:"success"`
	Credits      *float64 `json:"credits"`
	Threshold    *float64 `json:"threshold"`
	NeedAlarm    bool     `json:"need_alarm"`
	AlarmSent    bool     `json:"alarm_sent"`
	Error        *string  `json:"error"`
	Cached       bool     `json:"cached"`
	Runway       *Runway  `json:"runway,omitempty"`
}

// BalanceSummary 是看板顶部的计数。
type BalanceSummary struct {
	Total     int `json:"total"`
	Success   int `json:"success"`
	Failed    int `json:"failed"`
	NeedAlarm int `json:"need_alarm"`
}

// SummarizeBalance 统计一批检查结果。
func SummarizeBalance(results []CheckResult) BalanceSummary {
	s := BalanceSummary{Total: len(results)}
	for _, r := range results {
		if r.Success {
			s.Success++
		} else {
			s.Failed++
		}
		if r.NeedAlarm {
			s.NeedAlarm++
		}
	}
	return s
}

// DailySpend 是跑道分析里按本地日期归集的消耗。
type DailySpend struct {
	Date     string  `json:"date"` // YYYY-MM-DD
	Consumed float64 `json:"consumed"`
}

// 置信度：数据太少不下结论，跨度不足一天的估算不用于告警。
const (
	ConfidenceNone   = "none"
	ConfidenceLow    = "low"
	ConfidenceMedium = "medium"
	ConfidenceHigh   = "high"
)

// Runway 一个账户的消耗画像。字段名同时是接口响应的 JSON 键，前端和看板按这套名字取值。
type Runway struct {
	ProjectID      string       `json:"project_id"`
	ProjectName    string       `json:"project_name"`
	Provider       string       `json:"provider"`
	BalanceType    string       `json:"balance_type"`
	CurrentBalance *float64     `json:"current_balance"`
	WindowDays     int          `json:"window_days"`
	DataPoints     int          `json:"data_points"`
	SpanHours      float64      `json:"span_hours"`
	Consumed       float64      `json:"consumed"`
	ToppedUp       float64      `json:"topped_up"`
	BurnPerDay     *float64     `json:"burn_per_day"`
	RunwayDays     *float64     `json:"runway_days"`
	DepletionDate  *string      `json:"depletion_date"`
	Confidence     string       `json:"confidence"`
	Daily          []DailySpend `json:"daily"`
	TodayConsumed  *float64     `json:"today_consumed"`
	BaselineSpend  *float64     `json:"baseline_consumed"`
	SpikeRatio     *float64     `json:"spike_ratio"`
}

// HasEstimate 表示这份画像的日均消耗可用。
func (r *Runway) HasEstimate() bool {
	return r != nil && r.BurnPerDay != nil && r.Confidence != ConfidenceNone
}

// Alertable 表示置信度足以用来发告警（跨度不足一天的不算）。
func (r *Runway) Alertable() bool {
	return r != nil && (r.Confidence == ConfidenceMedium || r.Confidence == ConfidenceHigh)
}

// SubscriptionResult 一条订阅的检查结果，也是 /api/subscriptions 的元素。
type SubscriptionResult struct {
	Name             string  `json:"name"`
	OwnerProject     *string `json:"owner_project"`
	RenewalDay       int     `json:"renewal_day"`
	CycleType        string  `json:"cycle_type"`
	DaysUntilRenewal int     `json:"days_until_renewal"`
	NextRenewalDate  string  `json:"next_renewal_date"` // YYYY-MM-DD
	NeedAlert        bool    `json:"need_alert"`
	AlertSent        bool    `json:"alert_sent"`
	Amount           float64 `json:"amount"`
	AlreadyRenewed   bool    `json:"already_renewed"`
	LastRenewedDate  *string `json:"last_renewed_date"`
}

// MailboxResult 一个邮箱本次扫描的连接与统计情况。
type MailboxResult struct {
	Name        string  `json:"name"`
	Host        string  `json:"host"`
	Port        int     `json:"port"`
	Username    string  `json:"username"`
	TotalEmails int     `json:"total_emails"`
	AlertCount  int     `json:"alert_count"`
	Success     bool    `json:"success"`
	Error       *string `json:"error"`
}

// EmailAlert 一封命中关键词的邮件。
type EmailAlert struct {
	Mailbox     string   `json:"mailbox"`
	Subject     string   `json:"subject"`
	Sender      string   `json:"sender"`
	Date        string   `json:"date"`
	Keywords    []string `json:"keywords"`
	ServiceName *string  `json:"service_name"`
	Amount      *float64 `json:"amount"`
	AlertSent   bool     `json:"alert_sent"`
	// Duplicate 表示这封邮件近期已经通知过，本次跳过。
	// 看板据此显示「已通知过」徽章，好让人知道它不是漏发了。
	Duplicate bool `json:"duplicate,omitempty"`
}

// ScanResult 一次邮箱扫描的完整结果。
type ScanResult struct {
	Days      int             `json:"days"`
	DryRun    bool            `json:"dry_run"`
	Mailboxes []MailboxResult `json:"mailboxes"`
	Alerts    []EmailAlert    `json:"alerts"`
}

// BalancePoint 是余额历史里的一条快照，跑道分析的输入。
type BalancePoint struct {
	ProjectID   string
	ProjectName string
	Provider    string
	BalanceType string
	Balance     float64
	Threshold   *float64
	NeedAlarm   bool
	Timestamp   int64 // Unix 秒，UTC
}

// NormalizeProject 补齐省略字段：provider 统一成小写，name 缺省跟 provider 走，type 按 provider 推导。
func NormalizeProject(p *Project) {
	p.Provider = strings.ToLower(strings.TrimSpace(p.Provider))
	if p.Name == "" {
		p.Name = p.Provider
		if p.Name == "" {
			p.Name = "unknown"
		}
	}
	if p.Type == "" {
		p.Type = DefaultBalanceType(p.Provider)
	}
}

// DefaultBalanceType 按 provider 推导展示用的余额类型。
func DefaultBalanceType(provider string) string {
	switch provider {
	case "openrouter", "uniapi", "wxrank":
		return TypeCredits
	case "glm":
		return TypeQuota
	default:
		return TypeBalance
	}
}

// Ptr 用于给可空字段取地址，避免到处写临时变量。
func Ptr[T any](v T) *T { return &v }

// OwnerProjectOf 把空字符串（含纯空白）归一成 nil，"没填归属项目"只有这一种表示。
func OwnerProjectOf(s string) *string {
	if strings.TrimSpace(s) == "" {
		return nil
	}
	return &s
}
