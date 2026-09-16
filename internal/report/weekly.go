// Package report 生成周报：把一周的余额、消耗、跑道、订阅、邮箱汇成一张卡片。
//
// 平时只有出事才会收到通知，周报让"一切正常"也变成可感知的东西：这周烧了多少、
// 哪个账户最先见底、接下来一个月要准备多少订阅费。数据全部取自看板状态与余额历史，
// 不额外查上游接口。
package report

import (
	"fmt"
	"math"
	"sort"
	"strings"
	"time"

	"github.com/itswl/balance-alert/internal/model"
)

const (
	// WindowDays 周报统计的时间跨度。
	WindowDays = 7
	// TopN 各排行榜取前几名。
	TopN = 3
	// UpcomingDays 订阅支出预估的时间范围。
	UpcomingDays = 30
)

// SpendRow 是消耗排行榜的一行。
type SpendRow struct {
	Project       string   `json:"project"`
	Consumed      float64  `json:"consumed"`
	BurnPerDay    *float64 `json:"burn_per_day"`
	RunwayDays    *float64 `json:"runway_days"`
	DepletionDate *string  `json:"depletion_date"`
	Balance       *float64 `json:"balance"`
}

// AlertingRow 是余额告警清单的一行。
type AlertingRow struct {
	Project   string   `json:"project"`
	Balance   *float64 `json:"balance"`
	Threshold *float64 `json:"threshold"`
}

// FailedRow 是检查失败清单的一行。
type FailedRow struct {
	Project string `json:"project"`
	Error   string `json:"error"`
}

// Accounts 是账户总体情况。
type Accounts struct {
	Total    int `json:"total"`
	Alerting int `json:"alerting"`
	Failed   int `json:"failed"`
}

// Period 是统计区间。
type Period struct {
	Start string `json:"start"`
	End   string `json:"end"`
}

// MailboxStats 是邮箱扫描的概况。
type MailboxStats struct {
	Total  int `json:"total"`
	Failed int `json:"failed"`
	Alerts int `json:"alerts"`
}

// Summary 是一周的汇总数据，render 之前的中间结构。
type Summary struct {
	Period                Period                     `json:"period"`
	Accounts              Accounts                   `json:"accounts"`
	TotalConsumed         *float64                   `json:"total_consumed"`
	TopSpend              []SpendRow                 `json:"top_spend"`
	ShortestRunway        []SpendRow                 `json:"shortest_runway"`
	AlertingProjects      []AlertingRow              `json:"alerting_projects"`
	FailedProjects        []FailedRow                `json:"failed_projects"`
	UpcomingSubscriptions []model.SubscriptionResult `json:"upcoming_subscriptions"`
	UpcomingAmount        float64                    `json:"upcoming_amount"`
	Mailboxes             MailboxStats               `json:"mailboxes"`
}

// Build 汇总一周数据。runways 为空表示没有历史，那就只报余额部分。
func Build(results []model.CheckResult, subs []model.SubscriptionResult,
	mailboxes []model.MailboxResult, totalAlerts int, runways map[string]model.Runway, now time.Time) Summary {

	var succeeded []model.CheckResult
	var failed []model.CheckResult
	for _, r := range results {
		if r.Success {
			succeeded = append(succeeded, r)
		} else {
			failed = append(failed, r)
		}
	}

	spend := spendRows(succeeded, runways)
	upcoming := upcomingSubscriptions(subs)

	summary := Summary{
		Period: Period{
			Start: now.AddDate(0, 0, -WindowDays).Format("2006-01-02"),
			End:   now.Format("2006-01-02"),
		},
		Accounts: Accounts{
			Total:    len(results),
			Alerting: countAlerting(succeeded),
			Failed:   len(failed),
		},
		TopSpend:              topByConsumed(spend),
		ShortestRunway:        topByRunway(spend),
		AlertingProjects:      alertingRows(succeeded),
		FailedProjects:        failedRows(failed),
		UpcomingSubscriptions: upcoming,
		Mailboxes:             mailboxStats(mailboxes, totalAlerts),
	}

	if len(spend) > 0 {
		total := 0.0
		for _, row := range spend {
			total += row.Consumed
		}
		summary.TotalConsumed = model.Ptr(round2(total))
	}
	for _, sub := range upcoming {
		summary.UpcomingAmount += sub.Amount
	}
	summary.UpcomingAmount = round2(summary.UpcomingAmount)
	return summary
}

