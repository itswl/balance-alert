// Package metrics 把每一轮检查的结果翻译成 Prometheus 指标。
//
// 指标名与标签名是对外契约（见 grafana/README.md）：既有的面板、告警规则和抓取配置都按这套名字写死了，
// 改一个字就会让线上看板变成 No Data，所以这里的字符串字面量不许"顺手优化"。
//
// 指标只在跑定时任务的这个进程里更新，命令行手动跑出来的结果不进指标——这和 Python 版一致。
package metrics

import (
	"net/http"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/itswl/balance-alert/internal/model"
)

// 标签顺序就是 WithLabelValues / DeleteLabelValues 的入参顺序，调换会把序列写错位。
var (
	balanceLabels      = []string{"project", "provider", "type"}
	subscriptionLabels = []string{"name", "cycle_type"}
	mailboxLabels      = []string{"mailbox"}
	taskLabels         = []string{"task"}
)

// 序列分组：同一组里的 Gauge 标签集相同、生命周期相同，过期时一起删。
const (
	groupBalance      = "balance" // 余额、阈值、比例、状态、消耗、跑道
	groupCheck        = "check"   // 检查成败，单独一组：项目查失败时它要更新，余额那组反而要原样留着
	groupSubscription = "subscription"
	groupMailbox      = "mailbox"
)

// 每组的标签个数。labelValues 是定长数组，取前 n 个才是这一组真正的标签值。
var groupArity = map[string]int{
	groupBalance:      len(balanceLabels),
	groupCheck:        len(balanceLabels),
	groupSubscription: len(subscriptionLabels),
	groupMailbox:      len(mailboxLabels),
}

// labelValues 用定长数组而不是切片：切片不可比较、当不了 map 键，而每组的标签个数是固定的
// （余额 3、订阅 2、邮箱 1），多出来的位置留空就行。
type labelValues [3]string

// 标签值缺失时的兜底，避免写出 project="" 这种在面板上根本认不出来的序列。
const unknown = "unknown"

// Counter 的 status 标签取值。
const (
	statusSuccess = "success"
	statusFailed  = "failed"
)

// Collector 持有全部指标，并记着每个分组当前有哪些标签组合，
// 好在项目 / 订阅 / 邮箱被删掉或改名后清理掉旧序列。
type Collector struct {
	// 余额
	balance     *prometheus.GaugeVec
	threshold   *prometheus.GaugeVec
	ratio       *prometheus.GaugeVec
	status      *prometheus.GaugeVec
	checkStatus *prometheus.GaugeVec
	burnRate    *prometheus.GaugeVec
	runwayDays  *prometheus.GaugeVec

	// 订阅续费
	subDays   *prometheus.GaugeVec
	subAmount *prometheus.GaugeVec
	subStatus *prometheus.GaugeVec

	// 邮箱扫描
	mailboxStatus  *prometheus.GaugeVec
	lastScanEmails *prometheus.GaugeVec
	lastScanAlerts *prometheus.GaugeVec
	scanTotal      *prometheus.CounterVec
	alertsTotal    *prometheus.CounterVec

	// 定时任务
	jobLastRun      *prometheus.GaugeVec
	jobLastSuccess  *prometheus.GaugeVec
	jobLastStatus   *prometheus.GaugeVec
	jobLastDuration *prometheus.GaugeVec
	jobRuns         *prometheus.CounterVec

	// 通知与各类检查的最近更新时间
	notifications *prometheus.CounterVec
	lastCheck     *prometheus.GaugeVec

	gatherer prometheus.Gatherer

	// Vec 自身是并发安全的，这把锁只护住下面的序列台账：
	// 调度线程和 HTTP 处理器都可能触发更新，台账是普通 map，读写必须串行。
	mu     sync.Mutex
	series map[string]map[labelValues]struct{}

	now func() time.Time // 测试里替换成固定时钟
}

