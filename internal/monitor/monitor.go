// Package monitor 查各平台余额，判断要不要告警。
//
// 一轮检查分两步：先按静态阈值判断"现在够不够"，整轮结束后再交给 runway 做趋势分析
// （跑道见底、消耗突增）。趋势依赖历史，必须等所有账户都查完、都入库之后再算。
package monitor

import (
	"context"
	"crypto/md5"
	"encoding/hex"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/itswl/balance-alert/internal/config"
	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/notify"
	"github.com/itswl/balance-alert/internal/provider"
	"github.com/itswl/balance-alert/internal/runway"
	"github.com/itswl/balance-alert/internal/store"
)

// Monitor 一轮余额检查所需的全部依赖。
type Monitor struct {
	Settings *config.Settings
	Resolver *config.Resolver
	Store    store.Store
	Notifier notify.Notifier
	Client   *provider.Client
	Alerter  *runway.Alerter
	Log      *slog.Logger

	// OnNotify 每发一次通知回调一次，用于记指标。可空。
	OnNotify func(kind string, ok bool)

	cache responseCache
}

// Outcome 是一轮检查的产物。
type Outcome struct {
	Results []model.CheckResult
	Runways map[string]model.Runway
	Sent    runway.Sent
}

// Run 检查项目余额。projectName 为空表示检查所有启用的项目。
// dryRun 时一切照跑，只是不真的发通知。
func (m *Monitor) Run(ctx context.Context, projectName string, dryRun bool) (Outcome, error) {
	started := time.Now()
	cfg := m.Resolver.Load(ctx)

	projects := m.selectProjects(cfg, projectName)
	if len(projects) == 0 {
		if projectName != "" {
			return Outcome{}, fmt.Errorf("未找到项目: %s", projectName)
		}
		m.log().Warn("没有可监控的项目，检查 {PROVIDER}_API_KEY 或数据库动态配置")
		return Outcome{}, nil
	}

	m.log().Info("开始监控", "projects", len(projects), "dry_run", dryRun)
	results := m.checkAll(ctx, projects, dryRun)

	outcome := Outcome{Results: results}
	outcome.Runways, outcome.Sent = m.analyze(ctx, results, dryRun)

	m.logSummary(results, time.Since(started))
	return outcome, nil
}

// selectProjects 指定了项目名就只查那一个（忽略启用状态，页面上手动刷新要能刷到它），
// 否则查全部启用的项目。
func (m *Monitor) selectProjects(cfg model.Config, projectName string) []model.Project {
	if projectName == "" {
		return cfg.EnabledProjects()
	}
	for _, p := range cfg.Projects {
		if p.Name == projectName {
			return []model.Project{p}
		}
	}
	return nil
}

// checkAll 并发检查，结果按输入顺序返回，看板上的卡片顺序才稳定。
func (m *Monitor) checkAll(ctx context.Context, projects []model.Project, dryRun bool) []model.CheckResult {
	workers := min(m.Settings.Concurrency(), len(projects))
	m.log().Info("并发检查", "workers", workers, "projects", len(projects))

	results := make([]model.CheckResult, len(projects))
	jobs := make(chan int)
	var wg sync.WaitGroup

	for range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := range jobs {
				results[i] = m.CheckProject(ctx, projects[i], dryRun)
			}
		}()
	}
	for i := range projects {
		jobs <- i
	}
	close(jobs)
	wg.Wait()
	return results
}

// CheckProject 查一个账户的余额并判断是否需要告警。
func (m *Monitor) CheckProject(ctx context.Context, p model.Project, dryRun bool) model.CheckResult {
	m.log().Info("检查项目", "project", p.Name, "provider", p.Provider, "threshold", p.Threshold)

	adapter, err := provider.New(p.Provider, p.APIKey, m.Client)
	if err != nil {
		return m.failure(p, err)
	}

	cacheKey := cacheKeyFor(p.Provider, p.APIKey)
	ttl := time.Duration(m.Settings.ResponseCacheTTL) * time.Second
	credits, cached := m.cache.get(cacheKey, ttl)
	if cached {
		m.log().Info("使用缓存结果", "project", p.Name, "ttl_seconds", m.Settings.ResponseCacheTTL)
	} else {
		if credits, err = adapter.Fetch(ctx); err != nil {
			m.log().Error("获取余额失败", "project", p.Name, "error", err)
			return m.failure(p, err)
		}
		if ttl > 0 {
			m.cache.set(cacheKey, credits)
		}
	}
	m.log().Info("当前余额", "project", p.Name, "credits", credits)

	result := model.CheckResult{
		Project:      p.Name,
		OwnerProject: p.OwnerProject,
		Provider:     p.Provider,
		Type:         p.Type,
		Success:      true,
		Credits:      &credits,
		Threshold:    model.Ptr(p.Threshold),
		NeedAlarm:    credits < p.Threshold,
		Cached:       cached,
	}

	projectID := p.ID()
	if err := m.Store.SaveBalance(ctx, store.BalanceRecord{
		ProjectID: projectID, ProjectName: p.Name, Provider: p.Provider,
		Balance: credits, Threshold: model.Ptr(p.Threshold),
		BalanceType: p.Type, NeedAlarm: result.NeedAlarm,
	}); err != nil {
		m.log().Warn("记录余额历史失败", "project", p.Name, "error", err)
	}

	if !result.NeedAlarm {
		m.log().Info("余额充足", "project", p.Name, "credits", credits, "threshold", p.Threshold)
		return result
	}

	m.log().Warn("余额不足", "project", p.Name, "credits", credits, "threshold", p.Threshold)
	if dryRun {
		return result
	}
	result.AlarmSent = m.sendBalanceAlert(ctx, p, projectID, credits)
	return result
}