// spendRows 把消耗画像整理成排行榜用的行；没有历史的账户不出现在榜上。
func spendRows(results []model.CheckResult, runways map[string]model.Runway) []SpendRow {
	var rows []SpendRow
	for _, r := range results {
		profile, ok := runways[model.ProjectID(r.Provider, r.Project)]
		if !ok {
			continue
		}
		rows = append(rows, SpendRow{
			Project:       r.Project,
			Consumed:      profile.Consumed,
			BurnPerDay:    profile.BurnPerDay,
			RunwayDays:    profile.RunwayDays,
			DepletionDate: profile.DepletionDate,
			Balance:       profile.CurrentBalance,
		})
	}
	return rows
}

// upcomingSubscriptions 是未来一个月内要续费、且本周期还没续过的订阅，按紧迫程度排序。
func upcomingSubscriptions(subs []model.SubscriptionResult) []model.SubscriptionResult {
	var due []model.SubscriptionResult
	for _, s := range subs {
		if !s.AlreadyRenewed && s.DaysUntilRenewal >= 0 && s.DaysUntilRenewal <= UpcomingDays {
			due = append(due, s)
		}
	}
	sort.SliceStable(due, func(i, j int) bool { return due[i].DaysUntilRenewal < due[j].DaysUntilRenewal })
	return due
}

func topByConsumed(rows []SpendRow) []SpendRow {
	sorted := append([]SpendRow(nil), rows...)
	sort.SliceStable(sorted, func(i, j int) bool { return sorted[i].Consumed > sorted[j].Consumed })
	return head(sorted)
}

func topByRunway(rows []SpendRow) []SpendRow {
	var withRunway []SpendRow
	for _, row := range rows {
		if row.RunwayDays != nil {
			withRunway = append(withRunway, row)
		}
	}
	sort.SliceStable(withRunway, func(i, j int) bool { return *withRunway[i].RunwayDays < *withRunway[j].RunwayDays })
	return head(withRunway)
}

func head(rows []SpendRow) []SpendRow {
	if len(rows) > TopN {
		return rows[:TopN]
	}
	return rows
}

func countAlerting(results []model.CheckResult) int {
	count := 0
	for _, r := range results {
		if r.NeedAlarm {
			count++
		}
	}
	return count
}

func alertingRows(results []model.CheckResult) []AlertingRow {
	var rows []AlertingRow
	for _, r := range results {
		if r.NeedAlarm {
			rows = append(rows, AlertingRow{Project: r.Project, Balance: r.Credits, Threshold: r.Threshold})
		}
	}
	return rows
}

func failedRows(results []model.CheckResult) []FailedRow {
	var rows []FailedRow
	for _, r := range results {
		message := ""
		if r.Error != nil {
			message = *r.Error
		}
		rows = append(rows, FailedRow{Project: r.Project, Error: message})
	}
	return rows
}

func mailboxStats(mailboxes []model.MailboxResult, totalAlerts int) MailboxStats {
	stats := MailboxStats{Total: len(mailboxes), Alerts: totalAlerts}
	for _, m := range mailboxes {
		if m.Error != nil {
			stats.Failed++
		}
	}
	return stats
}

// Render 渲染成 Markdown 正文；各平台的消息包装由 notify 负责。
func Render(s Summary) string {
	lines := headline(s)
	lines = append(lines, section("最先见底", runwayLines(s.ShortestRunway))...)
	lines = append(lines, section("消耗最多", spendLines(s.TopSpend))...)
	lines = append(lines, section(
		fmt.Sprintf("未来 %d 天订阅支出: %s", UpcomingDays, fmtNum(&s.UpcomingAmount)),
		subscriptionLines(s.UpcomingSubscriptions))...)
	lines = append(lines, section("需要处理", problemLines(s))...)
	return strings.Join(lines, "\n")
}

