package metrics

import (
	"bytes"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	dto "github.com/prometheus/client_model/go"
	"github.com/prometheus/common/expfmt"

	"github.com/prometheus/client_golang/prometheus"

	"github.com/itswl/balance-alert/internal/model"
)

// 断言一律对着抓取时的文本做，而不是去读 Vec 内部：
// 契约是"Prometheus 抓到什么"，WithLabelValues 还会顺手把已被清理的序列建回来，掩盖 bug。
//
// 这里没用 prometheus/testutil：它依赖 kylelemons/godebug，本仓库的 go.sum 里没有，
// 而这个任务不许动 go.mod。下面这几个 helper 就是 testutil 里 GatherAndCompare / ToFloat64 /
// CollectAndCount 的等价物，都走 Gather + expfmt 这条官方路径。

// 固定时钟：last_check_timestamp 这类指标要能断言出确切数值。
var testNow = time.Date(2026, 9, 16, 10, 30, 0, 0, time.UTC)

func newTestCollector(t *testing.T) (*Collector, *prometheus.Registry) {
	t.Helper()
	reg := prometheus.NewPedanticRegistry()
	c := New(reg)
	c.now = func() time.Time { return testNow }
	return c, reg
}

func gather(t *testing.T, reg *prometheus.Registry) []*dto.MetricFamily {
	t.Helper()
	mfs, err := reg.Gather()
	if err != nil {
		t.Fatalf("gather 失败: %v", err)
	}
	return mfs
}

// encode 把指标族渲染成文本格式，Gather 出来的族名与序列都已排好序。
func encode(t *testing.T, mfs []*dto.MetricFamily) string {
	t.Helper()
	var buf bytes.Buffer
	enc := expfmt.NewEncoder(&buf, expfmt.NewFormat(expfmt.TypeTextPlain))
	for _, mf := range mfs {
		if err := enc.Encode(mf); err != nil {
			t.Fatalf("编码 %s 失败: %v", mf.GetName(), err)
		}
	}
	return buf.String()
}

// dump 是整个注册表的抓取文本。
func dump(t *testing.T, reg *prometheus.Registry) string {
	t.Helper()
	return encode(t, gather(t, reg))
}

// compareText 只比对给定指标的完整输出，等价于 testutil.GatherAndCompare。
func compareText(t *testing.T, reg *prometheus.Registry, expected string, names ...string) {
	t.Helper()
	keep := map[string]bool{}
	for _, n := range names {
		keep[n] = true
	}
	var filtered []*dto.MetricFamily
	for _, mf := range gather(t, reg) {
		if keep[mf.GetName()] {
			filtered = append(filtered, mf)
		}
	}
	got := strings.TrimSpace(encode(t, filtered))
	if want := strings.TrimSpace(expected); got != want {
		t.Errorf("指标输出不符。\n实际:\n%s\n期望:\n%s", got, want)
	}
}

func mustContain(t *testing.T, text string, lines ...string) {
	t.Helper()
	for _, line := range lines {
		if !strings.Contains(text, line) {
			t.Errorf("缺少指标行:\n%s\n实际输出:\n%s", line, text)
		}
	}
}

func mustNotContain(t *testing.T, text string, lines ...string) {
	t.Helper()
	for _, line := range lines {
		if strings.Contains(text, line) {
			t.Errorf("本应被清理掉的指标行还在:\n%s\n实际输出:\n%s", line, text)
		}
	}
}

// seriesCount 是某个指标当前有几条序列，指标整个不存在时为 0。
func seriesCount(t *testing.T, reg *prometheus.Registry, name string) int {
	t.Helper()
	for _, mf := range gather(t, reg) {
		if mf.GetName() == name {
			return len(mf.GetMetric())
		}
	}
	return 0
}

// gaugeValue 读一条 Gauge 序列的值，读不到就让用例失败。
func gaugeValue(t *testing.T, reg *prometheus.Registry, name string, labels ...string) float64 {
	t.Helper()
	for _, mf := range gather(t, reg) {
		if mf.GetName() != name {
			continue
		}
		for _, m := range mf.GetMetric() {
			values := make([]string, 0, len(m.GetLabel()))
			for _, lp := range m.GetLabel() {
				values = append(values, lp.GetValue())
			}
			if strings.Join(values, "\x00") == strings.Join(labels, "\x00") {
				return m.GetGauge().GetValue()
			}
		}
	}
	t.Fatalf("没有找到序列 %s%v", name, labels)
	return 0
}

