// Package app 把各模块装配成一个可运行的服务。
//
// 装配逻辑单独成包而不是堆在 main 里，是为了能在测试里整体拉起来跑。
package app

import (
	"context"
	"fmt"
	"io/fs"
	"log/slog"
	"net/http"
	"time"

	"github.com/itswl/balance-alert/internal/config"
	"github.com/itswl/balance-alert/internal/httpapi"
	"github.com/itswl/balance-alert/internal/mailscan"
	"github.com/itswl/balance-alert/internal/metrics"
	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/monitor"
	"github.com/itswl/balance-alert/internal/notify"
	"github.com/itswl/balance-alert/internal/provider"
	"github.com/itswl/balance-alert/internal/report"
	"github.com/itswl/balance-alert/internal/runway"
	"github.com/itswl/balance-alert/internal/scheduler"
	"github.com/itswl/balance-alert/internal/state"
	"github.com/itswl/balance-alert/internal/store"
	"github.com/itswl/balance-alert/internal/subscription"
)

// App 持有装配好的全部组件。
type App struct {
	Settings *config.Settings
	Log      *slog.Logger
	Store    store.Store
	Resolver *config.Resolver
	Notifier notify.Notifier
	Metrics  *metrics.Collector
	State    *state.Manager
	Monitor  *monitor.Monitor
	Subs     *subscription.Checker
	Scanner  *mailscan.Scanner
	Server   *httpapi.Server

	scheduler *scheduler.Scheduler
}

// New 按配置装配服务。assets 是打包好的前端产物，可为 nil。
func New(settings *config.Settings, log *slog.Logger, assets fs.FS) (*App, error) {
	st, err := openStore(settings, log)
	if err != nil {
		return nil, err
	}

	httpClient := &http.Client{Timeout: time.Duration(settings.RequestTimeout) * time.Second}
	notifier, err := notify.New(settings.WebhookURL, settings.WebhookType, settings.WebhookSource, httpClient)
	if err != nil {
		return nil, fmt.Errorf("Webhook 配置有误: %w", err)
	}
	if notifier == nil {
		log.Warn("未设置 WEBHOOK_URL，余额不足时无法发出告警")
	}

	app := &App{
		Settings: settings,
		Log:      log,
		Store:    st,
		Resolver: config.NewResolver(settings, st, log),
		Notifier: notifier,
		Metrics:  metrics.New(nil),
		State:    state.New(),
	}

	app.Monitor = &monitor.Monitor{
		Settings: settings,
		Resolver: app.Resolver,
		Store:    st,
		Notifier: notifier,
		Client:   provider.NewClient(time.Duration(settings.RequestTimeout) * time.Second),
		Log:      log,
		OnNotify: app.Metrics.RecordNotification,
		Alerter: &runway.Alerter{
			Store: st, Notifier: notifier, Log: log,
			RunwayAlertDays: settings.RunwayAlertDays,
			SpikeRatio:      settings.SpendSpikeRatio,
			SpikeMinAmount:  settings.SpendSpikeMinAmount,
			Cooldown:        time.Duration(settings.CooldownSeconds("balance")) * time.Second,
		},
	}
	app.Subs = &subscription.Checker{
		Store: st, Notifier: notifier, Log: log,
		Cooldown: time.Duration(settings.CooldownSeconds("subscription")) * time.Second,
		OnNotify: app.Metrics.RecordNotification,
	}
	app.Scanner = &mailscan.Scanner{
		Store: st, Notifier: notifier, Log: log,
		Keywords:  keywords(settings),
		MaxEmails: settings.MaxEmailsToScan,
		Timeout:   time.Duration(settings.RequestTimeout) * time.Second,
		OnNotify:  app.Metrics.RecordNotification,
	}
	app.Server = &httpapi.Server{
		Settings: settings, Resolver: app.Resolver, Store: st, State: app.State,
		Monitor: app.Monitor, Subs: app.Subs, Scanner: app.Scanner,
		Log: log, Assets: assets,
		OnBalanceUpdated:      app.Metrics.UpdateBalance,
		OnSubscriptionUpdated: app.Metrics.UpdateSubscriptions,
		OnEmailScanned:        app.Metrics.UpdateEmailScan,
	}
	return app, nil
}

