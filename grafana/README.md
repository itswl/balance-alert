# Grafana Dashboard 使用指南

Dashboard 文件：`dashboards/balance-alert-dashboard.json`（uid `balance-alert`，版本 3）。
`docker-compose --profile monitoring up -d` 会自动装载数据源和面板；也可以用 `import-dashboard.sh` 导入到已有的 Grafana。

指标来自 Web 进程 `:9100/metrics`（`ENABLE_PROMETHEUS=true`）。所有定时任务都在这个进程里跑，所以看板刷新、定时告警检查、
定时邮箱扫描、页面上的「立即扫描」都会反映到面板上；命令行手动跑的 `services.monitor` / `services.email_scanner` 不会。
完整指标列表见项目根目录 README 的「Prometheus 指标」一节。

## 面板布局

```
┌──────────────────────────────────────────────────────────────────────┐
│ 概览：项目总数 │ 正常 │ 告警 │ 检查失败 │ 7天内到期订阅 │ 上次余额检查 │
├─ 余额 ───────────────────────────────────────────────────────────────┤
│ 余额比例仪表盘（余额/阈值）           │ 余额比例趋势                  │
│ 项目余额对比（原始值，按类型筛选）    │ 余额趋势图                    │
│ 项目余额详情表：项目 / 服务商 / 类型 / 余额 / 阈值 / 比例 / 状态 / 检查 │
├─ 订阅续费 ───────────────────────────────────────────────────────────┤
│ 订阅续费倒计时                        │ 订阅状态详情表                │
├─ 邮箱扫描 ───────────────────────────────────────────────────────────┤
│ 邮箱数 │ 连接失败邮箱 │ 上次扫描命中 │ 上次邮箱扫描                    │
│ 邮箱扫描明细（状态 / 上次邮件数 / 上次命中 / 累计命中） │ 每日命中告警邮件 │
├─ 定时任务与通知 ─────────────────────────────────────────────────────┤
│ 失败任务 │ 24h 通知发送 │ 24h 通知失败 │ 上次告警检查成功               │
│ 定时任务状态表（状态 / 上次运行 / 上次成功 / 耗时 / 累计失败）│ 通知发送（按类型） │
└──────────────────────────────────────────────────────────────────────┘
```

## 各区块说明

### 概览

- **监控项目总数 / 正常 / 告警**：按 `balance_alert_status` 统计，项目删除或改名后旧序列会被清掉，不会多算。
- **检查失败项目**：`balance_alert_check_status == 0`，指上次查余额时接口报错或网络失败的项目。失败时余额保留上次成功值，所以「告警」和「检查失败」是两回事。
- **上次余额检查**：`balance_alert_last_check_timestamp{check_type="balance"}`，超过 3 个刷新周期没更新时 `/health` 也会变成 503。

### 余额

不同 provider 的余额单位不同：火山 / 阿里云 / DeepSeek 是人民币，OpenRouter / UniAPI 是 credits，GLM Coding Plan 是剩余配额百分比。
所以**跨项目比较请看比例面板**（余额 ÷ 阈值），原始值面板用顶部「类型」筛选器分开看。

- **余额比例仪表盘**：< 20% 红，20-50% 黄，> 50% 绿；比例低于 100% 就是已经触发告警。
- **项目余额详情表**：类型列显示为「积分 / Credits」「余额」「配额 %」；状态列是阈值判断，检查列是接口是否成功。

### 订阅续费

沿用旧版：倒计时按剩余天数排序（< 3 天红，3-7 天黄），详情表显示周期、金额、状态（正常 / 需续费 / 已续费）。

### 邮箱扫描

- **邮箱数 / 连接失败邮箱**：来自 `balance_alert_email_mailbox_status`，1 正常 0 失败。IMAP 登录不上、授权码过期都会在这里显示出来。
- **上次扫描命中**：`balance_alert_email_last_scan_alerts` 求和，即上次扫描匹配到欠费 / 续费关键词的邮件数。
- **每日命中告警邮件**：`increase(balance_alert_email_alerts_total[1d])`，按邮箱分组。
- 累计类指标是进程启动以来的计数，服务重启后归零。

### 定时任务与通知

三个进程内任务：`dashboard_refresh`（看板刷新）、`alert_check`（真实告警检查，默认每天 09:00 / 15:00）、`email_scan`（邮箱扫描，默认每天 10:00）。