func okResult(project, provider, balanceType string, credits, threshold float64, needAlarm bool) model.CheckResult {
	return model.CheckResult{
		Project:   project,
		Provider:  provider,
		Type:      balanceType,
		Success:   true,
		Credits:   model.Ptr(credits),
		Threshold: model.Ptr(threshold),
		NeedAlarm: needAlarm,
	}
}

func failedResult(project, provider, balanceType string) model.CheckResult {
	return model.CheckResult{
		Project:  project,
		Provider: provider,
		Type:     balanceType,
		Success:  false,
		Error:    model.Ptr("connection timeout"),
	}
}

// exerciseAll 走一遍全部更新路径，让每个指标都至少有一条序列。
func exerciseAll(c *Collector) {
	c.UpdateBalance([]model.CheckResult{{
		Project: "openai-main", Provider: "openai", Type: model.TypeBalance, Success: true,
		Credits: model.Ptr(42.5), Threshold: model.Ptr(50.0),
		Runway: &model.Runway{BurnPerDay: model.Ptr(3.0), RunwayDays: model.Ptr(14.0)},
	}})
	c.UpdateSubscriptions([]model.SubscriptionResult{
		{Name: "claude", CycleType: model.CycleMonthly, DaysUntilRenewal: 3, Amount: 20},
	})
	c.UpdateEmailScan(model.ScanResult{Mailboxes: []model.MailboxResult{
		{Name: "work", TotalEmails: 10, AlertCount: 2, Success: true},
	}})
	c.RecordJobRun("alert_check", true, testNow, 1500*time.Millisecond)
	c.RecordNotification("balance", true)
}

// 指标清单即契约，逐条对着 grafana/README.md：少一个面板 No Data，多一个说明写歪了。
func TestMetricInventoryMatchesContract(t *testing.T) {
	c, reg := newTestCollector(t)
	exerciseAll(c)

	// value 是按名字排序后的标签名，Gather 出来的标签本身就是有序的。
	want := map[string]string{
		"balance_alert_balance":                    "project,provider,type",
		"balance_alert_threshold":                  "project,provider,type",
		"balance_alert_ratio":                      "project,provider,type",
		"balance_alert_status":                     "project,provider,type",
		"balance_alert_check_status":               "project,provider,type",
		"balance_alert_burn_rate_per_day":          "project,provider,type",
		"balance_alert_runway_days":                "project,provider,type",
		"balance_alert_subscription_days":          "cycle_type,name",
		"balance_alert_subscription_amount":        "cycle_type,name",
		"balance_alert_subscription_status":        "cycle_type,name",
		"balance_alert_email_mailbox_status":       "mailbox",
		"balance_alert_email_last_scan_emails":     "mailbox",
		"balance_alert_email_last_scan_alerts":     "mailbox",
		"balance_alert_email_scan_total":           "mailbox",
		"balance_alert_email_alerts_total":         "mailbox",
		"balance_alert_job_last_run_timestamp":     "task",
		"balance_alert_job_last_success_timestamp": "task",
		"balance_alert_job_last_status":            "task",
		"balance_alert_job_last_duration_seconds":  "task",
		"balance_alert_job_runs_total":             "status,task",
		"balance_alert_notifications_total":        "kind,status",
		"balance_alert_last_check_timestamp":       "check_type",
	}

	got := map[string]string{}
	for _, mf := range gather(t, reg) {
		if len(mf.GetMetric()) == 0 {
			t.Errorf("%s 没有任何序列", mf.GetName())
			continue
		}
		names := make([]string, 0, len(mf.GetMetric()[0].GetLabel()))
		for _, lp := range mf.GetMetric()[0].GetLabel() {
			names = append(names, lp.GetName())
		}
		sort.Strings(names)
		got[mf.GetName()] = strings.Join(names, ",")
	}

	for name, labels := range want {
		actual, ok := got[name]
		if !ok {
			t.Errorf("契约里的指标没有暴露出来: %s", name)
			continue
		}
		if actual != labels {
			t.Errorf("%s 的标签是 %q，契约要求 %q", name, actual, labels)
		}
	}
	for name := range got {
		if _, ok := want[name]; !ok {
			t.Errorf("多暴露了契约之外的指标: %s", name)
		}
	}
}

