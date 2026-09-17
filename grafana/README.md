# Prometheus and Grafana

Set `ENABLE_PROMETHEUS=true` to expose `/metrics` on `METRICS_PORT` (default `9100`). Scheduled jobs, dashboard refreshes, and immediate scans all update the same process-local metrics; CLI-only runs do not.

## Metrics

| Metric | Labels | Meaning |
| --- | --- | --- |
| `balance_alert_balance`, `_threshold`, `_ratio`, `_status` | `project`, `provider`, `type` | Current balance, threshold, balance/threshold, and 1 for healthy or 0 for alert |
| `balance_alert_check_status` | `project`, `provider`, `type` | Last check status; failed checks retain the last successful balance |
| `balance_alert_burn_rate_per_day`, `_runway_days` | `project`, `provider`, `type` | Daily burn rate and estimated days remaining; emitted only with enough history |
| `balance_alert_subscription_days`, `_amount`, `_status` | `name`, `cycle_type` | Days to renewal, amount, and 1 healthy, 0 due, or -1 already renewed |
| `balance_alert_email_mailbox_status` | `mailbox` | Last mailbox scan status |
| `balance_alert_email_last_scan_emails`, `_alerts` | `mailbox` | Email and alert counts from the last scan |
| `balance_alert_email_scan_total`, `_alerts_total` | `mailbox` | Cumulative email and alert counts |
| `balance_alert_job_last_run_timestamp`, `_last_success_timestamp`, `_last_status`, `_last_duration_seconds` | `task` | Last run, last success, status, and duration |
| `balance_alert_job_runs_total` | `task`, `status` | Job run count |
| `balance_alert_notifications_total` | `kind`, `status` | Webhook count; kinds include `balance`, `subscription`, `email`, `mailbox_error`, `runway`, `spend_spike`, and `weekly_report` |
| `balance_alert_last_check_timestamp` | `check_type` | Last balance, subscription, or email check |

When a project, subscription, or mailbox is renamed or deleted, obsolete gauge series are removed on the next update. The job label is `task`; Prometheus may rename it to `exported_job` to avoid its built-in `job` label.

## Dashboard

`docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d` provisions Prometheus, Grafana, the data source, and the `balance-alert` dashboard. The dashboard contains:

- Overview: project totals, healthy and alerting projects, failed checks, renewals due within seven days, and the last balance check.
- Balances: ratio gauges, trends, and a type-filtered detail table.
- Renewals: countdown and status table.
- Email scanning: mailbox totals, failures, latest hits, details, and daily alert counts.
- Jobs and notifications: failed jobs, recent sends and failures, job status, and notification types.

Filters are `project`, `type`, `subscription`, and `mailbox`. Balance units differ between providers, so compare projects using the ratio panels.

To import the dashboard into an existing Grafana instance:

```bash
cd grafana && ./import-dashboard.sh http://localhost:3000 admin <password>
```

The provisioned dashboard is restored from disk after a Compose restart. Export UI changes from Settings → JSON Model and replace the checked-in dashboard file.

## PromQL examples

```promql
balance_alert_balance and on(project, provider, type) balance_alert_status == 0
bottomk(5, balance_alert_ratio)
balance_alert_check_status == 0
bottomk(5, balance_alert_runway_days)
balance_alert_runway_days < 7
balance_alert_burn_rate_per_day > 1.5 * avg_over_time(balance_alert_burn_rate_per_day[7d])
balance_alert_email_mailbox_status == 0
increase(balance_alert_email_alerts_total[7d])
time() - balance_alert_job_last_success_timestamp > 26 * 3600
increase(balance_alert_notifications_total{status="failed"}[1h]) > 0
```

## Self-monitoring rules

Balance Alert sends its own balance alerts through the configured Webhook. These optional rules monitor the monitor:

```yaml
groups:
  - name: balance-alert-self
    rules:
      - alert: BalanceAlertJobFailed
        expr: balance_alert_job_last_status == 0
        for: 10m
        annotations: { summary: "Balance Alert task {{ $labels.task }} failed" }
      - alert: BalanceAlertJobStale
        expr: time() - balance_alert_job_last_success_timestamp{task="alert_check"} > 26 * 3600
        annotations: { summary: "alert_check has not succeeded for 26 hours" }
      - alert: BalanceAlertRunwayShort
        expr: balance_alert_runway_days < 3
        for: 1h
        annotations: { summary: "{{ $labels.project }} has less than three days of runway" }
      - alert: BalanceAlertMailboxDown
        expr: balance_alert_email_mailbox_status == 0
        for: 1h
        annotations: { summary: "Mailbox {{ $labels.mailbox }} is unavailable" }
      - alert: BalanceAlertNotificationFailed
        expr: increase(balance_alert_notifications_total{status="failed"}[1h]) > 0
        annotations: { summary: "Webhook notification failed ({{ $labels.kind }})" }
```