- **上次运行失败的任务**：非 0 时 `/health` 返回 503，`GET /api/jobs` 能看到错误原文。
- **通知发送**：`balance_alert_notifications_total{kind, status}`，kind 为 `balance` / `subscription` / `email` / `mailbox_error`。发送失败一般是 Webhook 地址、网络或限流问题。
- **定时任务状态表**：任务标签名叫 `task`（不叫 `job`，因为 Prometheus 抓取时会把与自带 `job` 标签冲突的项改名成 `exported_job`）。

## 筛选器

| 变量 | 取值来源 | 作用范围 |
| --- | --- | --- |
| `project` | `label_values(balance_alert_balance, project)` | 余额区块 |
| `type` | `label_values(balance_alert_balance, type)` | 余额区块，把不同单位的项目分开看 |
| `subscription` | `label_values(balance_alert_subscription_days, name)` | 订阅区块 |
| `mailbox` | `label_values(balance_alert_email_mailbox_status, mailbox)` | 邮箱区块 |

默认时间范围最近 24 小时，自动刷新 1 分钟。

## PromQL 速查

```promql
# 余额低于阈值的项目及其当前余额
balance_alert_balance and on(project, provider, type) balance_alert_status == 0

# 余额比例最低的 5 个项目
bottomk(5, balance_alert_ratio)

# 上次检查失败的项目
balance_alert_check_status == 0

# 7 天内到期且还没续费的订阅
balance_alert_subscription_days <= 7 and balance_alert_subscription_status == 0

# 连接失败的邮箱
balance_alert_email_mailbox_status == 0

# 最近 7 天每个邮箱命中的告警邮件
increase(balance_alert_email_alerts_total[7d])

# 定时任务超过 26 小时没成功过（alert_check 每天两次，email_scan 每天一次）
time() - balance_alert_job_last_success_timestamp > 26 * 3600

# 最近 1 小时发送失败的通知
increase(balance_alert_notifications_total{status="failed"}[1h]) > 0
```

## 建议的 Prometheus 告警规则（可选）

Balance Alert 自己通过 Webhook 发余额告警，下面这些是给「监控系统本身」用的：

```yaml
groups:
  - name: balance-alert-self
    rules:
      - alert: BalanceAlertJobFailed
        expr: balance_alert_job_last_status == 0
        for: 10m
        labels: { severity: warning }
        annotations: { summary: "balance-alert 任务 {{ $labels.task }} 上次运行失败" }
      - alert: BalanceAlertJobStale
        expr: time() - balance_alert_job_last_success_timestamp{task="alert_check"} > 26 * 3600
        labels: { severity: warning }
        annotations: { summary: "alert_check 超过 26 小时没有成功运行" }
      - alert: BalanceAlertMailboxDown
        expr: balance_alert_email_mailbox_status == 0
        for: 1h
        labels: { severity: warning }
        annotations: { summary: "邮箱 {{ $labels.mailbox }} 连接失败" }
      - alert: BalanceAlertNotificationFailed
        expr: increase(balance_alert_notifications_total{status="failed"}[1h]) > 0
        labels: { severity: warning }
        annotations: { summary: "Webhook 通知发送失败（{{ $labels.kind }}）" }
```

## 导入与更新

```bash
# 导入 / 覆盖到已有 Grafana（需要 Prometheus 数据源名为 Prometheus）
cd grafana && ./import-dashboard.sh http://localhost:3000 admin <password>
```

Compose 方式装载的面板允许在 UI 里改，但重启后会以文件为准；想保留改动请用 Settings → JSON Model 导出后覆盖 `dashboards/balance-alert-dashboard.json`。

## 故障排查

**面板显示 No Data**：确认 `ENABLE_PROMETHEUS=true` 且 `curl http://<host>:9100/metrics` 有 `balance_alert_` 开头的指标；再看 Prometheus → Status → Targets 里 `balance-alert` 是否 UP。

**邮箱区块为空**：只有跑过一次扫描（定时 `email_scan` 或页面「立即扫描」）才有邮箱指标；没有配置邮箱时也为空。

**定时任务区块为空**：任务至少运行过一次才有 `balance_alert_job_*`；`dashboard_refresh` 启动即跑，其它两个到设定时刻才跑。

**数据不更新**：余额指标随 `dashboard_refresh`（默认每小时）和页面刷新更新；检查 `/api/jobs` 里任务是否正常，容器时区（`TZ`）是否符合预期。

---

**Dashboard 版本**: 3.0
**最后更新**: 2026-09-14