func TestBalanceMetricsText(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateBalance([]model.CheckResult{{
		Project: "openai-main", Provider: "openai", Type: model.TypeBalance, Success: true,
		Credits: model.Ptr(42.5), Threshold: model.Ptr(50.0), NeedAlarm: true,
		Runway: &model.Runway{BurnPerDay: model.Ptr(3.0), RunwayDays: model.Ptr(14.1666)},
	}})

	expected := `
# HELP balance_alert_balance Current balance or credits
# TYPE balance_alert_balance gauge
balance_alert_balance{project="openai-main",provider="openai",type="balance"} 42.5
# HELP balance_alert_burn_rate_per_day Average daily consumption over the burn-rate window
# TYPE balance_alert_burn_rate_per_day gauge
balance_alert_burn_rate_per_day{project="openai-main",provider="openai",type="balance"} 3
# HELP balance_alert_check_status Result of the last balance check (1=success, 0=failed; balance keeps its last good value)
# TYPE balance_alert_check_status gauge
balance_alert_check_status{project="openai-main",provider="openai",type="balance"} 1
# HELP balance_alert_ratio Balance to threshold ratio
# TYPE balance_alert_ratio gauge
balance_alert_ratio{project="openai-main",provider="openai",type="balance"} 0.85
# HELP balance_alert_runway_days Days of runway left at the current burn rate
# TYPE balance_alert_runway_days gauge
balance_alert_runway_days{project="openai-main",provider="openai",type="balance"} 14.1666
# HELP balance_alert_status Balance status (1=ok, 0=alert)
# TYPE balance_alert_status gauge
balance_alert_status{project="openai-main",provider="openai",type="balance"} 0
# HELP balance_alert_threshold Alert threshold
# TYPE balance_alert_threshold gauge
balance_alert_threshold{project="openai-main",provider="openai",type="balance"} 50
`
	compareText(t, reg, expected,
		"balance_alert_balance", "balance_alert_threshold", "balance_alert_ratio", "balance_alert_status",
		"balance_alert_check_status", "balance_alert_burn_rate_per_day", "balance_alert_runway_days")
}

// 阈值为 0 时比例必须是 0，不能是除零出来的 +Inf。
func TestRatioWithZeroThreshold(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateBalance([]model.CheckResult{okResult("p1", "glm", model.TypeQuota, 80, 0, false)})

	mustContain(t, dump(t, reg), `balance_alert_ratio{project="p1",provider="glm",type="quota"} 0`)
}

// 没攒够历史就不写跑道指标：写成 0 会被 runway_days < 3 这种告警当成马上见底。
func TestRunwayMetricsAbsentWithoutHistory(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateBalance([]model.CheckResult{okResult("p1", "openai", model.TypeBalance, 100, 20, false)})

	mustNotContain(t, dump(t, reg), "balance_alert_burn_rate_per_day", "balance_alert_runway_days")
}

// 检查失败只把 check_status 打成 0，余额相关序列保留上次成功的值。
func TestFailedCheckKeepsLastBalance(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateBalance([]model.CheckResult{{
		Project: "p1", Provider: "openai", Type: model.TypeBalance, Success: true,
		Credits: model.Ptr(100.0), Threshold: model.Ptr(20.0),
		Runway: &model.Runway{BurnPerDay: model.Ptr(5.0), RunwayDays: model.Ptr(20.0)},
	}})
	c.UpdateBalance([]model.CheckResult{failedResult("p1", "openai", model.TypeBalance)})

	mustContain(t, dump(t, reg),
		`balance_alert_balance{project="p1",provider="openai",type="balance"} 100`,
		`balance_alert_threshold{project="p1",provider="openai",type="balance"} 20`,
		`balance_alert_ratio{project="p1",provider="openai",type="balance"} 5`,
		`balance_alert_status{project="p1",provider="openai",type="balance"} 1`,
		`balance_alert_burn_rate_per_day{project="p1",provider="openai",type="balance"} 5`,
		`balance_alert_runway_days{project="p1",provider="openai",type="balance"} 20`,
		`balance_alert_check_status{project="p1",provider="openai",type="balance"} 0`,
	)

	// 恢复成功后余额跟着刷新，check_status 回到 1。
	c.UpdateBalance([]model.CheckResult{okResult("p1", "openai", model.TypeBalance, 88, 20, false)})
	mustContain(t, dump(t, reg),
		`balance_alert_balance{project="p1",provider="openai",type="balance"} 88`,
		`balance_alert_check_status{project="p1",provider="openai",type="balance"} 1`,
	)
}

