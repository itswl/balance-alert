// Package selfcheck provides the package implementation.
//
//	quotapulse -show-config
//
// Implementation note.
package selfcheck

import (
	"context"
	"fmt"
	"io"
	"strings"

	"github.com/itswl/quotapulse/internal/app"
	"github.com/itswl/quotapulse/internal/config"
	"github.com/itswl/quotapulse/internal/model"
	"github.com/itswl/quotapulse/internal/notify"
	"github.com/itswl/quotapulse/internal/provider"
	"github.com/itswl/quotapulse/internal/timeutil"
)

// Implementation note.
const (
	markOK   = "✓"
	markWarn = "!"
	markBad  = "✗"
)

// Implementation note.
func Run(ctx context.Context, instance *app.App, out io.Writer) int {
	settings := instance.Settings
	cfg := instance.Resolver.Load(ctx)

	var lines []string
	problems := 0

	lines = append(lines, "Configuration self-check", "  operation: "+databaseLabel(settings))
	lines = append(lines, "  operation: "+sources(cfg, settings))
	lines = append(lines, "  operation: "+features(settings))
	lines = append(lines, "  operation: "+schedules(settings))
	if !settings.EnableDatabase {
		lines = append(lines, "  "+markWarn+" operation ENABLE_DATABASE=true operation,operationDisabled")
	}
	if settings.EnableSubscriptions && !settings.EnableDynamicConfig {
		lines = append(lines, "  "+markWarn+" operation,operation,operation ENABLE_DYNAMIC_CONFIG=true")
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
		lines = append(lines, "", fmt.Sprintf("operation %d operation(operation %s / %s operation)", problems, markBad, markWarn))
	} else {
		lines = append(lines, "", "operation")
	}

	fmt.Fprintln(out, strings.Join(lines, "\n"))
	return problems
}

func databaseLabel(settings *config.Settings) string {
	if !settings.EnableDatabase {
		return "Disabled"
	}
	scheme, _, _ := strings.Cut(settings.DatabaseURL, "://")
	return scheme
}

