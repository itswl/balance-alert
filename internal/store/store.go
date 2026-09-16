// Package store 是持久化层的契约。
//
// 数据库是可选能力：没开数据库时用 Null()，所有写入静默丢弃、所有查询返回空，
// 于是"不冷却、不留痕、没有历史"，告警本身照发。调用方因此不需要到处判断数据库开没开。
package store

import (
	"context"
	"time"

	"github.com/itswl/balance-alert/internal/model"
)

// Store 是全部持久化操作。实现：SQL（sqlite / postgres / mysql）与 Null。
//
// 约定：Upsert* 是全量写入，不是部分更新。调用方要做"密码留空则不改"这类合并，
// 先读出现有记录合并好再传进来，合并规则只留在 HTTP 层一处。
type Store interface {
	// ---------- 动态配置 ----------

	ListProjects(ctx context.Context) ([]model.Project, error)
	UpsertProject(ctx context.Context, p model.Project) error
	DeleteProject(ctx context.Context, name string) error

	ListSubscriptions(ctx context.Context) ([]model.Subscription, error)
	UpsertSubscription(ctx context.Context, s model.Subscription) error
	DeleteSubscription(ctx context.Context, name string) error

	ListMailboxes(ctx context.Context) ([]model.Mailbox, error)
	UpsertMailbox(ctx context.Context, m model.Mailbox) error
	DeleteMailbox(ctx context.Context, name string) error

	// ---------- 余额历史 ----------

	SaveBalance(ctx context.Context, rec BalanceRecord) error
	// BalanceSeries 返回窗口内全部账户的快照，按时间升序，用于算消耗速率与跑道。
	BalanceSeries(ctx context.Context, days int) ([]model.BalancePoint, error)
	BalanceHistory(ctx context.Context, q BalanceQuery) ([]BalanceRow, error)
	// BalanceTrend 在该项目没有任何数据时返回 nil, nil。
	BalanceTrend(ctx context.Context, projectID string, days int) (*Trend, error)

	// ---------- 告警历史 ----------

	SaveAlert(ctx context.Context, rec AlertRecord) error
	// HasRecentAlert 判断冷却窗口内是否已经发过；within <= 0 一律返回 false。
	HasRecentAlert(ctx context.Context, alertID, alertType string, within time.Duration) (bool, error)
	RecentAlerts(ctx context.Context, q AlertQuery) ([]AlertRow, error)
	AlertStats(ctx context.Context, days int) (*Stats, error)

	// ---------- 邮件告警历史 ----------

	SaveEmailAlert(ctx context.Context, rec EmailAlertRecord) error
	HasRecentEmailAlert(ctx context.Context, mailbox, sender, subject, date string, days int) (bool, error)
	EmailAlerts(ctx context.Context, q EmailAlertQuery) ([]EmailAlertRow, error)

	// Enabled 表示这是真正落库的实现；Null() 返回 false。
	Enabled() bool
	Close() error
}

// ---------- 写入 ----------

// BalanceRecord 一次余额检查的留痕。
type BalanceRecord struct {
	ProjectID   string
	ProjectName string
	Provider    string
	Balance     float64
	Threshold   *float64
	BalanceType string
	NeedAlarm   bool
}

// AlertRecord 一条已发出的告警，作为下次冷却判断的依据。
type AlertRecord struct {
	AlertID   string // 余额用 ProjectID，订阅用 SubscriptionID
	Name      string
	AlertType string // low_balance / low_runway / spend_spike / subscription_renewal / email_alert
	Message   string
	Value     *float64
	Threshold *float64
	Status    string // 空则按 sent 处理
}

// EmailAlertRecord 一封扫描到的告警邮件。
type EmailAlertRecord struct {
	Mailbox     string
	Sender      string
	Subject     string
	Date        string
	ServiceName *string
	Amount      *float64
	Keywords    []string
	AlertSent   bool
}

// ---------- 查询 ----------

// BalanceQuery 余额历史的过滤条件，空字符串表示不过滤。
type BalanceQuery struct {
	ProjectID string
	Provider  string
	Days      int
	Limit     int
}

// AlertQuery 告警历史的过滤条件。
type AlertQuery struct {
	ProjectID string
	AlertType string
	Days      int
	Limit     int
}

// EmailAlertQuery 邮件告警历史的过滤条件。
type EmailAlertQuery struct {
	Mailbox string
	Days    int
	Limit   int
}

// BalanceRow 是 /api/history/balance 的一行。
type BalanceRow struct {
	ID          int64    `json:"id"`
	ProjectID   string   `json:"project_id"`
	ProjectName string   `json:"project_name"`
	Provider    string   `json:"provider"`
	Balance     float64  `json:"balance"`
	Threshold   *float64 `json:"threshold"`
	BalanceType string   `json:"balance_type"`
	NeedAlarm   bool     `json:"need_alarm"`
	Timestamp   string   `json:"timestamp"`
}

// AlertRow 是 /api/history/alerts 的一行。
type AlertRow struct {
	ID             int64    `json:"id"`
	ProjectID      string   `json:"project_id"`
	ProjectName    string   `json:"project_name"`
	AlertType      string   `json:"alert_type"`
	Status         string   `json:"status"`
	Message        string   `json:"message"`
	BalanceValue   *float64 `json:"balance_value"`
	ThresholdValue *float64 `json:"threshold_value"`
	Timestamp      string   `json:"timestamp"`
}

// EmailAlertRow 是 /api/history/email-alerts 的一行。
type EmailAlertRow struct {
	ID              int64    `json:"id"`
	Mailbox         string   `json:"mailbox"`
	Sender          string   `json:"sender"`
	Subject         string   `json:"subject"`
	Date            string   `json:"date"`
	ServiceName     *string  `json:"service_name"`
	Amount          *float64 `json:"amount"`
	MatchedKeywords *string  `json:"matched_keywords"` // JSON 数组文本
	AlertSent       bool     `json:"alert_sent"`
	Timestamp       string   `json:"timestamp"`
}

// TrendPoint 是趋势图上的一个点。
type TrendPoint struct {
	Timestamp string  `json:"timestamp"`
	Balance   float64 `json:"balance"`
	NeedAlarm bool    `json:"need_alarm"`
}

// Trend 是 /api/history/trend/<project_id> 的响应体。
type Trend struct {
	ProjectID      string       `json:"project_id"`
	ProjectName    string       `json:"project_name"`
	Days           int          `json:"days"`
	DataPoints     int          `json:"data_points"`
	CurrentBalance float64      `json:"current_balance"`
	MinBalance     float64      `json:"min_balance"`
	MaxBalance     float64      `json:"max_balance"`
	AvgBalance     float64      `json:"avg_balance"`
	Threshold      float64      `json:"threshold"`
	FirstTimestamp string       `json:"first_timestamp"`
	LastTimestamp  string       `json:"last_timestamp"`
	History        []TrendPoint `json:"history"`
	Change         *float64     `json:"change,omitempty"`
	ChangePercent  *float64     `json:"change_percent,omitempty"`
}

// TopProject 是告警统计里的一项。
type TopProject struct {
	Project string `json:"project"`
	Count   int    `json:"count"`
}

// Stats 是 /api/history/stats 的响应体。
type Stats struct {
	Days        int            `json:"days"`
	TotalAlerts int            `json:"total_alerts"`
	ByType      map[string]int `json:"by_type"`
	TopProjects []TopProject   `json:"top_projects"`
}