// sendBalanceAlert 发余额不足告警；冷却窗口内跳过，发出去了才留痕。
func (m *Monitor) sendBalanceAlert(ctx context.Context, p model.Project, projectID string, credits float64) bool {
	cooldown := time.Duration(m.Settings.CooldownSeconds("balance")) * time.Second
	cooling, err := m.Store.HasRecentAlert(ctx, projectID, "low_balance", cooldown)
	if err != nil {
		m.log().Warn("查询告警冷却失败，按未冷却处理", "project", p.Name, "error", err)
	}
	if cooling {
		m.log().Info("告警仍在冷却窗口内，跳过重复通知", "project", p.Name, "cooldown", cooldown)
		return false
	}
	if m.Notifier == nil {
		m.log().Error("未配置 webhook 地址")
		return false
	}

	msg := notify.BalanceAlert(p.Name, p.OwnerProject, provider.DisplayName(p.Provider), credits, p.Threshold)
	sendErr := m.Notifier.Send(ctx, msg)
	if m.OnNotify != nil {
		m.OnNotify(msg.Kind, sendErr == nil)
	}
	if sendErr != nil {
		m.log().Error("发送余额告警失败", "project", p.Name, "error", sendErr)
		return false
	}

	if err := m.Store.SaveAlert(ctx, store.AlertRecord{
		AlertID: projectID, Name: p.Name, AlertType: "low_balance",
		Message:   fmt.Sprintf("余额不足: %v < %v", credits, p.Threshold),
		Value:     &credits,
		Threshold: model.Ptr(p.Threshold),
	}); err != nil {
		m.log().Warn("记录告警失败", "project", p.Name, "error", err)
	}
	return true
}

// analyze 整轮检查之后的趋势分析：挂画像 + 发跑道 / 突增告警。
// 没开数据库就没有历史，这里自然什么都不做。
func (m *Monitor) analyze(ctx context.Context, results []model.CheckResult, dryRun bool) (map[string]model.Runway, runway.Sent) {
	series, err := m.Store.BalanceSeries(ctx, m.Settings.BurnRateWindowDays)
	if err != nil {
		m.log().Warn("读取余额历史失败，跳过趋势分析", "error", err)
		return nil, runway.Sent{}
	}
	runways := runway.ComputeAll(series, m.Settings.BurnRateWindowDays, time.Now())
	if len(runways) == 0 {
		return nil, runway.Sent{}
	}
	runway.Attach(results, runways)

	if m.Alerter == nil {
		return runways, runway.Sent{}
	}
	return runways, m.Alerter.Check(ctx, results, dryRun)
}

func (m *Monitor) failure(p model.Project, err error) model.CheckResult {
	message := err.Error()
	return model.CheckResult{
		Project: p.Name, OwnerProject: p.OwnerProject, Provider: p.Provider,
		Type: p.Type, Success: false, Error: &message,
	}
}

func (m *Monitor) logSummary(results []model.CheckResult, elapsed time.Duration) {
	summary := model.SummarizeBalance(results)
	m.log().Info("检查汇总",
		"total", summary.Total, "success", summary.Success,
		"failed", summary.Failed, "need_alarm", summary.NeedAlarm,
		"seconds", elapsed.Seconds())

	for _, r := range results {
		if !r.Success {
			m.log().Error("检查失败", "project", r.Project, "error", deref(r.Error))
			continue
		}
		if r.NeedAlarm {
			m.log().Warn("需告警", "project", r.Project, "credits", deref(r.Credits), "threshold", deref(r.Threshold), "sent", r.AlarmSent)
		}
	}
}

func (m *Monitor) log() *slog.Logger {
	if m.Log != nil {
		return m.Log
	}
	return slog.Default()
}

func deref[T any](p *T) T {
	var zero T
	if p == nil {
		return zero
	}
	return *p
}

// cacheKeyFor 用密钥摘要而不是密钥本身当 key，日志或调试打印时不会泄露。
func cacheKeyFor(providerKey, apiKey string) string {
	sum := md5.Sum([]byte(apiKey))
	return providerKey + ":" + hex.EncodeToString(sum[:])
}

// responseCache 缓存同一 provider+key 的余额结果，防止页面上手动连点把上游打爆。
type responseCache struct {
	mu   sync.Mutex
	data map[string]cacheEntry
}

type cacheEntry struct {
	at      time.Time
	credits float64
}

func (c *responseCache) get(key string, ttl time.Duration) (float64, bool) {
	if ttl <= 0 {
		return 0, false
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	entry, ok := c.data[key]
	if !ok || time.Since(entry.at) >= ttl {
		delete(c.data, key)
		return 0, false
	}
	return entry.credits, true
}

func (c *responseCache) set(key string, credits float64) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.data == nil {
		c.data = make(map[string]cacheEntry)
	}
	c.data[key] = cacheEntry{at: time.Now(), credits: credits}
}
