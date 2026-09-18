package store

import (
	"context"
	"database/sql"
	"time"

	gen "github.com/itswl/quotapulse/internal/store/sqlc/sqlite"
)

// Implementation note.
// Implementation note.
type sqliteQuerier struct{ q *gen.Queries }

func newSQLiteQuerier(db *sql.DB) querier { return sqliteQuerier{q: gen.New(db)} }

func (e sqliteQuerier) listProjectConfigs(ctx context.Context) ([]projectConfigRow, error) {
	rows, err := e.q.ListProjectConfigs(ctx)
	if err != nil {
		return nil, err
	}
	return mapRows(rows, func(r gen.ProjectConfig) projectConfigRow { return projectConfigRow(r) }), nil
}

func (e sqliteQuerier) upsertProjectConfig(ctx context.Context, arg upsertProjectParams) error {
	return e.q.UpsertProjectConfig(ctx, gen.UpsertProjectConfigParams(arg))
}

func (e sqliteQuerier) deleteProjectConfig(ctx context.Context, name string) error {
	return e.q.DeleteProjectConfig(ctx, name)
}

func (e sqliteQuerier) updateProjectAPIKey(ctx context.Context, name, apiKey string) error {
	return e.q.UpdateProjectAPIKey(ctx, gen.UpdateProjectAPIKeyParams{Name: name, ApiKey: apiKey})
}

func (e sqliteQuerier) listSubscriptionConfigs(ctx context.Context) ([]subscriptionConfigRow, error) {
	rows, err := e.q.ListSubscriptionConfigs(ctx)
	if err != nil {
		return nil, err
	}
	return mapRows(rows, func(r gen.SubscriptionConfig) subscriptionConfigRow { return subscriptionConfigRow(r) }), nil
}

func (e sqliteQuerier) upsertSubscriptionConfig(ctx context.Context, arg upsertSubscriptionParams) error {
	return e.q.UpsertSubscriptionConfig(ctx, gen.UpsertSubscriptionConfigParams(arg))
}

func (e sqliteQuerier) deleteSubscriptionConfig(ctx context.Context, name string) error {
	return e.q.DeleteSubscriptionConfig(ctx, name)
}

func (e sqliteQuerier) listEmailConfigs(ctx context.Context) ([]emailConfigRow, error) {
	rows, err := e.q.ListEmailConfigs(ctx)
	if err != nil {
		return nil, err
	}
	return mapRows(rows, func(r gen.EmailConfig) emailConfigRow { return emailConfigRow(r) }), nil
}

func (e sqliteQuerier) upsertEmailConfig(ctx context.Context, arg upsertEmailParams) error {
	return e.q.UpsertEmailConfig(ctx, gen.UpsertEmailConfigParams(arg))
}

func (e sqliteQuerier) deleteEmailConfig(ctx context.Context, name string) error {
	return e.q.DeleteEmailConfig(ctx, name)
}

func (e sqliteQuerier) updateEmailPassword(ctx context.Context, name, password string) error {
	return e.q.UpdateEmailPassword(ctx, gen.UpdateEmailPasswordParams{Name: name, Password: password})
}

func (e sqliteQuerier) insertBalance(ctx context.Context, arg insertBalanceParams) error {
	return e.q.InsertBalanceHistory(ctx, gen.InsertBalanceHistoryParams(arg))
}

func (e sqliteQuerier) listBalanceSeries(ctx context.Context, since time.Time) ([]balanceHistoryRow, error) {
	rows, err := e.q.ListBalanceSeries(ctx, nullTime(since))
	if err != nil {
		return nil, err
	}
	return mapRows(rows, func(r gen.BalanceHistory) balanceHistoryRow { return balanceHistoryRow(r) }), nil
}

func (e sqliteQuerier) listBalanceTrend(ctx context.Context, projectID string, since time.Time) ([]balanceHistoryRow, error) {
	rows, err := e.q.ListBalanceTrend(ctx, gen.ListBalanceTrendParams{ProjectID: projectID, Since: nullTime(since)})
	if err != nil {
		return nil, err
	}
	return mapRows(rows, func(r gen.BalanceHistory) balanceHistoryRow { return balanceHistoryRow(r) }), nil
}

