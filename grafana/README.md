# 监控：Prometheus 指标与 Grafana 面板

`ENABLE_PROMETHEUS=true` 后进程在 `METRICS_PORT`（默认 9100）暴露 `/metrics`。所有定时任务、页面刷新和立即扫描都在这一个进程里，指标是完整的；命令行手动跑的结果不进指标。

## 指标

| 指标 | 标签 | 含义 |
| --- | --- | --- |
| `balance_alert_balance` / `_threshold` / `_ratio` / `_status` | `project` `provider` `type` | 当前余额、阈值、余额 ÷ 阈值、1 正常 0 告警 |
| `balance_alert_check_status` | `project` `provider` `type` | 上次检查 1 成功 0 失败；失败时余额保留上次成功值 |
| `balance_alert_burn_rate_per_day` / `_runway_days` | `project` `provider` `type` | 日均消耗、按此速率还能用几天；需数据库历史，没攒够就没有这两个序列 |
| `balance_alert_subscription_days` / `_amount` / `_status` | `name` `cycle_type` | 距续费天数、金额、1 正常 0 需续费 -1 本周期已续费 |
| `balance_alert_email_mailbox_status` | `mailbox` | 上次扫描 1 连接正常 0 失败 |
| `balance_alert_email_last_scan_emails` / `_alerts` | `mailbox` | 上次扫描的邮件数、命中告警数 |
| `balance_alert_email_scan_total` / `balance_alert_email_alerts_total` | `mailbox` | 累计扫描邮件数、累计命中数 |
| `balance_alert_job_last_run_timestamp` / `_last_success_timestamp` / `_last_status` / `_last_duration_seconds` | `task` | 定时任务上次运行、上次成功、1 成功 0 失败、耗时 |
| `balance_alert_job_runs_total` | `task` `status` | 任务运行次数 |
| `balance_alert_notifications_total` | `kind` `status` | Webhook 通知次数；kind 为 `balance` `subscription` `email` `mailbox_error` `runway` `spend_spike` `weekly_report` |
| `balance_alert_last_check_timestamp` | `check_type` | `balance` / `subscription` / `email` 最近一次更新时间 |

项目、订阅、邮箱删除或改名后，旧序列在下一次更新时清掉。任务标签叫 `task` 而不是 `job`：Prometheus 抓取时会把与自带 `job` 冲突的标签改名成 `exported_job`。

## 面板

`docker-compose --profile monitoring up -d` 自动装载数据源与 `dashboards/balance-alert-dashboard.json`（uid `balance-alert`）。五个区块：

- **概览**：项目总数、正常、告警、检查失败、7 天内到期订阅、上次余额检查。
- **余额**：余额比例仪表盘与趋势（跨币种可比），原始余额按「类型」筛选，详情表带状态与检查两列。
- **订阅续费**：倒计时与状态表。
- **邮箱扫描**：邮箱数、连接失败、上次命中、明细表、每日命中柱状图。
- **定时任务与通知**：失败任务、24 小时通知发送与失败、任务状态表、按类型的通知柱状图。

筛选器：`project` `type` `subscription` `mailbox`。不同 provider 的余额单位不同（人民币、credits、配额百分比），跨项目比较看比例面板。

导入到已有 Grafana（需要 jq，数据源名为 `Prometheus`）：

```bash
cd grafana && ./import-dashboard.sh http://localhost:3000 admin <password>
```

Compose 装载的面板重启后以文件为准，UI 里的改动请从 Settings → JSON Model 导出后覆盖文件。

## 常用查询

```promql
balance_alert_balance and on(project, provider, type) balance_alert_status == 0   # 低于阈值的项目及余额
bottomk(5, balance_alert_ratio)                                                  # 余额比例最低的 5 个
balance_alert_check_status == 0                                                  # 上次检查失败的项目
bottomk(5, balance_alert_runway_days)                                            # 最先见底的 5 个账户
balance_alert_runway_days < 7                                                    # 跑道不足一周
balance_alert_burn_rate_per_day > 1.5 * avg_over_time(balance_alert_burn_rate_per_day[7d])  # 消耗在抬头
balance_alert_email_mailbox_status == 0                                          # 连接失败的邮箱
increase(balance_alert_email_alerts_total[7d])                                   # 最近 7 天每个邮箱命中数
time() - balance_alert_job_last_success_timestamp > 26 * 3600                    # 超过 26 小时没成功的任务
increase(balance_alert_notifications_total{status="failed"}[1h]) > 0             # 最近 1 小时发送失败的通知
```

## 自监控告警（可选）

Balance Alert 自己通过 Webhook 发余额告警，下面这些用来监控它本身：

```yaml
groups:
  - name: balance-alert-self
    rules:
      - alert: BalanceAlertJobFailed
        expr: balance_alert_job_last_status == 0
        for: 10m
        annotations: { summary: "balance-alert 任务 {{ $labels.task }} 上次运行失败" }
      - alert: BalanceAlertJobStale
        expr: time() - balance_alert_job_last_success_timestamp{task="alert_check"} > 26 * 3600
        annotations: { summary: "alert_check 超过 26 小时没有成功运行" }
      - alert: BalanceAlertRunwayShort
        expr: balance_alert_runway_days < 3
        for: 1h
        annotations: { summary: "{{ $labels.project }} 按当前消耗速率不到 3 天就会见底" }
      - alert: BalanceAlertMailboxDown
        expr: balance_alert_email_mailbox_status == 0
        for: 1h
        annotations: { summary: "邮箱 {{ $labels.mailbox }} 连接失败" }
      - alert: BalanceAlertNotificationFailed
        expr: increase(balance_alert_notifications_total{status="failed"}[1h]) > 0
        annotations: { summary: "Webhook 通知发送失败（{{ $labels.kind }}）" }
```

## 排障

- 面板 No Data：确认 `ENABLE_PROMETHEUS=true`，`curl http://<host>:9100/metrics` 能看到 `balance_alert_` 指标，Prometheus 的 Targets 里 `balance-alert` 是 UP。
- 邮箱、任务区块为空：至少跑过一次扫描或任务才有对应指标；`dashboard_refresh` 启动即跑，其它两个到设定时刻才跑。
