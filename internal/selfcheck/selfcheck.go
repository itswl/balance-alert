// Package selfcheck 一条命令看清「配了什么、从哪来、哪里不对」。
//
//	balance-alert -show-config
//
// 有问题时返回非零退出码，可以直接用于部署前校验。
package selfcheck

import (
	"context"
	"fmt"
	"io"
	"strings"

	"github.com/itswl/balance-alert/internal/app"
	"github.com/itswl/balance-alert/internal/config"
	"github.com/itswl/balance-alert/internal/model"
	"github.com/itswl/balance-alert/internal/notify"
	"github.com/itswl/balance-alert/internal/provider"
	"github.com/itswl/balance-alert/internal/timeutil"
)

// 标记符号：✓ 没问题，! 能跑但不对劲，✗ 一定有问题。
const (
	markOK   = "✓"
	markWarn = "!"
	markBad  = "✗"
)

// Run 打印自检报告，返回发现的问题数量。
func Run(ctx context.Context, instance *app.App, out io.Writer) int {
	settings := instance.Settings
	cfg := instance.Resolver.Load(ctx)

	var lines []string
	problems := 0

	lines = append(lines, "配置自检", "  数据库: "+databaseLabel(settings))
	lines = append(lines, "  业务清单来源: "+sources(cfg, settings))
	lines = append(lines, "  可选能力: "+features(settings))
	lines = append(lines, "  定时任务: "+schedules(settings))
	if !settings.EnableDatabase {
		lines = append(lines, "  "+markWarn+" 消耗分析与跑道估算需要 ENABLE_DATABASE=true 攒历史，当前未启用")
	}
	if settings.EnableSubscriptions && !settings.EnableDynamicConfig {
		lines = append(lines, "  "+markWarn+" 订阅提醒已开启，但订阅清单只能存在数据库里，还需要 ENABLE_DYNAMIC_CONFIG=true")
		problems++
	}

	projectLines, projectProblems := checkProjects(cfg.Projects)
	lines = append(lines, projectLines...)
	problems += projectProblems

	subLines, subProblems := checkSubscriptions(cfg.Subscriptions)
	lines = append(lines, subLines...)
	problems += subProblems

	mailLines, mailProblems := checkMailboxes(cfg.Mailboxes)
	lines = append(lines, mailLines...)
	problems += mailProblems

	channelLines, channelProblems := checkChannel(settings)
	lines = append(lines, channelLines...)
	problems += channelProblems

	if problems > 0 {
		lines = append(lines, "", fmt.Sprintf("发现 %d 个问题（上面标 %s / %s 的条目）", problems, markBad, markWarn))
	} else {
		lines = append(lines, "", "配置看起来没问题")
	}

	fmt.Fprintln(out, strings.Join(lines, "\n"))
	return problems
}

func databaseLabel(settings *config.Settings) string {
	if !settings.EnableDatabase {
		return "未启用"
	}
	scheme, _, _ := strings.Cut(settings.DatabaseURL, "://")
	return scheme
}

// sources 说明三段清单各自来自哪：数据库、环境变量，或两者都有。
func sources(cfg model.Config, settings *config.Settings) string {
	label := func(total, fromEnv int) string {
		if total == 0 {
			return "(空)"
		}
		var parts []string
		if total-fromEnv > 0 {
			if settings.EnableDynamicConfig {
				parts = append(parts, "数据库")
			} else {
				parts = append(parts, "未知来源")
			}
		}
		if fromEnv > 0 {
			parts = append(parts, "环境变量")
		}
		return strings.Join(parts, " + ")
	}

	projectsFromEnv := 0
	for _, p := range cfg.Projects {
		if p.FromEnv {
			projectsFromEnv++
		}
	}
	mailboxesFromEnv := 0
	for _, m := range cfg.Mailboxes {
		if m.FromEnv {
			mailboxesFromEnv++
		}
	}
	return fmt.Sprintf("项目=%s  订阅=%s  邮箱=%s",
		label(len(cfg.Projects), projectsFromEnv),
		label(len(cfg.Subscriptions), 0),
		label(len(cfg.Mailboxes), mailboxesFromEnv))
}

func features(settings *config.Settings) string {
	toggles := []struct {
		name string
		on   bool
	}{
		{"数据库", settings.EnableDatabase},
		{"动态配置", settings.EnableDynamicConfig},
		{"历史 API", settings.EnableHistoryAPI},
		{"订阅提醒", settings.EnableSubscriptions},
		{"Prometheus", settings.EnablePrometheus},
		{"Web 告警", settings.EnableWebAlarm},
	}
	parts := make([]string, 0, len(toggles))
	for _, t := range toggles {
		mark := markBad
		if t.on {
			mark = markOK
		}
		parts = append(parts, t.name+mark)
	}
	return strings.Join(parts, "  ")
}

func schedules(settings *config.Settings) string {
	return fmt.Sprintf("看板刷新 每 %d 秒  告警检查 %s  邮箱扫描 %s（最近 %d 天）  周报 %s",
		settings.RefreshInterval(),
		timeutil.Describe(settings.AlertTimes, nil),
		timeutil.Describe(settings.EmailScanTimes, nil),
		settings.EmailScanDays,
		timeutil.Describe(settings.WeeklyReportTimes, settings.WeeklyReportWeekdays))
}

