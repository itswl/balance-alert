package notify

import (
	"fmt"
	"strings"
	"time"

	"github.com/itswl/balance-alert/internal/model"
)

// BalanceAlert 余额不足。
//
// 底下的 balanceAlert 还带 balanceType 和 unit 两个参数，但调用点只会传 "余额" 和空串——
// 真正的余额类型（点数 / 套餐）只影响看板，不进告警文案。
// 这里就不把它们摊到签名上了，需要时改 balanceAlert。
func BalanceAlert(projectName string, ownerProject *string, provider string, currentValue, threshold float64) Message {
	return balanceAlert(projectName, ownerProject, provider, "余额", currentValue, threshold, "")
}

func balanceAlert(projectName string, ownerProject *string, provider, balanceType string,
	currentValue, threshold float64, unit string) Message {
	current := unit + formatAmount(currentValue)
	limit := unit + formatAmount(threshold)

	lines := []string{"API 调用: " + projectName}
	lines = appendOwner(lines, ownerProject)
	lines = append(lines,
		"服务商: "+provider,
		"当前"+balanceType+": "+current,
		"告警阈值: "+limit,
		"状态: ⚠️ "+balanceType+"不足",
	)

	return Message{
		Title: "余额告警",
		Lines: lines,
		Kind:  KindBalance,
		envelope: &envelope{
			Type:     "AlarmNotification",
			RuleName: projectName + balanceType + "告警",
			Level:    "critical",
			Resources: []any{balanceResource{
				ProjectName:  projectName,
				OwnerProject: ownerProject,
				Provider:     provider,
				BalanceType:  balanceType,
				CurrentValue: currentValue,
				Threshold:    threshold,
				Unit:         unit,
				Message: fmt.Sprintf("项目 [%s] %s不足，当前: %s，阈值: %s",
					projectName, balanceType, current, limit),
			}},
		},
	}
}

// SubscriptionAlert 订阅快到期。
func SubscriptionAlert(name string, ownerProject *string, cycleType string,
	renewalDay, daysUntilRenewal int, amount float64) Message {
	cycle := FormatSubscriptionCycle(cycleType, renewalDay)

	lines := []string{"订阅: " + name}
	lines = appendOwner(lines, ownerProject)
	lines = append(lines,
		"续费周期: "+cycle,
		"距离续费: "+formatDays(daysUntilRenewal),
		"续费金额: "+formatFloat(amount),
	)

	// 今天或已经过期的按 critical 发，还有几天的只是提醒
	level := "warning"
	if daysUntilRenewal <= 0 {
		level = "critical"
	}

	return Message{
		Title: "订阅续费提醒",
		Lines: lines,
		Kind:  KindSubscription,
		envelope: &envelope{
			Type:     "SubscriptionReminder",
			RuleName: name + "续费提醒",
			Level:    level,
			Resources: []any{subscriptionResource{
				SubscriptionName: name,
				OwnerProject:     ownerProject,
				RenewalDay:       renewalDay,
				CycleType:        cycleType,
				DaysUntilRenewal: daysUntilRenewal,
				Amount:           amount,
				Message: fmt.Sprintf("订阅 [%s] 将在 %d 天后（%s）续费，金额: %s",
					name, daysUntilRenewal, cycle, formatFloat(amount)),
			}},
		},
	}
}

// Custom 富文本告警：跑道见底、消耗突增、周报共用这一条路，正文由调用方拼好 Markdown。
// kind 只用于指标分类，不影响报文。
func Custom(title string, lines []string, kind string) Message {
	return Message{Title: title, Lines: lines, Kind: kind}
}

