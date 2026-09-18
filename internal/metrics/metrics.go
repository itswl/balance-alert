// Package metrics provides the package implementation.
//
// Implementation note.
// Implementation note.
//
// Implementation note.
// Implementation note.
package metrics

import (
	"net/http"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"github.com/itswl/quotapulse/internal/model"
)

// Implementation note.
var (
	balanceLabels      = []string{"project", "provider", "type"}
	subscriptionLabels = []string{"name", "cycle_type"}
	mailboxLabels      = []string{"mailbox"}
	taskLabels         = []string{"task"}
)

// Implementation note.
const (
	groupBalance      = "balance" // operation, operation, operation, operation, operation, operation
	groupCheck        = "check"   // operation,operation:operation,operation
	groupSubscription = "subscription"
	groupMailbox      = "mailbox"
)

// Implementation note.
var groupArity = map[string]int{
	groupBalance:      len(balanceLabels),
	groupCheck:        len(balanceLabels),
	groupSubscription: len(subscriptionLabels),
	groupMailbox:      len(mailboxLabels),
}

// Implementation note.
// Implementation note.
type labelValues [3]string

// Implementation note.
const unknown = "unknown"

// Implementation note.
const (
	statusSuccess = "success"
	statusFailed  = "failed"
)

// Implementation note.
// Implementation note.
type Collector struct {
	// Implementation note.
	balance     *prometheus.GaugeVec
	threshold   *prometheus.GaugeVec
	ratio       *prometheus.GaugeVec
	status      *prometheus.GaugeVec
	checkStatus *prometheus.GaugeVec
	burnRate    *prometheus.GaugeVec
	runwayDays  *prometheus.GaugeVec

	// Implementation note.
	subDays   *prometheus.GaugeVec
	subAmount *prometheus.GaugeVec
	subStatus *prometheus.GaugeVec

	// Implementation note.
	mailboxStatus  *prometheus.GaugeVec
	lastScanEmails *prometheus.GaugeVec
	lastScanAlerts *prometheus.GaugeVec
	scanTotal      *prometheus.CounterVec
	alertsTotal    *prometheus.CounterVec

	// Implementation note.
	jobLastRun      *prometheus.GaugeVec
	jobLastSuccess  *prometheus.GaugeVec
	jobLastStatus   *prometheus.GaugeVec
	jobLastDuration *prometheus.GaugeVec
	jobRuns         *prometheus.CounterVec

	// Implementation note.
	notifications *prometheus.CounterVec
	lastCheck     *prometheus.GaugeVec

	gatherer prometheus.Gatherer

	// Implementation note.
	// Implementation note.
	mu     sync.Mutex
	series map[string]map[labelValues]struct{}

	now func() time.Time // operation
}