func checkProjects(projects []model.Project) ([]string, int) {
	lines := []string{"", fmt.Sprintf("项目 (%d)", len(projects))}
	if len(projects) == 0 {
		return append(lines, "  "+markBad+" 没有任何项目，余额检查不会执行"), 1
	}

	problems := 0
	ordinals := make(map[string]int)
	for _, p := range projects {
		if p.Provider == "" {
			lines = append(lines, "  "+markBad+" "+displayName(p.Name)+": 缺少 provider 字段")
			problems++
			continue
		}
		if _, known := provider.Lookup(p.Provider); !known {
			lines = append(lines, fmt.Sprintf("  %s %s: 未知的服务商 %q，支持 %s",
				markBad, displayName(p.Name), p.Provider, strings.Join(provider.Keys(), " ")))
			problems++
			continue
		}

		ordinals[p.Provider]++
		source, candidates := config.KeySource(p, ordinals[p.Provider])
		if source == "" {
			hint := "?"
			if len(candidates) > 0 {
				hint = strings.Join(candidates, " 或 ")
			}
			lines = append(lines, fmt.Sprintf("  %s %s [%s]: 缺少 API Key，请设置 %s",
				markBad, displayName(p.Name), p.Provider, hint))
			problems++
			continue
		}

		origin := ""
		if p.FromEnv {
			origin = "（环境变量自动发现）"
		}
		detail := fmt.Sprintf("%s [%s/%s] 阈值 %g — Key 来自 %s%s",
			displayName(p.Name), p.Provider, p.Type, p.Threshold, source, origin)
		if p.Threshold == 0 {
			hint := "页面上填写阈值"
			if p.FromEnv {
				hint = strings.ToUpper(p.Provider) + "_THRESHOLD"
			}
			lines = append(lines, fmt.Sprintf("  %s %s（阈值 0，不会触发告警，设 %s）", markWarn, detail, hint))
			problems++
			continue
		}
		lines = append(lines, "  "+markOK+" "+detail)
	}
	return lines, problems
}

func checkSubscriptions(subs []model.Subscription) ([]string, int) {
	lines := []string{"", fmt.Sprintf("订阅 (%d)", len(subs))}
	if len(subs) == 0 {
		return append(lines, "  — 未配置"), 0
	}

	problems := 0
	for _, s := range subs {
		readable := notify.FormatSubscriptionCycle(s.CycleType, s.RenewalDay)
		if readable == "未知周期" {
			lines = append(lines, fmt.Sprintf("  %s %s: 周期类型 %q 不支持（weekly/monthly/yearly）",
				markBad, displayName(s.Name), s.CycleType))
			problems++
			continue
		}
		lines = append(lines, fmt.Sprintf("  %s %s: %s，提前 %d 天提醒，金额 %g",
			markOK, displayName(s.Name), readable, s.AlertDaysBefore, s.Amount))
	}
	return lines, problems
}

func checkMailboxes(mailboxes []model.Mailbox) ([]string, int) {
	lines := []string{"", fmt.Sprintf("邮箱 (%d)", len(mailboxes))}
	if len(mailboxes) == 0 {
		return append(lines, "  — 未配置"), 0
	}

	problems := 0
	for _, m := range mailboxes {
		var missing []string
		if m.Host == "" {
			missing = append(missing, "host")
		}
		if m.Username == "" {
			missing = append(missing, "username")
		}
		if m.Password == "" {
			missing = append(missing, "password")
		}
		if len(missing) > 0 {
			lines = append(lines, fmt.Sprintf("  %s %s: 缺少 %s",
				markBad, displayName(m.Name), strings.Join(missing, ", ")))
			problems++
			continue
		}
		transport := "明文"
		if m.UseSSL {
			transport = "SSL"
		}
		lines = append(lines, fmt.Sprintf("  %s %s: %s:%d %s，账号 %s",
			markOK, displayName(m.Name), m.Host, m.Port, transport, m.Username))
	}
	return lines, problems
}

func checkChannel(settings *config.Settings) ([]string, int) {
	lines := []string{"", "告警与访问"}
	problems := 0

	if settings.WebhookURL == "" {
		lines = append(lines, "  "+markBad+" 未设置 WEBHOOK_URL，余额不足时无法发出告警")
		problems++
	} else {
		webhookType := settings.WebhookType
		if webhookType == "" {
			webhookType = "custom"
		}
		if _, err := notify.New(settings.WebhookURL, webhookType, settings.WebhookSource, nil); err != nil {
			lines = append(lines, fmt.Sprintf("  %s Webhook [%s]: %s（可选 %s）",
				markBad, webhookType, err, strings.Join(notify.SupportedTypes(), "/")))
			problems++
		} else {
			lines = append(lines, fmt.Sprintf("  %s Webhook [%s] → %s",
				markOK, webhookType, notify.MaskURL(settings.WebhookURL)))
		}
	}

	if settings.WebAPIKey == "" {
		lines = append(lines, "  "+markBad+" 未设置 WEB_API_KEY，所有 /api/* 请求会返回 503")
		problems++
	} else {
		lines = append(lines, fmt.Sprintf("  %s WEB_API_KEY 已设置（%s）", markOK, mask(settings.WebAPIKey)))
	}

	if settings.EnableDynamicConfig && settings.ConfigEncryptionKey == "" {
		lines = append(lines, "  "+markWarn+" 数据库动态配置已开启但未设置 CONFIG_ENCRYPTION_KEY，密钥将明文入库")
	}
	return lines, problems
}

func displayName(name string) string {
	if name == "" {
		return "(未命名)"
	}
	return name
}

func mask(value string) string {
	if len(value) <= 4 {
		return "***"
	}
	return value[:4] + "***"
}
