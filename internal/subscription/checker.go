package subscription

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/notify"
	"github.com/itswl/balance-alert/internal/store"
)

// Checker 检查订阅是否临近续费。
type Checker struct {
	Store    store.Store
	Notifier notify.Notifier
	Log      *slog.Logger
	Cooldown time.Duration

	// OnNotify 每发一次通知回调一次，用于记指标。可空。
	OnNotify func(kind string, ok bool)
}

// Check 逐条判断订阅要不要提醒。dryRun 时只判断不发送。
func (c *Checker) Check(ctx context.Context, subs []model.Subscription, dryRun bool) []model.SubscriptionResult {
	if len(subs) == 0 {
		c.log().Info("没有订阅项目，可在页面上添加（需要数据库动态配置）")
		return []model.SubscriptionResult{}
	}
	c.log().Info("开始检查订阅", "count", len(subs), "dry_run", dryRun)

	today := time.Now()
	results := make([]model.SubscriptionResult, 0, len(subs))
	for _, sub := range subs {
		results = append(results, c.checkOne(ctx, sub, today, dryRun))
	}
	c.logSummary(results)
	return results
}

func (c *Checker) checkOne(ctx context.Context, sub model.Subscription, today time.Time, dryRun bool) model.SubscriptionResult {
	lastRenewed := parseRenewedDate(sub.LastRenewedDate, today.Location(), c.log())
	days, next := NextRenewal(sub.CycleType, sub.RenewalDay, today, lastRenewed)

	alreadyRenewed := false
	if lastRenewed != nil {
		start := cycleStart(sub.CycleType, sub.RenewalDay, startOfDay(today), next)
		alreadyRenewed = !lastRenewed.Before(start)
	}
	needAlert := days >= 0 && days <= sub.AlertDaysBefore && !alreadyRenewed

	result := model.SubscriptionResult{
		Name:             sub.Name,
		OwnerProject:     sub.OwnerProject,
		RenewalDay:       sub.RenewalDay,
		CycleType:        sub.CycleType,
		DaysUntilRenewal: days,
		NextRenewalDate:  next.Format("2006-01-02"),
		NeedAlert:        needAlert,
		Amount:           sub.Amount,
		AlreadyRenewed:   alreadyRenewed,
		LastRenewedDate:  sub.LastRenewedDate,
	}

	c.log().Info("订阅检查",
		"name", sub.Name,
		"cycle", notify.FormatSubscriptionCycle(sub.CycleType, sub.RenewalDay),
		"amount", sub.Amount, "days_until_renewal", days, "next", result.NextRenewalDate)

	switch {
	case alreadyRenewed:
		c.log().Info("本周期已续费，无需提醒", "name", sub.Name)
	case !needAlert:
		c.log().Info("无需提醒", "name", sub.Name)
	case dryRun:
		c.log().Warn("需要提醒续费，测试模式不发送", "name", sub.Name, "before_days", sub.AlertDaysBefore)
	default:
		c.log().Warn("需要提醒续费", "name", sub.Name, "before_days", sub.AlertDaysBefore)
		result.AlertSent = c.send(ctx, sub, days)
	}
	return result
}

// send 发送续费提醒并留痕；冷却窗口内跳过。
func (c *Checker) send(ctx context.Context, sub model.Subscription, days int) bool {
	alertID := model.SubscriptionID(sub.Name)
	cooling, err := c.Store.HasRecentAlert(ctx, alertID, "subscription_renewal", c.Cooldown)
	if err != nil {
		c.log().Warn("查询订阅告警冷却失败，按未冷却处理", "name", sub.Name, "error", err)
	}
	if cooling {
		c.log().Info("订阅提醒仍在冷却窗口内，跳过重复通知", "name", sub.Name, "cooldown", c.Cooldown)
		return false
	}
	if c.Notifier == nil {
		c.log().Error("未配置 webhook 地址")
		return false
	}

	msg := notify.SubscriptionAlert(sub.Name, sub.OwnerProject, sub.CycleType, sub.RenewalDay, days, sub.Amount)
	sendErr := c.Notifier.Send(ctx, msg)
	if c.OnNotify != nil {
		c.OnNotify(msg.Kind, sendErr == nil)
	}
	if sendErr != nil {
		c.log().Error("发送订阅提醒失败", "name", sub.Name, "error", sendErr)
		return false
	}

	if err := c.Store.SaveAlert(ctx, store.AlertRecord{
		AlertID: alertID, Name: sub.Name, AlertType: "subscription_renewal",
		Message:   fmt.Sprintf("订阅续费提醒: %s 将在 %d 天后续费", sub.Name, days),
		Value:     &sub.Amount,
		Threshold: model.Ptr(float64(sub.AlertDaysBefore)),
	}); err != nil {
		c.log().Warn("记录订阅告警失败", "name", sub.Name, "error", err)
	}
	return true
}

// parseRenewedDate 解析上次续费日期；格式不对时当作没续过，并记一条警告。
func parseRenewedDate(value *string, loc *time.Location, log *slog.Logger) *time.Time {
	if value == nil || *value == "" {
		return nil
	}
	parsed, err := time.ParseInLocation("2006-01-02", *value, loc)
	if err != nil {
		log.Warn("续费日期格式错误", "value", *value)
		return nil
	}
	return &parsed
}

func (c *Checker) logSummary(results []model.SubscriptionResult) {
	needAlert, sent := 0, 0
	for _, r := range results {
		if r.NeedAlert {
			needAlert++
		}
		if r.AlertSent {
			sent++
		}
	}
	c.log().Info("订阅检查汇总", "total", len(results), "need_alert", needAlert, "sent", sent)
}

func (c *Checker) log() *slog.Logger {
	if c.Log != nil {
		return c.Log
	}
	return slog.Default()
}

// NextRenewalFrom 供页面"标记已续费"后展示下次续费日用。
func NextRenewalFrom(cycleType string, renewalDay int, from time.Time) (time.Time, error) {
	switch cycleType {
	case model.CycleWeekly:
		ahead := renewalDay - isoWeekday(from)
		if ahead <= 0 {
			ahead += 7
		}
		return from.AddDate(0, 0, ahead), nil
	case model.CycleMonthly:
		return shiftMonth(from, 1, renewalDay), nil
	case model.CycleYearly:
		month, day, ok := SplitMMDD(renewalDay)
		if !ok {
			// 兼容旧格式：只写了 1-31 时按周年日计算
			return safeReplaceYear(from, from.Year()+1), nil
		}
		return safeMonthDate(from.Year()+1, time.Month(month), day, from.Location()), nil
	}
	return time.Time{}, fmt.Errorf("不支持的周期类型: %s", cycleType)
}