func (e sqliteQuerier) listBalanceHistory(ctx context.Context, since time.Time, projectID, provider string, limit int64) ([]balanceHistoryRow, error) {
	rows, err := e.q.ListBalanceHistory(ctx, gen.ListBalanceHistoryParams{
		Since:     nullTime(since),
		ProjectID: projectID,
		Provider:  provider,
		RowLimit:  limit,
	})
	if err != nil {
		return nil, err
	}
	return mapRows(rows, func(r gen.BalanceHistory) balanceHistoryRow { return balanceHistoryRow(r) }), nil
}

func (e sqliteQuerier) insertAlert(ctx context.Context, arg insertAlertParams) error {
	return e.q.InsertAlertHistory(ctx, gen.InsertAlertHistoryParams(arg))
}

func (e sqliteQuerier) countRecentAlerts(ctx context.Context, alertID, alertType, status string, since time.Time) (int64, error) {
	return e.q.CountRecentAlerts(ctx, gen.CountRecentAlertsParams{
		ProjectID: alertID,
		AlertType: alertType,
		Status:    sql.NullString{String: status, Valid: true},
		Since:     nullTime(since),
	})
}

func (e sqliteQuerier) listAlertHistory(ctx context.Context, since time.Time, projectID, alertType string, limit int64) ([]alertHistoryRow, error) {
	rows, err := e.q.ListAlertHistory(ctx, gen.ListAlertHistoryParams{
		Since:     nullTime(since),
		ProjectID: projectID,
		AlertType: alertType,
		RowLimit:  limit,
	})
	if err != nil {
		return nil, err
	}
	return mapRows(rows, func(r gen.AlertHistory) alertHistoryRow { return alertHistoryRow(r) }), nil
}

func (e sqliteQuerier) countAlerts(ctx context.Context, since time.Time) (int64, error) {
	return e.q.CountAlerts(ctx, nullTime(since))
}

func (e sqliteQuerier) countAlertsByType(ctx context.Context, since time.Time) ([]typeCountRow, error) {
	rows, err := e.q.CountAlertsByType(ctx, nullTime(since))
	if err != nil {
		return nil, err
	}
	return mapRows(rows, func(r gen.CountAlertsByTypeRow) typeCountRow { return typeCountRow(r) }), nil
}

func (e sqliteQuerier) countAlertsByProject(ctx context.Context, since time.Time) ([]projectCountRow, error) {
	rows, err := e.q.CountAlertsByProject(ctx, nullTime(since))
	if err != nil {
		return nil, err
	}
	return mapRows(rows, func(r gen.CountAlertsByProjectRow) projectCountRow { return projectCountRow(r) }), nil
}

func (e sqliteQuerier) insertEmailAlert(ctx context.Context, arg insertEmailAlertParams) error {
	return e.q.InsertEmailAlertHistory(ctx, gen.InsertEmailAlertHistoryParams(arg))
}

func (e sqliteQuerier) countRecentEmailAlerts(ctx context.Context, mailbox, sender, subject, date string, since time.Time) (int64, error) {
	return e.q.CountRecentEmailAlerts(ctx, gen.CountRecentEmailAlertsParams{
		Mailbox: mailbox,
		Sender:  sender,
		Subject: subject,
		Date:    date,
		Since:   nullTime(since),
	})
}

func (e sqliteQuerier) listEmailAlertHistory(ctx context.Context, since time.Time, mailbox string, limit int64) ([]emailAlertHistoryRow, error) {
	rows, err := e.q.ListEmailAlertHistory(ctx, gen.ListEmailAlertHistoryParams{
		Since:    nullTime(since),
		Mailbox:  mailbox,
		RowLimit: limit,
	})
	if err != nil {
		return nil, err
	}
	return mapRows(rows, func(r gen.EmailAlertHistory) emailAlertHistoryRow { return emailAlertHistoryRow(r) }), nil
}