// 失败结果里没有 type 时，按 project+provider 前缀也要认出那条要保留的余额序列。
func TestFailedCheckWithoutTypeStillKeepsBalance(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateBalance([]model.CheckResult{okResult("p1", "openai", model.TypeBalance, 100, 20, false)})
	c.UpdateBalance([]model.CheckResult{failedResult("p1", "openai", "")})

	text := dump(t, reg)
	mustContain(t, text,
		`balance_alert_balance{project="p1",provider="openai",type="balance"} 100`,
		`balance_alert_check_status{project="p1",provider="openai",type="unknown"} 0`,
	)
	// check_status 跟着本轮走：上一轮那条 type="balance" 要被清掉。
	mustNotContain(t, text, `balance_alert_check_status{project="p1",provider="openai",type="balance"}`)
}

// 项目改名后旧序列必须消失，否则面板上的 count() 永远偏大。
func TestRenamedProjectDropsOldSeries(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateBalance([]model.CheckResult{{
		Project: "old-name", Provider: "openai", Type: model.TypeBalance, Success: true,
		Credits: model.Ptr(100.0), Threshold: model.Ptr(20.0),
		Runway: &model.Runway{BurnPerDay: model.Ptr(5.0), RunwayDays: model.Ptr(20.0)},
	}})
	c.UpdateBalance([]model.CheckResult{okResult("new-name", "openai", model.TypeBalance, 100, 20, false)})

	text := dump(t, reg)
	mustNotContain(t, text, `project="old-name"`)
	mustContain(t, text, `balance_alert_balance{project="new-name",provider="openai",type="balance"} 100`)

	for name, want := range map[string]int{
		"balance_alert_balance":           1,
		"balance_alert_threshold":         1,
		"balance_alert_ratio":             1,
		"balance_alert_status":            1,
		"balance_alert_check_status":      1,
		"balance_alert_burn_rate_per_day": 0, // 新项目没有历史，这两条压根没写过
		"balance_alert_runway_days":       0,
	} {
		if got := seriesCount(t, reg, name); got != want {
			t.Errorf("%s 剩下 %d 条序列，期望 %d", name, got, want)
		}
	}
}

// 项目被删光时传空切片，所有余额序列一起清掉。
func TestEmptyBalanceUpdateClearsSeries(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateBalance([]model.CheckResult{
		okResult("p1", "openai", model.TypeBalance, 100, 20, false),
		okResult("p2", "glm", model.TypeQuota, 80, 30, true),
	})
	c.UpdateBalance(nil)

	text := dump(t, reg)
	mustNotContain(t, text, "balance_alert_balance{", "balance_alert_check_status{", "balance_alert_status{")
	// last_check_timestamp 不受影响：这一轮确实检查过了。
	mustContain(t, text, `balance_alert_last_check_timestamp{check_type="balance"}`)
}

func TestSubscriptionStatus(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateSubscriptions([]model.SubscriptionResult{
		{Name: "claude", CycleType: model.CycleMonthly, DaysUntilRenewal: 3, Amount: 20, NeedAlert: true},
		{Name: "github", CycleType: model.CycleYearly, DaysUntilRenewal: 200, Amount: 100},
		// 已续费优先于 need_alert：本周期交过钱了就不该再提醒。
		{Name: "vps", CycleType: model.CycleMonthly, DaysUntilRenewal: 28, Amount: 5, NeedAlert: true, AlreadyRenewed: true},
	})

	expected := `
# HELP balance_alert_subscription_status Subscription status (1=normal, 0=needs_renewal, -1=renewed_in_cycle)
# TYPE balance_alert_subscription_status gauge
balance_alert_subscription_status{cycle_type="monthly",name="claude"} 0
balance_alert_subscription_status{cycle_type="monthly",name="vps"} -1
balance_alert_subscription_status{cycle_type="yearly",name="github"} 1
`
	compareText(t, reg, expected, "balance_alert_subscription_status")

	mustContain(t, dump(t, reg),
		`balance_alert_subscription_days{cycle_type="monthly",name="claude"} 3`,
		`balance_alert_subscription_amount{cycle_type="yearly",name="github"} 100`,
	)
}

func TestSubscriptionRenameAndDisableDropSeries(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateSubscriptions([]model.SubscriptionResult{
		{Name: "old-sub", CycleType: model.CycleMonthly, DaysUntilRenewal: 3, Amount: 20},
	})
	c.UpdateSubscriptions([]model.SubscriptionResult{
		{Name: "new-sub", CycleType: model.CycleMonthly, DaysUntilRenewal: 3, Amount: 20},
	})

	text := dump(t, reg)
	mustNotContain(t, text, `name="old-sub"`)
	mustContain(t, text, `balance_alert_subscription_days{cycle_type="monthly",name="new-sub"} 3`)

	// 订阅功能关掉时调用方传空切片，序列随之清空。
	c.UpdateSubscriptions(nil)
	mustNotContain(t, dump(t, reg), "balance_alert_subscription_days{", "balance_alert_subscription_status{")
}

