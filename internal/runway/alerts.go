package runway

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"
	"strings"
	"time"

	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/notify"
	"github.com/itswl/balance-alert/internal/store"
)

// Alerter 发跑道见底与消耗突增两类趋势告警。
//
// 它们都依赖历史，数据不足时自动沉默——宁可不报，也不能拿一小时的数据推断"还剩三天"。
type Alerter struct {
	Store    store.Store
	Notifier notify.Notifier
	Log      *slog.Logger

	// RunwayAlertDays 跑道低于这个天数就提醒，设 0 关闭
	RunwayAlertDays float64
	// SpikeRatio 今日消耗达到日常中位数的几倍算突增，设 0 关闭
	SpikeRatio float64
	// SpikeMinAmount 今日消耗低于这个绝对值不报突增，避免噪音
	SpikeMinAmount float64
	// Cooldown 同一条告警的冷却时长
	Cooldown time.Duration
}

// Sent 是本轮各类告警的发送计数。
type Sent struct {
	Runway int
	Spike  int
}

// notice 是一条待发的趋势告警。alertType 用于冷却去重，kind 用于指标分类。
type notice struct {
	alertType string
	kind      string
	title     string
	lines     []string
	message   string
	value     *float64
	threshold *float64
}

// Check 逐个账户判断要不要发趋势告警。dryRun 时只判断不发送。
func (a *Alerter) Check(ctx context.Context, results []model.CheckResult, dryRun bool) Sent {
	var sent Sent
	if a.RunwayAlertDays <= 0 && a.SpikeRatio <= 0 {
		return sent
	}

	for i := range results {
		result := &results[i]
		if !result.Success || !result.Runway.Alertable() {
			continue
		}
		projectID := model.ProjectID(result.Provider, result.Project)

		if a.runwayDue(result) {
			a.log().Warn("跑道不足", "project", result.Project,
				"runway_days", *result.Runway.RunwayDays, "limit", a.RunwayAlertDays)
			if !dryRun && a.emit(ctx, projectID, result.Project, a.runwayNotice(result)) {
				sent.Runway++
			}
		}
		if a.spikeDue(result.Runway) {
			a.log().Warn("消耗突增", "project", result.Project, "ratio", *result.Runway.SpikeRatio)
			if !dryRun && a.emit(ctx, projectID, result.Project, a.spikeNotice(result)) {
				sent.Spike++
			}
		}
	}
	return sent
}

// runwayDue 判断跑道是否见底。已经在报余额不足的账户不重复打扰。
func (a *Alerter) runwayDue(result *model.CheckResult) bool {
	return a.RunwayAlertDays > 0 && result.Runway.RunwayDays != nil &&
		*result.Runway.RunwayDays <= a.RunwayAlertDays && !result.NeedAlarm
}

// spikeDue 判断消耗是否异常放大。比例再大，绝对值太小也不值得打扰。
func (a *Alerter) spikeDue(r *model.Runway) bool {
	if a.SpikeRatio <= 0 || r.SpikeRatio == nil || *r.SpikeRatio < a.SpikeRatio {
		return false
	}
	today := 0.0
	if r.TodayConsumed != nil {
		today = *r.TodayConsumed
	}
	return today >= a.SpikeMinAmount
}

// emit 发送并留痕；冷却窗口内直接跳过，发失败不留痕（下次还能再试）。
func (a *Alerter) emit(ctx context.Context, projectID, projectName string, n notice) bool {
	cooling, err := a.Store.HasRecentAlert(ctx, projectID, n.alertType, a.Cooldown)
	if err != nil {
		a.log().Warn("查询告警冷却失败，按未冷却处理", "error", err)
	}
	if cooling {
		return false
	}
	if a.Notifier == nil {
		a.log().Error("未配置 webhook 地址")
		return false
	}
	if err := a.Notifier.Send(ctx, notify.Message{Title: n.title, Lines: n.lines, Kind: n.kind}); err != nil {
		a.log().Error("发送趋势告警失败", "project", projectName, "kind", n.kind, "error", err)
		return false
	}
	if err := a.Store.SaveAlert(ctx, store.AlertRecord{
		AlertID: projectID, Name: projectName, AlertType: n.alertType,
		Message: n.message, Value: n.value, Threshold: n.threshold,
	}); err != nil {
		a.log().Warn("记录告警失败", "project", projectName, "error", err)
	}
	return true
}