// Implementation note.
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
		balance:   gauge("quotapulse_balance", "Current balance or credits", balanceLabels),
		threshold: gauge("quotapulse_threshold", "Alert threshold", balanceLabels),
		ratio:     gauge("quotapulse_ratio", "Balance to threshold ratio", balanceLabels),
		status:    gauge("quotapulse_status", "Balance status (1=ok, 0=alert)", balanceLabels),
		checkStatus: gauge("quotapulse_check_status",
			"Result of the last balance check (1=success, 0=failed; balance keeps its last good value)", balanceLabels),
		burnRate: gauge("quotapulse_burn_rate_per_day",
			"Average daily consumption over the burn-rate window", balanceLabels),
		runwayDays: gauge("quotapulse_runway_days",
			"Days of runway left at the current burn rate", balanceLabels),

		subDays:   gauge("quotapulse_subscription_days", "Days until subscription renewal", subscriptionLabels),
		subAmount: gauge("quotapulse_subscription_amount", "Subscription renewal amount", subscriptionLabels),
		subStatus: gauge("quotapulse_subscription_status",
			"Subscription status (1=normal, 0=needs_renewal, -1=renewed_in_cycle)", subscriptionLabels),

		mailboxStatus: gauge("quotapulse_email_mailbox_status",
			"Mailbox status in the last scan (1=ok, 0=failed)", mailboxLabels),
		lastScanEmails: gauge("quotapulse_email_last_scan_emails", "Emails scanned in the last scan", mailboxLabels),
		lastScanAlerts: gauge("quotapulse_email_last_scan_alerts", "Alert emails found in the last scan", mailboxLabels),
		scanTotal:      counter("quotapulse_email_scan_total", "Total emails scanned", mailboxLabels),
		alertsTotal:    counter("quotapulse_email_alerts_total", "Total alert emails found", mailboxLabels),

		// Implementation note.
		jobLastRun:      gauge("quotapulse_job_last_run_timestamp", "Unix time of the last run", taskLabels),
		jobLastSuccess:  gauge("quotapulse_job_last_success_timestamp", "Unix time of the last successful run", taskLabels),
		jobLastStatus:   gauge("quotapulse_job_last_status", "Result of the last run (1=success, 0=failed)", taskLabels),
		jobLastDuration: gauge("quotapulse_job_last_duration_seconds", "Duration of the last run in seconds", taskLabels),
		jobRuns:         counter("quotapulse_job_runs_total", "Job runs by result", []string{"task", "status"}),

		notifications: counter("quotapulse_notifications_total",
			"Webhook notifications by kind and result", []string{"kind", "status"}),
		lastCheck: gauge("quotapulse_last_check_timestamp", "Timestamp of last check", []string{"check_type"}),

		series: map[string]map[labelValues]struct{}{},
		now:    time.Now,
	}

	// Implementation note.
	// Implementation note.
	if g, ok := reg.(prometheus.Gatherer); ok {
		c.gatherer = g
	} else {
		c.gatherer = prometheus.DefaultGatherer
	}
	return c
}

// Implementation note.
func (c *Collector) Handler() http.Handler {
	return promhttp.HandlerFor(c.gatherer, promhttp.HandlerOpts{})
}

// Implementation note.

// Implementation note.
func (c *Collector) set(vec *prometheus.GaugeVec, group string, lv labelValues, value float64) {
	vec.WithLabelValues(lv[:groupArity[group]]...).Set(value)
	set, ok := c.series[group]
	if !ok {
		set = map[labelValues]struct{}{}
		c.series[group] = set
	}
	set[lv] = struct{}{}
}

// Implementation note.
// Implementation note.
//
// Implementation note.
// Implementation note.
// Implementation note.
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

// Implementation note.

// Implementation note.
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

		// Implementation note.
		// Implementation note.
		// Implementation note.
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

	// Implementation note.
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

	// Implementation note.
	// Implementation note.
	if r.Runway != nil {
		if r.Runway.BurnPerDay != nil {
			c.set(c.burnRate, groupBalance, lv, *r.Runway.BurnPerDay)
		}
		if r.Runway.RunwayDays != nil {
			c.set(c.runwayDays, groupBalance, lv, *r.Runway.RunwayDays)
		}
	}
}

// Implementation note.

// Implementation note.
func (c *Collector) UpdateSubscriptions(results []model.SubscriptionResult) {
	c.mu.Lock()
	defer c.mu.Unlock()

	keep := map[labelValues]struct{}{}
	for _, r := range results {
		lv := labelValues{orUnknown(r.Name), orDefault(r.CycleType, model.CycleMonthly)}

		// Implementation note.
		// Implementation note.
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

// Implementation note.

// Implementation note.
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

// Implementation note.

// Implementation note.
//
// Implementation note.
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

	// Implementation note.
	if success {
		c.jobLastSuccess.WithLabelValues(task).Set(ts)
	}
}

// Implementation note.
// balance / subscription / email / mailbox_error / runway / spend_spike / weekly_report。
func (c *Collector) RecordNotification(kind string, ok bool) {
	status := statusFailed
	if ok {
		status = statusSuccess
	}
	c.notifications.WithLabelValues(kind, status).Inc()
}

// Implementation note.

func orUnknown(s string) string { return orDefault(s, unknown) }

func orDefault(s, fallback string) string {
	if s == "" {
		return fallback
	}
	return s
}

// Implementation note.
func deref(v *float64) float64 {
	if v == nil {
		return 0
	}
	return *v
}

// Implementation note.
// Implementation note.
func unixSeconds(t time.Time) float64 {
	return float64(t.Unix()) + float64(t.Nanosecond())/1e9
}