func TestEmailScanGaugesAndCounters(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateEmailScan(model.ScanResult{Mailboxes: []model.MailboxResult{
		{Name: "work", TotalEmails: 10, AlertCount: 2, Success: true},
		{Name: "broken", Success: false, Error: model.Ptr("auth failed")},
	}})

	mustContain(t, dump(t, reg),
		`balance_alert_email_mailbox_status{mailbox="work"} 1`,
		`balance_alert_email_mailbox_status{mailbox="broken"} 0`,
		`balance_alert_email_last_scan_emails{mailbox="work"} 10`,
		`balance_alert_email_last_scan_alerts{mailbox="work"} 2`,
	)

	// 第二轮：Gauge 反映本次扫描，Counter 累加；broken 这个邮箱被删了。
	c.UpdateEmailScan(model.ScanResult{Mailboxes: []model.MailboxResult{
		{Name: "work", TotalEmails: 5, AlertCount: 1, Success: true},
	}})

	text := dump(t, reg)
	mustContain(t, text,
		`balance_alert_email_last_scan_emails{mailbox="work"} 5`,
		`balance_alert_email_last_scan_alerts{mailbox="work"} 1`,
		`balance_alert_email_scan_total{mailbox="work"} 15`,
		`balance_alert_email_alerts_total{mailbox="work"} 3`,
	)
	mustNotContain(t, text,
		`balance_alert_email_mailbox_status{mailbox="broken"}`,
		`balance_alert_email_last_scan_emails{mailbox="broken"}`,
	)
	// 累计 Counter 不删：删了 increase() 会看到一次假重置。
	mustContain(t, text, `balance_alert_email_scan_total{mailbox="broken"} 0`)
}

func TestRecordJobRun(t *testing.T) {
	c, reg := newTestCollector(t)
	start := time.Date(2026, 9, 16, 9, 0, 0, 0, time.UTC)

	c.RecordJobRun("alert_check", true, start, 1500*time.Millisecond)
	c.RecordJobRun("alert_check", false, start.Add(time.Hour), 2*time.Second)

	if got := gaugeValue(t, reg, "balance_alert_job_last_run_timestamp", "alert_check"); got != unixSeconds(start.Add(time.Hour)) {
		t.Errorf("last_run = %v，期望最后一次运行的时刻", got)
	}
	// 失败不刷新 last_success：告警规则靠 time() - last_success 判断任务多久没成功了。
	if got := gaugeValue(t, reg, "balance_alert_job_last_success_timestamp", "alert_check"); got != unixSeconds(start) {
		t.Errorf("last_success = %v，期望停在上次成功的时刻", got)
	}
	if got := gaugeValue(t, reg, "balance_alert_job_last_status", "alert_check"); got != 0 {
		t.Errorf("last_status = %v，期望 0", got)
	}
	if got := gaugeValue(t, reg, "balance_alert_job_last_duration_seconds", "alert_check"); got != 2 {
		t.Errorf("last_duration_seconds = %v，期望 2", got)
	}

	expected := `
# HELP balance_alert_job_runs_total Job runs by result
# TYPE balance_alert_job_runs_total counter
balance_alert_job_runs_total{status="failed",task="alert_check"} 1
balance_alert_job_runs_total{status="success",task="alert_check"} 1
`
	compareText(t, reg, expected, "balance_alert_job_runs_total")

	// 标签叫 task 不叫 job：抓取时和 Prometheus 自带的 job 冲突会被改名成 exported_job。
	mustContain(t, dump(t, reg), `balance_alert_job_last_status{task="alert_check"}`)
	mustNotContain(t, dump(t, reg), `{job="alert_check"}`)
}

func TestRecordJobRunWithZeroStartTime(t *testing.T) {
	c, reg := newTestCollector(t)
	c.RecordJobRun("email_scan", true, time.Time{}, time.Second)

	if got := gaugeValue(t, reg, "balance_alert_job_last_run_timestamp", "email_scan"); got != unixSeconds(testNow) {
		t.Errorf("last_run = %v，期望退回当前时间 %v", got, unixSeconds(testNow))
	}
}