// New 注册全部指标。reg 传 nil 用默认注册表。
func New(reg prometheus.Registerer) *Collector {
	if reg == nil {
		reg = prometheus.DefaultRegisterer
	}
	f := promauto.With(reg)
	gauge := func(name, help string, labels []string) *prometheus.GaugeVec {
		return f.NewGaugeVec(prometheus.GaugeOpts{Name: name, Help: help}, labels)
	}
	counter := func(name, help string, labels []string) *prometheus.CounterVec {
		return f.NewCounterVec(prometheus.CounterOpts{Name: name, Help: help}, labels)
	}

	c := &Collector{
		balance:   gauge("balance_alert_balance", "Current balance or credits", balanceLabels),
		threshold: gauge("balance_alert_threshold", "Alert threshold", balanceLabels),
		ratio:     gauge("balance_alert_ratio", "Balance to threshold ratio", balanceLabels),
		status:    gauge("balance_alert_status", "Balance status (1=ok, 0=alert)", balanceLabels),
		checkStatus: gauge("balance_alert_check_status",
			"Result of the last balance check (1=success, 0=failed; balance keeps its last good value)", balanceLabels),
		burnRate: gauge("balance_alert_burn_rate_per_day",
			"Average daily consumption over the burn-rate window", balanceLabels),
		runwayDays: gauge("balance_alert_runway_days",
			"Days of runway left at the current burn rate", balanceLabels),

		subDays:   gauge("balance_alert_subscription_days", "Days until subscription renewal", subscriptionLabels),
		subAmount: gauge("balance_alert_subscription_amount", "Subscription renewal amount", subscriptionLabels),
		subStatus: gauge("balance_alert_subscription_status",
			"Subscription status (1=normal, 0=needs_renewal, -1=renewed_in_cycle)", subscriptionLabels),

		mailboxStatus: gauge("balance_alert_email_mailbox_status",
			"Mailbox status in the last scan (1=ok, 0=failed)", mailboxLabels),
		lastScanEmails: gauge("balance_alert_email_last_scan_emails", "Emails scanned in the last scan", mailboxLabels),
		lastScanAlerts: gauge("balance_alert_email_last_scan_alerts", "Alert emails found in the last scan", mailboxLabels),
		scanTotal:      counter("balance_alert_email_scan_total", "Total emails scanned", mailboxLabels),
		alertsTotal:    counter("balance_alert_email_alerts_total", "Total alert emails found", mailboxLabels),

		// 标签叫 task 不叫 job：Prometheus 抓取时会把与自带 job 标签冲突的那个改名成 exported_job。
		jobLastRun:      gauge("balance_alert_job_last_run_timestamp", "Unix time of the last run", taskLabels),
		jobLastSuccess:  gauge("balance_alert_job_last_success_timestamp", "Unix time of the last successful run", taskLabels),
		jobLastStatus:   gauge("balance_alert_job_last_status", "Result of the last run (1=success, 0=failed)", taskLabels),
		jobLastDuration: gauge("balance_alert_job_last_duration_seconds", "Duration of the last run in seconds", taskLabels),
		jobRuns:         counter("balance_alert_job_runs_total", "Job runs by result", []string{"task", "status"}),

		notifications: counter("balance_alert_notifications_total",
			"Webhook notifications by kind and result", []string{"kind", "status"}),
		lastCheck: gauge("balance_alert_last_check_timestamp", "Timestamp of last check", []string{"check_type"}),

		series: map[string]map[labelValues]struct{}{},
		now:    time.Now,
	}

	// Handler 要的是 Gatherer。默认注册表和 *prometheus.Registry 两者兼具，
	// 碰上只实现了 Registerer 的包装类型就退回默认的，至少让 /metrics 还能起来。
	if g, ok := reg.(prometheus.Gatherer); ok {
		c.gatherer = g
	} else {
		c.gatherer = prometheus.DefaultGatherer
	}
	return c
}

// Handler 暴露 /metrics。
func (c *Collector) Handler() http.Handler {
	return promhttp.HandlerFor(c.gatherer, promhttp.HandlerOpts{})
}

// ---------- 序列台账 ----------

// set 写一个 Gauge 并把标签组合记进分组台账，供下一轮 prune 比对。调用前必须持锁。
func (c *Collector) set(vec *prometheus.GaugeVec, group string, lv labelValues, value float64) {
	vec.WithLabelValues(lv[:groupArity[group]]...).Set(value)
	set, ok := c.series[group]
	if !ok {
		set = map[labelValues]struct{}{}
		c.series[group] = set
	}
	set[lv] = struct{}{}
}

