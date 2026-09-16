package store

import (
	"context"
	"time"

	"github.com/itswl/balance-alert/internal/model"
)

// Null 返回一个什么都不存的 Store，用于没开数据库的核心版。
//
// 写入静默丢弃，查询返回空，冷却判断一律放行。于是上层不必到处判断数据库开没开：
// 没有数据库就是"不冷却、不留痕、没有历史"，告警本身照发。
func Null() Store { return nullStore{} }

type nullStore struct{}

func (nullStore) ListProjects(context.Context) ([]model.Project, error)           { return nil, nil }
func (nullStore) UpsertProject(context.Context, model.Project) error              { return ErrDisabled }
func (nullStore) DeleteProject(context.Context, string) error                     { return ErrDisabled }
func (nullStore) ListSubscriptions(context.Context) ([]model.Subscription, error) { return nil, nil }
func (nullStore) UpsertSubscription(context.Context, model.Subscription) error    { return ErrDisabled }
func (nullStore) DeleteSubscription(context.Context, string) error                { return ErrDisabled }
func (nullStore) ListMailboxes(context.Context) ([]model.Mailbox, error)          { return nil, nil }
func (nullStore) UpsertMailbox(context.Context, model.Mailbox) error              { return ErrDisabled }
func (nullStore) DeleteMailbox(context.Context, string) error                     { return ErrDisabled }

func (nullStore) SaveBalance(context.Context, BalanceRecord) error { return nil }

func (nullStore) BalanceSeries(context.Context, int) ([]model.BalancePoint, error) { return nil, nil }

func (nullStore) BalanceHistory(context.Context, BalanceQuery) ([]BalanceRow, error) {
	return nil, nil
}

func (nullStore) BalanceTrend(context.Context, string, int) (*Trend, error) { return nil, nil }

func (nullStore) SaveAlert(context.Context, AlertRecord) error { return nil }

func (nullStore) HasRecentAlert(context.Context, string, string, time.Duration) (bool, error) {
	return false, nil
}

func (nullStore) RecentAlerts(context.Context, AlertQuery) ([]AlertRow, error) { return nil, nil }

func (nullStore) AlertStats(context.Context, int) (*Stats, error) { return nil, nil }

func (nullStore) SaveEmailAlert(context.Context, EmailAlertRecord) error { return nil }

func (nullStore) HasRecentEmailAlert(context.Context, string, string, string, string, int) (bool, error) {
	return false, nil
}

func (nullStore) EmailAlerts(context.Context, EmailAlertQuery) ([]EmailAlertRow, error) {
	return nil, nil
}

func (nullStore) Enabled() bool { return false }
func (nullStore) Close() error  { return nil }