// EmailAlert 邮件命中关键词。
func EmailAlert(mailbox, subject, sender, date string, keywords []string,
	serviceName *string, amount *float64) Message {
	if mailbox == "" {
		mailbox = "未知"
	}

	lines := []string{
		"**邮箱**: " + mailbox,
		"**发件人**: " + sender,
		"**日期**: " + date,
		"**服务**: " + serviceText(serviceName),
	}
	// 金额认不出来（或是 0）就不写这行，免得群里看到一个空数字
	if amount != nil && *amount != 0 {
		lines = append(lines, "**金额**: "+formatFloat(*amount))
	}
	lines = append(lines, "**关键词**: "+strings.Join(keywords, ", "))

	return Message{Title: "📧 邮件告警: " + subject, Lines: lines, Kind: KindEmail}
}

// MailboxError 邮箱连不上。
//
// host 是调用方手里的上下文，但正文里不写这一行——值班群认的就是这三行，
// 多一行就是改模板。参数留着是为了不动调用点。
func MailboxError(mailbox, host, reason string) Message {
	return mailboxError(mailbox, reason, time.Now())
}

// mailboxError 把时钟拆出来，测试才能钉住"**时间**"那一行。
func mailboxError(mailbox, reason string, at time.Time) Message {
	return Message{
		Title: "❌ 邮箱连接失败告警",
		Lines: []string{
			"**邮箱**: " + mailbox,
			"**错误信息**: " + reason,
			"**时间**: " + at.Format("2006-01-02 15:04:05"),
		},
		Kind: KindMailboxError,
	}
}

// FormatSubscriptionCycle 把续费周期说成人话，订阅检查与配置自检也用它。
//
// 返回 "未知周期" 表示周期类型不认识，调用方靠这个值把配置错误报出来。
// 别改成按月付兜底（"每月 15 号"）：那样写错的周期类型会一直发着看起来正常的提醒，
// 直到有人发现续费日期对不上才查得出来。
func FormatSubscriptionCycle(cycleType string, renewalDay int) string {
	switch cycleType {
	case model.CycleWeekly:
		weekdays := []string{"周一", "周二", "周三", "周四", "周五", "周六", "周日"}
		if renewalDay >= 1 && renewalDay <= 7 {
			return "每周 " + weekdays[renewalDay-1]
		}
		return fmt.Sprintf("每周第 %d 天", renewalDay)
	case model.CycleYearly:
		if month, day, ok := splitMMDD(renewalDay); ok {
			return fmt.Sprintf("每年 %d月%d日", month, day)
		}
		// 旧配置里年付也可能只写了日，说不出具体日期
		return "每年固定日期"
	case model.CycleMonthly:
		return fmt.Sprintf("每月 %d 号", renewalDay)
	}
	return "未知周期"
}

// splitMMDD 把年付的 MMDD 整数（如 315）拆成月和日。
//
// 与 internal/subscription.SplitMMDD 是同一套规则，这里重写一份而不是 import：
// subscription 包要用 notify 发提醒，反过来依赖就成环了。
func splitMMDD(renewalDay int) (month, day int, ok bool) {
	// 小于等于 31 的属于旧配置的"只写了日"，不是 MMDD
	if renewalDay <= 31 {
		return 0, 0, false
	}
	month, day = renewalDay/100, renewalDay%100
	if month < 1 || month > 12 || day < 1 || day > 31 {
		return 0, 0, false
	}
	return month, day, true
}

// formatDays 把天数说成人话：0 是今天，1 是明天，其余写 "N 天后"。
func formatDays(days int) string {
	switch days {
	case 0:
		return "今天"
	case 1:
		return "明天"
	}
	return fmt.Sprintf("%d 天后", days)
}

// appendOwner 没归属项目时整行不出现，而不是留一行空的 "所属项目: "。
func appendOwner(lines []string, ownerProject *string) []string {
	if ownerProject == nil || *ownerProject == "" {
		return lines
	}
	return append(lines, "所属项目: "+*ownerProject)
}

// serviceText 没识别出服务名时写的是字面量 "None"，群里看到的就是 "**服务**: None"。
// 看着别扭，但值班群认的就是这个词，换成 "未知" 属于文案变更，message_test.go 钉住了它。
func serviceText(name *string) string {
	if name == nil {
		return "None"
	}
	return *name
}