// prune 把 group 里不在 keep 中的标签组合从相关 Gauge 上删掉——项目改名或下线后，
// 面板上不能一直挂着一个早就不存在的序列，否则 count() 之类的统计永远偏大。
//
// 这里不能用 Vec.Reset()：Reset 清空整个 Vec，连"本轮没更新到但必须留着"的序列一起没了，
// 而检查失败时保留的上次余额恰好就是这一类。所以只按标签精确删。
// 累计型 Counter（邮箱扫描数等）同理不删：删了下次从 0 开始，increase() 会看到一次假重置。
func (c *Collector) prune(group string, keep map[labelValues]struct{}, vecs ...*prometheus.GaugeVec) {
	n := groupArity[group]
	for lv := range c.series[group] {
		if _, ok := keep[lv]; ok {
			continue
		}
		for _, vec := range vecs {
			vec.DeleteLabelValues(lv[:n]...)
		}
	}
	c.series[group] = keep
}

// ---------- 余额 ----------

// UpdateBalance 更新余额一族指标。传空切片等于"一个项目都没有"，旧序列会被全部清掉。
func (c *Collector) UpdateBalance(results []model.CheckResult) {
	c.mu.Lock()
	defer c.mu.Unlock()

	keepBalance := map[labelValues]struct{}{}
	keepCheck := map[labelValues]struct{}{}

	for _, r := range results {
		lv := labelValues{orUnknown(r.Project), orUnknown(r.Provider), orUnknown(r.Type)}
		keepCheck[lv] = struct{}{}

		if r.Success {
			c.recordBalance(lv, r)
			keepBalance[lv] = struct{}{}
			continue
		}

		// 查不到余额时只把 check_status 打成 0，余额那组一个字节都不动：
		// 面板要显示的是"上次成功时的余额 + 这次检查失败"，而不是余额凭空消失。
		// 按 project+provider 前缀匹配是因为失败结果里的 type 未必和上次成功时一样。
		c.set(c.checkStatus, groupCheck, lv, 0)
		for old := range c.series[groupBalance] {
			if old[0] == lv[0] && old[1] == lv[1] {
				keepBalance[old] = struct{}{}
			}
		}
	}

	c.prune(groupBalance, keepBalance,
		c.balance, c.threshold, c.ratio, c.status, c.burnRate, c.runwayDays)
	c.prune(groupCheck, keepCheck, c.checkStatus)
	c.lastCheck.WithLabelValues("balance").Set(unixSeconds(c.now()))
}

func (c *Collector) recordBalance(lv labelValues, r model.CheckResult) {
	credits := deref(r.Credits)
	threshold := deref(r.Threshold)

	c.set(c.checkStatus, groupCheck, lv, 1)
	c.set(c.balance, groupBalance, lv, credits)
	c.set(c.threshold, groupBalance, lv, threshold)

	// 阈值为 0 时比例写 0：除零会出 +Inf，面板上的仪表盘会直接画爆。
	ratio := 0.0
	if threshold > 0 {
		ratio = credits / threshold
	}
	c.set(c.ratio, groupBalance, lv, ratio)

	ok := 1.0
	if r.NeedAlarm {
		ok = 0
	}
	c.set(c.status, groupBalance, lv, ok)

	// 消耗画像要攒够历史才算得出来；算不出来就不写这两条，
	// 面板上表现为"无数据"而不是 0——0 会被 runway_days < 3 这类告警当成马上见底。
	if r.Runway != nil {
		if r.Runway.BurnPerDay != nil {
			c.set(c.burnRate, groupBalance, lv, *r.Runway.BurnPerDay)
		}
		if r.Runway.RunwayDays != nil {
			c.set(c.runwayDays, groupBalance, lv, *r.Runway.RunwayDays)
		}
	}
}

// ---------- 订阅 ----------