func (a *Alerter) runwayNotice(result *model.CheckResult) notice {
	r := result.Runway
	return notice{
		alertType: "low_runway",
		kind:      "runway",
		title:     "余额跑道不足: " + result.Project,
		lines: append(head(result),
			"**服务商**: "+result.Provider,
			"**当前余额**: "+thousands(deref(r.CurrentBalance), 2),
			fmt.Sprintf("**日均消耗**: %s（最近 %d 天）", thousands(deref(r.BurnPerDay), 2), r.WindowDays),
			fmt.Sprintf("**预计耗尽**: %s，还剩 %.1f 天（阈值 %s 天）",
				deref(r.DepletionDate), deref(r.RunwayDays), trimFloat(a.RunwayAlertDays)),
		),
		message:   fmt.Sprintf("跑道不足: %.1f 天，预计 %s 耗尽", deref(r.RunwayDays), deref(r.DepletionDate)),
		value:     r.CurrentBalance,
		threshold: model.Ptr(a.RunwayAlertDays),
	}
}

func (a *Alerter) spikeNotice(result *model.CheckResult) notice {
	r := result.Runway
	lines := append(head(result),
		"**今日消耗**: "+thousands(deref(r.TodayConsumed), 2),
		fmt.Sprintf("**日常水平**: %s（最近 %d 天中位数）", thousands(deref(r.BaselineSpend), 2), r.WindowDays),
		fmt.Sprintf("**放大倍数**: %.1fx", deref(r.SpikeRatio)),
		"**当前余额**: "+thousands(deref(r.CurrentBalance), 2),
	)
	if r.RunwayDays != nil {
		lines = append(lines, fmt.Sprintf("**按当前速率**: 还剩 %.1f 天", *r.RunwayDays))
	}
	return notice{
		alertType: "spend_spike",
		kind:      "spend_spike",
		title:     "消耗异常放大: " + result.Project,
		lines:     lines,
		message: fmt.Sprintf("消耗突增: 今日 %s，是日常的 %.1f 倍",
			thousands(deref(r.TodayConsumed), 2), deref(r.SpikeRatio)),
		value:     r.TodayConsumed,
		threshold: r.BaselineSpend,
	}
}

func head(result *model.CheckResult) []string {
	lines := []string{"**账户**: " + result.Project}
	if result.OwnerProject != nil && *result.OwnerProject != "" {
		lines = append(lines, "**所属项目**: "+*result.OwnerProject)
	}
	return lines
}

func (a *Alerter) log() *slog.Logger {
	if a.Log != nil {
		return a.Log
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

// thousands 把数字格式化成带千位分隔的形式，对应 Python 的 {:,.2f}。
func thousands(value float64, decimals int) string {
	text := strconv.FormatFloat(value, 'f', decimals, 64)
	sign := ""
	if strings.HasPrefix(text, "-") {
		sign, text = "-", text[1:]
	}
	intPart, frac, _ := strings.Cut(text, ".")

	var grouped strings.Builder
	for i, digit := range intPart {
		if i > 0 && (len(intPart)-i)%3 == 0 {
			grouped.WriteByte(',')
		}
		grouped.WriteRune(digit)
	}
	if frac == "" {
		return sign + grouped.String()
	}
	return sign + grouped.String() + "." + frac
}

// trimFloat 对应 Python 的 {:g}：7.0 显示成 7，7.5 还是 7.5。
func trimFloat(value float64) string {
	return strconv.FormatFloat(value, 'g', -1, 64)
}