// Implementation note.
func sources(cfg model.Config, settings *config.Settings) string {
	label := func(total, fromEnv int) string {
		if total == 0 {
			return "(operation)"
		}
		var parts []string
		if total-fromEnv > 0 {
			if settings.EnableDynamicConfig {
				parts = append(parts, "operation")
			} else {
				parts = append(parts, "operation")
			}
		}
		if fromEnv > 0 {
			parts = append(parts, "environment variable")
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
	return fmt.Sprintf("operation=%s  operation=%s  operation=%s",
		label(len(cfg.Projects), projectsFromEnv),
		label(len(cfg.Subscriptions), 0),
		label(len(cfg.Mailboxes), mailboxesFromEnv))
}

func features(settings *config.Settings) string {
	toggles := []struct {
		name string
		on   bool
	}{
		{"operation", settings.EnableDatabase},
		{"operation", settings.EnableDynamicConfig},
		{"operation API", settings.EnableHistoryAPI},
		{"operation", settings.EnableSubscriptions},
		{"Prometheus", settings.EnablePrometheus},
		{"Web operation", settings.EnableWebAlarm},
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
	return fmt.Sprintf("operation operation %d operation  operation %s  operation %s(operation %d operation)  operation %s",
		settings.RefreshInterval(),
		timeutil.Describe(settings.AlertTimes, nil),
		timeutil.Describe(settings.EmailScanTimes, nil),
		settings.EmailScanDays,
		timeutil.Describe(settings.WeeklyReportTimes, settings.WeeklyReportWeekdays))
}

func checkProjects(projects []model.Project) ([]string, int) {
	lines := []string{"", fmt.Sprintf("operation (%d)", len(projects))}
	if len(projects) == 0 {
		return append(lines, "  "+markBad+" operation,operation"), 1
	}

	problems := 0
	ordinals := make(map[string]int)
	for _, p := range projects {
		if p.Provider == "" {
			lines = append(lines, "  "+markBad+" "+displayName(p.Name)+": operation provider operation")
			problems++
			continue
		}
		if _, known := provider.Lookup(p.Provider); !known {
			lines = append(lines, fmt.Sprintf("  %s %s: Unknown provider %q,operation %s",
				markBad, displayName(p.Name), p.Provider, strings.Join(provider.Keys(), " ")))
			problems++
			continue
		}

		ordinals[p.Provider]++
		source, candidates := config.KeySource(p, ordinals[p.Provider])
		if source == "" {
			hint := "?"
			if len(candidates) > 0 {
				hint = strings.Join(candidates, " operation ")
			}
			lines = append(lines, fmt.Sprintf("  %s %s [%s]: Missing API key; set  %s",
				markBad, displayName(p.Name), p.Provider, hint))
			problems++
			continue
		}

		origin := ""
		if p.FromEnv {
			origin = "(environment variableauto-discovered)"
		}
		detail := fmt.Sprintf("%s [%s/%s] operation %g — Key operation %s%s",
			displayName(p.Name), p.Provider, p.Type, p.Threshold, source, origin)
		if p.Threshold == 0 {
			hint := "operation"
			if p.FromEnv {
				hint = strings.ToUpper(p.Provider) + "_THRESHOLD"
			}
			lines = append(lines, fmt.Sprintf("  %s %s(operation 0,operation,operation %s)", markWarn, detail, hint))
			problems++
			continue
		}
		lines = append(lines, "  "+markOK+" "+detail)
	}
	return lines, problems
}

func checkSubscriptions(subs []model.Subscription) ([]string, int) {
	lines := []string{"", fmt.Sprintf("operation (%d)", len(subs))}
	if len(subs) == 0 {
		return append(lines, "  — operation"), 0
	}

	problems := 0
	for _, s := range subs {
		readable := notify.FormatSubscriptionCycle(s.CycleType, s.RenewalDay)
		if readable == "Unknown cycle" {
			lines = append(lines, fmt.Sprintf("  %s %s: operation %q operation(weekly/monthly/yearly)",
				markBad, displayName(s.Name), s.CycleType))
			problems++
			continue
		}
		lines = append(lines, fmt.Sprintf("  %s %s: %s,operation %d operation,Amount %g",
			markOK, displayName(s.Name), readable, s.AlertDaysBefore, s.Amount))
	}
	return lines, problems
}

func checkMailboxes(mailboxes []model.Mailbox) ([]string, int) {
	lines := []string{"", fmt.Sprintf("operation (%d)", len(mailboxes))}
	if len(mailboxes) == 0 {
		return append(lines, "  — operation"), 0
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
			lines = append(lines, fmt.Sprintf("  %s %s: operation %s",
				markBad, displayName(m.Name), strings.Join(missing, ", ")))
			problems++
			continue
		}
		transport := "operation"
		if m.UseSSL {
			transport = "SSL"
		}
		lines = append(lines, fmt.Sprintf("  %s %s: %s:%d %s,operation %s",
			markOK, displayName(m.Name), m.Host, m.Port, transport, m.Username))
	}
	return lines, problems
}

func checkChannel(settings *config.Settings) ([]string, int) {
	lines := []string{"", "operation"}
	problems := 0

	if settings.WebhookURL == "" {
		lines = append(lines, "  "+markBad+" WEBHOOK_URL is not set,Low balanceoperation")
		problems++
	} else {
		webhookType := settings.WebhookType
		if webhookType == "" {
			webhookType = "custom"
		}
		if _, err := notify.New(settings.WebhookURL, webhookType, settings.WebhookSource, nil); err != nil {
			lines = append(lines, fmt.Sprintf("  %s Webhook [%s]: %s(operation %s)",
				markBad, webhookType, err, strings.Join(notify.SupportedTypes(), "/")))
			problems++
		} else {
			lines = append(lines, fmt.Sprintf("  %s Webhook [%s] → %s",
				markOK, webhookType, notify.MaskURL(settings.WebhookURL)))
		}
	}

	if settings.WebAPIKey == "" {
		lines = append(lines, "  "+markBad+" WEB_API_KEY is not set,operation /api/* operation 503")
		problems++
	} else {
		lines = append(lines, fmt.Sprintf("  %s WEB_API_KEY operation(%s)", markOK, mask(settings.WebAPIKey)))
	}

	if settings.EnableDynamicConfig && settings.ConfigEncryptionKey == "" {
		lines = append(lines, "  "+markWarn+" database dynamic configurationoperation CONFIG_ENCRYPTION_KEY,operation")
	}
	return lines, problems
}

func displayName(name string) string {
	if name == "" {
		return "(operation)"
	}
	return name
}

func mask(value string) string {
	if len(value) <= 4 {
		return "***"
	}
	return value[:4] + "***"
}