// keywords 组合出最终的告警关键词表：override 整体替换默认，extras 在其上追加。
func keywords(settings *config.Settings) []string {
	base := settings.AlertKeywordOverride()
	if len(base) == 0 {
		base = mailscan.DefaultAlertKeywords
	}
	return append(append([]string(nil), base...), settings.AlertKeywordExtras()...)
}

// openStore 开数据库；没开启用时返回 Null 实现，上层不必判断。
func openStore(settings *config.Settings, log *slog.Logger) (store.Store, error) {
	if !settings.EnableDatabase {
		return store.Null(), nil
	}
	st, err := store.Open(context.Background(), store.Options{
		DatabaseURL:       settings.DatabaseURL,
		EncryptionKey:     settings.ConfigEncryptionKey,
		AutoEncryptOnRead: settings.AutoEncryptOnRead,
	})
	if err != nil {
		// 数据库挂了不该让余额告警停摆，除非用户明确要求严格模式
		if settings.StrictDatabaseErrors {
			return nil, fmt.Errorf("数据库初始化失败: %w", err)
		}
		log.Warn("数据库初始化失败，将跳过历史数据与动态配置", "error", err)
		return store.Null(), nil
	}
	log.Info("数据库已初始化")
	return st, nil
}

// Close 释放资源。
func (a *App) Close() error { return a.Store.Close() }

// ---------- 定时任务 ----------

// BuildTasks 定义四个定时任务，与旧版一一对应。
func (a *App) BuildTasks() []*scheduler.Task {
	settings := a.Settings

	webAlarmNote := "只查不发告警"
	if settings.EnableWebAlarm {
		webAlarmNote = "会发送真实告警"
	}

	return []*scheduler.Task{
		{
			Name:        "dashboard_refresh",
			Description: fmt.Sprintf("刷新看板的余额与订阅状态（%s）", webAlarmNote),
			Interval:    time.Duration(settings.RefreshInterval()) * time.Second,
			RunAtStart:  true,
			Run: func(ctx context.Context) (any, error) {
				return a.refreshAll(ctx, !settings.EnableWebAlarm)
			},
		},
		{
			Name:        "alert_check",
			Description: "余额与订阅告警检查，发送真实通知",
			DailyTimes:  settings.AlertTimes,
			Run: func(ctx context.Context) (any, error) {
				return a.refreshAll(ctx, false)
			},
		},
		{
			Name:        "email_scan",
			Description: fmt.Sprintf("扫描邮箱最近 %d 天的欠费 / 续费邮件，发送真实通知", settings.EmailScanDays),
			DailyTimes:  settings.EmailScanTimes,
			Run: func(ctx context.Context) (any, error) {
				return a.ScanMailboxes(ctx, settings.EmailScanDays, false)
			},
		},
		{
			Name:        "weekly_report",
			Description: "推送一周的消耗、跑道与待续费汇总",
			DailyTimes:  settings.WeeklyReportTimes,
			Weekdays:    settings.WeeklyReportWeekdays,
			Run:         a.SendWeeklyReport,
		},
	}
}

// refreshAll 查一遍余额与订阅，并把结果写进看板状态与指标。
func (a *App) refreshAll(ctx context.Context, dryRun bool) (any, error) {
	outcome, err := a.Monitor.Run(ctx, "", dryRun)
	if err != nil {
		return nil, err
	}
	a.State.SetBalance(outcome.Results)
	a.Metrics.UpdateBalance(outcome.Results)
	summary := model.SummarizeBalance(outcome.Results)

	detail := map[string]any{
		"projects": summary.Total, "failed": summary.Failed,
		"need_alarm": summary.NeedAlarm, "dry_run": dryRun,
	}

	subs := a.refreshSubscriptions(ctx, dryRun)
	detail["subscriptions"] = len(subs)
	needAlert := 0
	for _, s := range subs {
		if s.NeedAlert {
			needAlert++
		}
	}
	detail["need_alert"] = needAlert
	return detail, nil
}

// refreshSubscriptions 订阅是可选能力，没开时直接给空结果。
func (a *App) refreshSubscriptions(ctx context.Context, dryRun bool) []model.SubscriptionResult {
	if !a.Settings.EnableSubscriptions {
		return nil
	}
	cfg := a.Resolver.Load(ctx)
	results := a.Subs.Check(ctx, cfg.EnabledSubscriptions(), dryRun)
	a.State.SetSubscriptions(results)
	a.Metrics.UpdateSubscriptions(results)
	return results
}

