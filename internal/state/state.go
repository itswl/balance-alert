// Package state 保存看板要展示的运行时状态。
//
// 写的是后台调度线程，读的是 HTTP 处理器，真并发。所有读写都在锁内，
// 读取返回副本，调用方可以任意修改而不影响内部状态。
//
// 这些状态只在进程内存里，重启即清空——它们是"上次检查的结果"，不是账本。
// 需要长期留存的东西在 store 里。
package state

import (
	"sync"
	"time"

	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/timeutil"
)

// BalanceState 是 /api/credits 的响应体。
type BalanceState struct {
	LastUpdate *string              `json:"last_update"`
	Projects   []model.CheckResult  `json:"projects"`
	Summary    model.BalanceSummary `json:"summary"`
}

// SubscriptionState 是 /api/subscriptions 的响应体。
type SubscriptionState struct {
	LastUpdate    *string                    `json:"last_update"`
	Subscriptions []model.SubscriptionResult `json:"subscriptions"`
	Summary       SubscriptionSummary        `json:"summary"`
}

// SubscriptionSummary 是订阅视图顶部的计数。
type SubscriptionSummary struct {
	Total     int `json:"total"`
	NeedAlert int `json:"need_alert"`
}

// EmailState 是 /api/email/scan 的响应体。
type EmailState struct {
	LastUpdate *string               `json:"last_update"`
	Days       *int                  `json:"days"`
	DryRun     *bool                 `json:"dry_run"`
	Mailboxes  []model.MailboxResult `json:"mailboxes"`
	Alerts     []model.EmailAlert    `json:"alerts"`
	Summary    EmailSummary          `json:"summary"`
}

// EmailSummary 是邮箱视图顶部的计数。
type EmailSummary struct {
	TotalMailboxes  int `json:"total_mailboxes"`
	FailedMailboxes int `json:"failed_mailboxes"`
	TotalEmails     int `json:"total_emails"`
	TotalAlerts     int `json:"total_alerts"`
	AlertsSent      int `json:"alerts_sent"`
}

// Job 是一个定时任务的运行情况，/api/jobs 的元素。
type Job struct {
	Name         string   `json:"name"`
	Description  string   `json:"description"`
	Schedule     string   `json:"schedule"`
	Enabled      bool     `json:"enabled"`
	NextRun      *string  `json:"next_run"`
	LastRun      *string  `json:"last_run"`
	LastSuccess  *string  `json:"last_success"`
	LastError    *string  `json:"last_error"`
	LastDuration *float64 `json:"last_duration_seconds"`
	LastDetail   any      `json:"last_detail"`
	Runs         int      `json:"runs"`
	Failures     int      `json:"failures"`
}

// JobState 是 /api/jobs 的响应体。healthy = 所有启用任务的上次运行都成功。
type JobState struct {
	Healthy bool  `json:"healthy"`
	Jobs    []Job `json:"jobs"`
}

// Manager 是线程安全的状态容器。
type Manager struct {
	mu        sync.RWMutex
	startTime time.Time
	balance   BalanceState
	subs      SubscriptionState
	email     EmailState
	jobs      map[string]*Job
	jobOrder  []string // 保持登记顺序，/api/jobs 的输出才稳定
}

// New 创建状态容器。
func New() *Manager {
	return &Manager{
		startTime: time.Now(),
		jobs:      make(map[string]*Job),
	}
}

// UptimeSeconds 是进程已经跑了多久。
func (m *Manager) UptimeSeconds() float64 { return time.Since(m.startTime).Seconds() }

// ---------- 余额 ----------

// SetBalance 全量替换余额状态。
func (m *Manager) SetBalance(results []model.CheckResult) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.setBalanceLocked(results)
}

// MergeBalance 按项目名合并部分刷新结果，用于只刷新了一个项目的场景。
func (m *Manager) MergeBalance(results []model.CheckResult) {
	m.mu.Lock()
	defer m.mu.Unlock()

	merged := make([]model.CheckResult, len(m.balance.Projects))
	copy(merged, m.balance.Projects)
	index := make(map[string]int, len(merged))
	for i, p := range merged {
		index[p.Project] = i
	}
	for _, r := range results {
		if i, ok := index[r.Project]; ok {
			merged[i] = r
		} else {
			index[r.Project] = len(merged)
			merged = append(merged, r)
		}
	}
	m.setBalanceLocked(merged)
}

// RemoveBalanceProject 在项目被删除后立刻从看板摘掉，不必等下一轮检查。
func (m *Manager) RemoveBalanceProject(name string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	kept := make([]model.CheckResult, 0, len(m.balance.Projects))
	for _, p := range m.balance.Projects {
		if p.Project != name {
			kept = append(kept, p)
		}
	}
	if len(kept) != len(m.balance.Projects) {
		m.setBalanceLocked(kept)
	}
}

func (m *Manager) setBalanceLocked(results []model.CheckResult) {
	now := timeutil.NowISO()
	m.balance = BalanceState{
		LastUpdate: &now,
		Projects:   results,
		Summary:    model.SummarizeBalance(results),
	}
}

