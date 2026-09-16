package store

import (
	"context"
	"database/sql"
	"time"
)

// 这一组类型是三个 sqlc 生成包的公约数。
//
// sqlc.yaml 刻意让 sqlite / postgres / mysql 三个包生成字段布局完全一致的结构体，
// 所以适配层能用一次结构体转换（balanceHistoryRow(row)）把生成类型搬过来，
// 不必逐字段赋值。哪天某个引擎的列类型被改歪了，转换会直接编译不过——这就是我们要的护栏。
//
// 参数则不强求一致：MySQL 的 LIMIT 不接受具名参数，生成出来的字段名和宽度注定不同，
// 所以 querier 的入参用普通标量，由各引擎自己拼 Params。

type projectConfigRow struct {
	ID           int64
	Name         string
	OwnerProject sql.NullString
	Provider     string
	ApiKey       string
	Threshold    sql.NullFloat64
	Type         sql.NullString
	Enabled      sql.NullBool
	CreatedAt    sql.NullTime
	UpdatedAt    sql.NullTime
}

type subscriptionConfigRow struct {
	ID              int64
	Name            string
	OwnerProject    sql.NullString
	CycleType       sql.NullString
	RenewalDay      sql.NullInt64
	AlertDaysBefore sql.NullInt64
	Amount          sql.NullFloat64
	Enabled         sql.NullBool
	LastRenewedDate sql.NullString
	CreatedAt       sql.NullTime
	UpdatedAt       sql.NullTime
}

type emailConfigRow struct {
	ID        int64
	Name      string
	Host      string
	Port      sql.NullInt64
	Username  string
	Password  string
	UseSsl    sql.NullBool
	Enabled   sql.NullBool
	CreatedAt sql.NullTime
	UpdatedAt sql.NullTime
}

type balanceHistoryRow struct {
	ID          int64
	ProjectID   string
	ProjectName string
	Provider    string
	Balance     float64
	Threshold   sql.NullFloat64
	BalanceType sql.NullString
	NeedAlarm   sql.NullBool
	Timestamp   sql.NullTime
}

type alertHistoryRow struct {
	ID             int64
	ProjectID      string
	ProjectName    string
	AlertType      string
	Status         sql.NullString
	Message        sql.NullString
	BalanceValue   sql.NullFloat64
	ThresholdValue sql.NullFloat64
	Timestamp      sql.NullTime
}

type emailAlertHistoryRow struct {
	ID              int64
	Mailbox         string
	Sender          string
	Subject         string
	Date            string
	ServiceName     sql.NullString
	Amount          sql.NullFloat64
	MatchedKeywords sql.NullString
	AlertSent       sql.NullBool
	Timestamp       sql.NullTime
}

type typeCountRow struct {
	AlertType string
	Count     int64
}

type projectCountRow struct {
	ProjectName string
	Count       int64
}

// ---------- 写入参数 ----------

type upsertProjectParams struct {
	Name         string
	OwnerProject sql.NullString
	Provider     string
	ApiKey       string
	Threshold    sql.NullFloat64
	Type         sql.NullString
	Enabled      sql.NullBool
	CreatedAt    sql.NullTime
	UpdatedAt    sql.NullTime
}

type upsertSubscriptionParams struct {
	Name            string
	OwnerProject    sql.NullString
	CycleType       sql.NullString
	RenewalDay      sql.NullInt64
	AlertDaysBefore sql.NullInt64
	Amount          sql.NullFloat64
	Enabled         sql.NullBool
	LastRenewedDate sql.NullString
	CreatedAt       sql.NullTime
	UpdatedAt       sql.NullTime
}

type upsertEmailParams struct {
	Name      string
	Host      string
	Port      sql.NullInt64
	Username  string
	Password  string
	UseSsl    sql.NullBool
	Enabled   sql.NullBool
	CreatedAt sql.NullTime
	UpdatedAt sql.NullTime
}

type insertBalanceParams struct {
	ProjectID   string
	ProjectName string
	Provider    string
	Balance     float64
	Threshold   sql.NullFloat64
	BalanceType sql.NullString
	NeedAlarm   sql.NullBool
	Timestamp   sql.NullTime
}

type insertAlertParams struct {
	ProjectID      string
	ProjectName    string
	AlertType      string
	Status         sql.NullString
	Message        sql.NullString
	BalanceValue   sql.NullFloat64
	ThresholdValue sql.NullFloat64
	Timestamp      sql.NullTime
}

type insertEmailAlertParams struct {
	Mailbox         string
	Sender          string
	Subject         string
	Date            string
	ServiceName     sql.NullString
	Amount          sql.NullFloat64
	MatchedKeywords sql.NullString
	AlertSent       sql.NullBool
	Timestamp       sql.NullTime
}

// querier 是 sqlStore 唯一依赖的数据库能力，三种引擎各实现一份。
//
// 业务语义（过滤、聚合、解密、时间格式）全部留在 sql.go 里只写一遍，
// 这里只负责把参数递进生成代码、把行搬回来。
type querier interface {
	listProjectConfigs(ctx context.Context) ([]projectConfigRow, error)
	upsertProjectConfig(ctx context.Context, arg upsertProjectParams) error
	deleteProjectConfig(ctx context.Context, name string) error
	updateProjectAPIKey(ctx context.Context, name, apiKey string) error

	listSubscriptionConfigs(ctx context.Context) ([]subscriptionConfigRow, error)
	upsertSubscriptionConfig(ctx context.Context, arg upsertSubscriptionParams) error
	deleteSubscriptionConfig(ctx context.Context, name string) error

	listEmailConfigs(ctx context.Context) ([]emailConfigRow, error)
	upsertEmailConfig(ctx context.Context, arg upsertEmailParams) error
	deleteEmailConfig(ctx context.Context, name string) error
	updateEmailPassword(ctx context.Context, name, password string) error

	insertBalance(ctx context.Context, arg insertBalanceParams) error
	listBalanceSeries(ctx context.Context, since time.Time) ([]balanceHistoryRow, error)
	listBalanceTrend(ctx context.Context, projectID string, since time.Time) ([]balanceHistoryRow, error)
	listBalanceHistory(ctx context.Context, since time.Time, projectID, provider string, limit int64) ([]balanceHistoryRow, error)

	insertAlert(ctx context.Context, arg insertAlertParams) error
	countRecentAlerts(ctx context.Context, alertID, alertType, status string, since time.Time) (int64, error)
	listAlertHistory(ctx context.Context, since time.Time, projectID, alertType string, limit int64) ([]alertHistoryRow, error)
	countAlerts(ctx context.Context, since time.Time) (int64, error)
	countAlertsByType(ctx context.Context, since time.Time) ([]typeCountRow, error)
	countAlertsByProject(ctx context.Context, since time.Time) ([]projectCountRow, error)

	insertEmailAlert(ctx context.Context, arg insertEmailAlertParams) error
	countRecentEmailAlerts(ctx context.Context, mailbox, sender, subject, date string, since time.Time) (int64, error)
	listEmailAlertHistory(ctx context.Context, since time.Time, mailbox string, limit int64) ([]emailAlertHistoryRow, error)
}

// mapRows 把生成包的行切片转成规范行切片。conv 一律是一次结构体转换。
func mapRows[S, D any](src []S, conv func(S) D) []D {
	out := make([]D, len(src))
	for i := range src {
		out[i] = conv(src[i])
	}
	return out
}

// nullTime 把一个时刻包成查询参数。时间列在建表时是可空的，生成代码因此要 sql.NullTime。
func nullTime(t time.Time) sql.NullTime {
	return sql.NullTime{Time: t.UTC(), Valid: true}
}