// ScanMailboxes 扫描所有启用的邮箱。
func (a *App) ScanMailboxes(ctx context.Context, days int, dryRun bool) (any, error) {
	cfg := a.Resolver.Load(ctx)
	mailboxes := cfg.EnabledMailboxes()
	if len(mailboxes) == 0 {
		return map[string]any{"mailboxes": 0, "skipped": "未配置邮箱"}, nil
	}

	result := a.Scanner.Scan(ctx, mailboxes, days, dryRun)
	a.State.SetEmailScan(result)
	a.Metrics.UpdateEmailScan(result)

	summary := a.State.EmailScan().Summary
	return map[string]any{
		"mailboxes": summary.TotalMailboxes, "failed_mailboxes": summary.FailedMailboxes,
		"emails": summary.TotalEmails, "alerts": summary.TotalAlerts,
		"alerts_sent": summary.AlertsSent, "dry_run": dryRun,
	}, nil
}

// SendWeeklyReport 汇总本周数据并推一张卡片。
func (a *App) SendWeeklyReport(ctx context.Context) (any, error) {
	balance := a.State.Balance()
	subs := a.State.Subscriptions()
	email := a.State.EmailScan()

	series, err := a.Store.BalanceSeries(ctx, report.WindowDays)
	if err != nil {
		a.Log.Warn("读取余额历史失败，周报只报余额部分", "error", err)
	}
	runways := runway.ComputeAll(series, report.WindowDays, time.Now())

	summary := report.Build(balance.Projects, subs.Subscriptions,
		email.Mailboxes, email.Summary.TotalAlerts, runways, time.Now())

	sent := false
	if a.Notifier == nil {
		a.Log.Error("未配置 webhook 地址，周报未发送")
	} else {
		msg := notify.Custom("余额周报", []string{report.Render(summary)}, "weekly_report")
		sendErr := a.Notifier.Send(ctx, msg)
		a.Metrics.RecordNotification(msg.Kind, sendErr == nil)
		if sendErr != nil {
			a.Log.Error("周报发送失败", "error", sendErr)
		} else {
			sent = true
		}
	}

	return map[string]any{
		"accounts": summary.Accounts.Total, "consumed": summary.TotalConsumed,
		"upcoming_amount": summary.UpcomingAmount, "sent": sent,
	}, nil
}

// StartScheduler 登记任务并起调度循环。
func (a *App) StartScheduler(ctx context.Context) {
	tasks := a.BuildTasks()
	a.scheduler = scheduler.New(tasks, a.onJobResult, a.Log)

	for _, task := range tasks {
		a.State.RegisterJob(task.Name, task.Description, task.ScheduleText(), task.Enabled(), task.NextRun())
		a.Log.Info("定时任务", "name", task.Name, "schedule", task.ScheduleText(), "description", task.Description)
	}
	a.scheduler.Start(ctx)
}

// onJobResult 把每次运行的结果同时交给看板状态和指标。
func (a *App) onJobResult(result scheduler.Result) {
	a.State.RecordJobRun(result.Name, result.Success, result.StartedAt,
		result.Duration, result.Err, result.Detail, result.NextRun)
	a.Metrics.RecordJobRun(result.Name, result.Success, result.StartedAt, result.Duration)
}

// StopScheduler 停掉调度循环。
func (a *App) StopScheduler() {
	if a.scheduler != nil {
		a.scheduler.Stop(5 * time.Second)
	}
}

// ServeMetrics 在独立端口暴露 /metrics。
func (a *App) ServeMetrics(ctx context.Context) {
	if !a.Settings.EnablePrometheus {
		return
	}
	addr := fmt.Sprintf(":%d", a.Settings.MetricsPort)
	mux := http.NewServeMux()
	mux.Handle("GET /metrics", a.Metrics.Handler())
	server := &http.Server{Addr: addr, Handler: mux, ReadHeaderTimeout: 10 * time.Second}

	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdownCtx)
	}()
	go func() {
		a.Log.Info("Prometheus 指标已启动", "addr", addr+"/metrics")
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			a.Log.Error("指标服务异常退出", "error", err)
		}
	}()
}