func headline(s Summary) []string {
	state := "，全部正常"
	if s.Accounts.Alerting > 0 {
		state = fmt.Sprintf("，%d 个余额告警", s.Accounts.Alerting)
	}
	if s.Accounts.Failed > 0 {
		state += fmt.Sprintf("，%d 个检查失败", s.Accounts.Failed)
	}
	lines := []string{
		fmt.Sprintf("**统计区间**: %s ~ %s", s.Period.Start, s.Period.End),
		fmt.Sprintf("**账户**: 共 %d 个%s", s.Accounts.Total, state),
	}
	if s.TotalConsumed != nil {
		lines = append(lines, "**本周消耗**: "+fmtNum(s.TotalConsumed))
	}
	return lines
}

// section 没有内容的小节整段不出现，卡片才不会一堆空标题。
func section(title string, rows []string) []string {
	if len(rows) == 0 {
		return nil
	}
	return append([]string{"", "**" + title + "**"}, rows...)
}

func runwayLines(rows []SpendRow) []string {
	var out []string
	for _, row := range rows {
		line := fmt.Sprintf("- %s: 还剩 %.1f 天", row.Project, *row.RunwayDays)
		if row.DepletionDate != nil {
			line += fmt.Sprintf("（预计 %s 耗尽）", *row.DepletionDate)
		}
		out = append(out, line+"，余额 "+fmtNum(row.Balance))
	}
	return out
}

func spendLines(rows []SpendRow) []string {
	var out []string
	for _, row := range rows {
		out = append(out, fmt.Sprintf("- %s: %s，日均 %s",
			row.Project, fmtNum(&row.Consumed), fmtNum(row.BurnPerDay)))
	}
	return out
}

func subscriptionLines(subs []model.SubscriptionResult) []string {
	var out []string
	for _, sub := range subs {
		amount := sub.Amount
		out = append(out, fmt.Sprintf("- %s: %d 天后续费，%s", sub.Name, sub.DaysUntilRenewal, fmtNum(&amount)))
	}
	return out
}

func problemLines(s Summary) []string {
	var out []string
	for _, item := range s.AlertingProjects {
		out = append(out, fmt.Sprintf("- %s: 余额 %s 低于阈值 %s",
			item.Project, fmtNum(item.Balance), fmtNum(item.Threshold)))
	}
	for _, item := range s.FailedProjects {
		out = append(out, fmt.Sprintf("- %s: 检查失败，%s", item.Project, item.Error))
	}
	if s.Mailboxes.Failed > 0 {
		out = append(out, fmt.Sprintf("- 邮箱: %d 个连接失败", s.Mailboxes.Failed))
	}
	return out
}

// fmtNum 对应 Python 的 _fmt：空值显示成横杠，其余带千位分隔保留两位小数。
func fmtNum(value *float64) string {
	if value == nil {
		return "-"
	}
	return thousands(*value, 2)
}

func thousands(value float64, decimals int) string {
	text := fmt.Sprintf("%.*f", decimals, value)
	sign := ""
	if strings.HasPrefix(text, "-") {
		sign, text = "-", text[1:]
	}
	intPart, frac, hasFrac := strings.Cut(text, ".")

	var grouped strings.Builder
	for i, digit := range intPart {
		if i > 0 && (len(intPart)-i)%3 == 0 {
			grouped.WriteByte(',')
		}
		grouped.WriteRune(digit)
	}
	if !hasFrac {
		return sign + grouped.String()
	}
	return sign + grouped.String() + "." + frac
}

// round2 用银行家舍入，与 Python 的 round(x, 2) 保持一致。
func round2(value float64) float64 {
	return math.RoundToEven(value*100) / 100
}