func TestNotificationsByKindAndStatus(t *testing.T) {
	c, reg := newTestCollector(t)
	c.RecordNotification("balance", true)
	c.RecordNotification("balance", true)
	c.RecordNotification("balance", false)
	c.RecordNotification("weekly_report", true)
	c.RecordNotification("mailbox_error", false)

	expected := `
# HELP balance_alert_notifications_total Webhook notifications by kind and result
# TYPE balance_alert_notifications_total counter
balance_alert_notifications_total{kind="balance",status="failed"} 1
balance_alert_notifications_total{kind="balance",status="success"} 2
balance_alert_notifications_total{kind="mailbox_error",status="failed"} 1
balance_alert_notifications_total{kind="weekly_report",status="success"} 1
`
	compareText(t, reg, expected, "balance_alert_notifications_total")
}

func TestLastCheckTimestamp(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateBalance(nil)
	c.UpdateSubscriptions(nil)
	c.UpdateEmailScan(model.ScanResult{})

	ts := unixSeconds(testNow)
	expected := fmt.Sprintf(`
# HELP balance_alert_last_check_timestamp Timestamp of last check
# TYPE balance_alert_last_check_timestamp gauge
balance_alert_last_check_timestamp{check_type="balance"} %v
balance_alert_last_check_timestamp{check_type="email"} %v
balance_alert_last_check_timestamp{check_type="subscription"} %v
`, ts, ts, ts)
	compareText(t, reg, expected, "balance_alert_last_check_timestamp")
}

// 标签值缺失时退回 unknown / monthly，免得面板上出现 project="" 这种认不出来的序列。
func TestMissingLabelsFallBack(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateBalance([]model.CheckResult{{Success: true, Credits: model.Ptr(1.0)}})
	c.UpdateSubscriptions([]model.SubscriptionResult{{DaysUntilRenewal: 1}})
	c.UpdateEmailScan(model.ScanResult{Mailboxes: []model.MailboxResult{{Success: true}}})

	mustContain(t, dump(t, reg),
		`balance_alert_balance{project="unknown",provider="unknown",type="unknown"} 1`,
		`balance_alert_subscription_days{cycle_type="monthly",name="unknown"} 1`,
		`balance_alert_email_mailbox_status{mailbox="unknown"} 1`,
	)
}

// 余额查不到时按 0 记，指针语义只在 API 响应里有意义。
func TestNilBalanceCountsAsZero(t *testing.T) {
	c, reg := newTestCollector(t)
	c.UpdateBalance([]model.CheckResult{{Project: "p1", Provider: "openai", Type: model.TypeBalance, Success: true}})

	mustContain(t, dump(t, reg),
		`balance_alert_balance{project="p1",provider="openai",type="balance"} 0`,
		`balance_alert_threshold{project="p1",provider="openai",type="balance"} 0`,
		`balance_alert_ratio{project="p1",provider="openai",type="balance"} 0`,
	)
}

func TestHandlerServesMetrics(t *testing.T) {
	c, _ := newTestCollector(t)
	exerciseAll(c)

	rec := httptest.NewRecorder()
	c.Handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/metrics", nil))

	if rec.Code != http.StatusOK {
		t.Fatalf("状态码 %d", rec.Code)
	}
	mustContain(t, rec.Body.String(), "balance_alert_balance{", "balance_alert_notifications_total{")
}

// 调度线程和 HTTP 处理器会同时更新指标，序列台账是普通 map，靠这条用例（配 -race）盯住。
func TestConcurrentUpdates(t *testing.T) {
	c, reg := newTestCollector(t)

	var wg sync.WaitGroup
	for i := range 8 {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			c.UpdateBalance([]model.CheckResult{okResult(fmt.Sprintf("p%d", i), "openai", model.TypeBalance, float64(i), 10, false)})
			c.UpdateSubscriptions([]model.SubscriptionResult{{Name: fmt.Sprintf("s%d", i), CycleType: model.CycleMonthly}})
			c.UpdateEmailScan(model.ScanResult{Mailboxes: []model.MailboxResult{{Name: fmt.Sprintf("m%d", i), Success: true}}})
			c.RecordJobRun("alert_check", true, testNow, time.Second)
			c.RecordNotification("balance", true)
		}(i)
	}
	wg.Wait()

	// 每轮都是全量更新，最后活下来的只能是某一轮的那一条。
	if got := seriesCount(t, reg, "balance_alert_balance"); got != 1 {
		t.Errorf("余额剩下 %d 条序列，期望 1", got)
	}
	mustContain(t, dump(t, reg), `balance_alert_job_runs_total{status="success",task="alert_check"} 8`)
}