// UpdateSubscriptions 更新续费指标。订阅功能关掉时调用方传空切片，旧序列随之清掉。
func (c *Collector) UpdateSubscriptions(results []model.SubscriptionResult) {
	c.mu.Lock()
	defer c.mu.Unlock()

	keep := map[labelValues]struct{}{}
	for _, r := range results {
		lv := labelValues{orUnknown(r.Name), orDefault(r.CycleType, model.CycleMonthly)}

		// -1 是"本周期已经续过费"，和 0（该续费了）区分开：面板上这两种都不是 1，
		// 但已续费的不该再提醒。
		status := 1.0
		switch {
		case r.AlreadyRenewed:
			status = -1
		case r.NeedAlert:
			status = 0
		}

		c.set(c.subDays, groupSubscription, lv, float64(r.DaysUntilRenewal))
		c.set(c.subAmount, groupSubscription, lv, r.Amount)
		c.set(c.subStatus, groupSubscription, lv, status)
		keep[lv] = struct{}{}
	}

	c.prune(groupSubscription, keep, c.subDays, c.subAmount, c.subStatus)
	c.lastCheck.WithLabelValues("subscription").Set(unixSeconds(c.now()))
}

// ---------- 邮箱扫描 ----------

// UpdateEmailScan 更新邮箱指标：Gauge 反映上次扫描，Counter 只增不减。
func (c *Collector) UpdateEmailScan(result model.ScanResult) {
	c.mu.Lock()
	defer c.mu.Unlock()

	keep := map[labelValues]struct{}{}
	for _, m := range result.Mailboxes {
		lv := labelValues{orUnknown(m.Name)}

		ok := 0.0
		if m.Success && m.Error == nil {
			ok = 1
		}
		c.set(c.mailboxStatus, groupMailbox, lv, ok)
		c.set(c.lastScanEmails, groupMailbox, lv, float64(m.TotalEmails))
		c.set(c.lastScanAlerts, groupMailbox, lv, float64(m.AlertCount))

		c.scanTotal.WithLabelValues(lv[0]).Add(float64(m.TotalEmails))
		c.alertsTotal.WithLabelValues(lv[0]).Add(float64(m.AlertCount))
		keep[lv] = struct{}{}
	}

	c.prune(groupMailbox, keep, c.mailboxStatus, c.lastScanEmails, c.lastScanAlerts)
	c.lastCheck.WithLabelValues("email").Set(unixSeconds(c.now()))
}

// ---------- 定时任务 / 通知 ----------

// RecordJobRun 记一次任务运行。startedAt 是零值时按当前时间算。
//
// 任务这几条不做序列清理：任务清单在代码里写死，不会像项目那样被删掉或改名。
func (c *Collector) RecordJobRun(task string, success bool, startedAt time.Time, duration time.Duration) {
	ts := unixSeconds(startedAt)
	if startedAt.IsZero() {
		ts = unixSeconds(c.now())
	}

	c.jobLastRun.WithLabelValues(task).Set(ts)
	c.jobLastDuration.WithLabelValues(task).Set(duration.Seconds())

	status := statusFailed
	result := 0.0
	if success {
		status, result = statusSuccess, 1
	}
	c.jobLastStatus.WithLabelValues(task).Set(result)
	c.jobRuns.WithLabelValues(task, status).Inc()

	// 失败时不动 last_success：告警规则就是靠 time() - last_success 判断任务多久没成功了。
	if success {
		c.jobLastSuccess.WithLabelValues(task).Set(ts)
	}
}

// RecordNotification 记一次 Webhook 通知。kind 取值见 grafana/README.md：
// balance / subscription / email / mailbox_error / runway / spend_spike / weekly_report。
func (c *Collector) RecordNotification(kind string, ok bool) {
	status := statusFailed
	if ok {
		status = statusSuccess
	}
	c.notifications.WithLabelValues(kind, status).Inc()
}

// ---------- 小工具 ----------

func orUnknown(s string) string { return orDefault(s, unknown) }

func orDefault(s, fallback string) string {
	if s == "" {
		return fallback
	}
	return s
}

// deref 把"没查到"折成 0：余额指标必须是个数，指针语义只在 API 响应里有意义。
func deref(v *float64) float64 {
	if v == nil {
		return 0
	}
	return *v
}

// unixSeconds 保留亚秒精度，和 Python 的 time.time() 对齐。
func unixSeconds(t time.Time) float64 {
	return float64(t.Unix()) + float64(t.Nanosecond())/1e9
}