// Balance 返回余额状态的副本。
func (m *Manager) Balance() BalanceState {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := m.balance
	out.Projects = append([]model.CheckResult(nil), m.balance.Projects...)
	return out
}

// ---------- 订阅 ----------

// SetSubscriptions 全量替换订阅状态。
func (m *Manager) SetSubscriptions(results []model.SubscriptionResult) {
	m.mu.Lock()
	defer m.mu.Unlock()

	summary := SubscriptionSummary{Total: len(results)}
	for _, r := range results {
		if r.NeedAlert {
			summary.NeedAlert++
		}
	}
	now := timeutil.NowISO()
	m.subs = SubscriptionState{LastUpdate: &now, Subscriptions: results, Summary: summary}
}

// Subscriptions 返回订阅状态的副本。
func (m *Manager) Subscriptions() SubscriptionState {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := m.subs
	out.Subscriptions = append([]model.SubscriptionResult(nil), m.subs.Subscriptions...)
	return out
}

// ---------- 邮箱扫描 ----------

// SetEmailScan 替换邮箱扫描状态。
func (m *Manager) SetEmailScan(result model.ScanResult) {
	m.mu.Lock()
	defer m.mu.Unlock()

	summary := EmailSummary{
		TotalMailboxes: len(result.Mailboxes),
		TotalAlerts:    len(result.Alerts),
	}
	for _, mb := range result.Mailboxes {
		if mb.Error != nil {
			summary.FailedMailboxes++
		}
		summary.TotalEmails += mb.TotalEmails
	}
	for _, a := range result.Alerts {
		if a.AlertSent {
			summary.AlertsSent++
		}
	}
	now := timeutil.NowISO()
	days, dryRun := result.Days, result.DryRun
	m.email = EmailState{
		LastUpdate: &now, Days: &days, DryRun: &dryRun,
		Mailboxes: result.Mailboxes, Alerts: result.Alerts, Summary: summary,
	}
}

// EmailScan 返回邮箱扫描状态的副本。
func (m *Manager) EmailScan() EmailState {
	m.mu.RLock()
	defer m.mu.RUnlock()
	out := m.email
	out.Mailboxes = append([]model.MailboxResult(nil), m.email.Mailboxes...)
	out.Alerts = append([]model.EmailAlert(nil), m.email.Alerts...)
	return out
}

// ---------- 定时任务 ----------

// RegisterJob 登记任务的静态信息，运行记录由 RecordJobRun 补充。
func (m *Manager) RegisterJob(name, description, schedule string, enabled bool, nextRun time.Time) {
	m.mu.Lock()
	defer m.mu.Unlock()

	job, ok := m.jobs[name]
	if !ok {
		job = &Job{Name: name}
		m.jobs[name] = job
		m.jobOrder = append(m.jobOrder, name)
	}
	job.Description = description
	job.Schedule = schedule
	job.Enabled = enabled
	if enabled {
		job.NextRun = timeutil.UTCISO(nextRun)
	} else {
		job.NextRun = nil
	}
}

// RecordJobRun 记录一次任务运行。
func (m *Manager) RecordJobRun(name string, success bool, startedAt time.Time,
	duration time.Duration, runErr error, detail any, nextRun time.Time) {
	m.mu.Lock()
	defer m.mu.Unlock()

	job, ok := m.jobs[name]
	if !ok {
		job = &Job{Name: name, Enabled: true}
		m.jobs[name] = job
		m.jobOrder = append(m.jobOrder, name)
	}
	job.LastRun = timeutil.UTCISO(startedAt)
	seconds := duration.Seconds()
	job.LastDuration = &seconds
	if job.Enabled {
		job.NextRun = timeutil.UTCISO(nextRun)
	} else {
		job.NextRun = nil
	}
	job.Runs++
	if success {
		job.LastSuccess = job.LastRun
		job.LastError = nil
		job.LastDetail = detail
		return
	}
	job.Failures++
	message := "未知错误"
	if runErr != nil {
		message = runErr.Error()
	}
	job.LastError = &message
}

// Jobs 返回任务状态的副本。
func (m *Manager) Jobs() JobState {
	m.mu.RLock()
	defer m.mu.RUnlock()

	out := JobState{Healthy: true, Jobs: make([]Job, 0, len(m.jobOrder))}
	for _, name := range m.jobOrder {
		job := m.jobs[name]
		if job.Enabled && job.LastError != nil {
			out.Healthy = false
		}
		out.Jobs = append(out.Jobs, *job)
	}
	return out
}

// FailedJobs 返回上次运行失败的启用任务名，/health 用它说明为什么不健康。
func (m *Manager) FailedJobs() []string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	var failed []string
	for _, name := range m.jobOrder {
		if job := m.jobs[name]; job.Enabled && job.LastError != nil {
			failed = append(failed, name)
		}
	}
	return failed
}
