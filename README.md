# Balance Alert

Balance Alert 是一个余额监控和告警工具：定时检查多个平台的余额或 credits，低于阈值时发送 Webhook 告警，并提供 Web 看板查看当前状态。

这份 README 重点说明怎么配置。项目默认只启用核心能力：

- 余额检查
- Webhook 告警
- Web 看板

数据库历史、数据库动态配置、订阅提醒、邮箱扫描、Prometheus/Grafana 都是可选能力，需要通过环境变量显式打开。

## 配置总览

**一个值只有一个家**，三层配置各管一摊、互不重叠：

| 来源 | 只放 | 适合场景 |
| --- | --- | --- |
| `.env` / Kubernetes Secret（环境变量） | 密钥、Webhook、数据库连接、功能开关、调度参数 —— 全部见下方「环境变量」表 | 所有部署 |
| `config.json` | 仅业务清单：`projects` / `subscriptions` / `email` | 本地运行、简单部署 |
| 数据库动态配置 | 同上三类业务清单 | 生产环境，Web UI 维护 |

加载规则：

1. 默认读取 `CONFIG_PATH` 指定的配置文件，未设置时读取 `config.json`。
2. 配置文件里的 `${VAR}` 会被同名环境变量替换，适合把密钥留在 `.env` 或 Secret。
3. 当 `ENABLE_DATABASE=true` 且 `ENABLE_DYNAMIC_CONFIG=true` 时，如果数据库里有对应数据，数据库中的 `projects` / `subscriptions` / `email` 会覆盖配置文件中的同名段落。

排障时用这个命令查看脱敏后的最终生效配置和每段来源：

```bash
python -m services.monitor --show-config
```

推荐原则：

- Provider 密钥放 `.env`（变量名 `{PROVIDER}_API_KEY`，`config.json` 里不用写 `api_key`）；生产可改用数据库动态配置，配上 `CONFIG_ENCRYPTION_KEY` 后加密存储。不要把真实密钥明文写进 `config.json`。
- Web 登录密钥使用 `WEB_API_KEY`，不要复用云厂商或 Provider 的业务 API Key。

## 快速开始

安装依赖并准备配置：

```bash
pip install -r requirements.txt
cp config.json.example config.json
cp .env.example .env
```

编辑 `.env`，至少填这些值：

```bash
WEB_API_KEY=change-this-login-key
WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN
WEBHOOK_TYPE=feishu
WEBHOOK_SOURCE=balance-alert

OPENROUTER_API_KEY=sk-or-v1-xxx
ALIYUN_1_API_KEY=ACCESS_KEY_ID:ACCESS_KEY_SECRET
VOLC_1_API_KEY=ACCESS_KEY_ID:SECRET_KEY
```

注意：`.env` 的值后面不要写行内注释。下面这种写法会把注释也当成值的一部分：

```bash
WEB_API_KEY=change-me  # 不推荐
```

应写成：

```bash
# Web/API 访问密钥
WEB_API_KEY=change-me
```

启动 Web 看板：

```bash
python main.py
```

访问：

```text
http://localhost:8080
```

执行一次余额检查：

```bash
python -m services.monitor --dry-run
```

## 配置文件

`config.json` 只负责业务列表（`projects` 为主），顶层结构如下：

```json
{
  "email": [],
  "subscriptions": [],
  "projects": []
}
```

Webhook、刷新间隔、并发数、各类开关等**只由环境变量配置**（见下方「环境变量」）。
文件里的 `settings` / `webhook` 块已不再生效，请迁移到环境变量。

`projects` 是余额监控的核心配置。**一个项目最少只要两个字段**——密钥自动从环境变量读，不用写占位符：

```json
{ "provider": "openrouter", "threshold": 10000 }
```

配合 `.env` 里的 `OPENROUTER_API_KEY=sk-or-v1-xxx` 即可工作。需要自定义时再补字段：

```json
{
  "name": "火山-主账号",
  "owner_project": "云服务",
  "provider": "volc",
  "threshold": 7000
}
```

字段说明：

| 字段 | 必填 | 省略时 |
| --- | --- | --- |
| `provider` | 是 | — 见下方 provider 表 |
| `threshold` | 建议 | 不填则永不告警（自检会提示） |
| `api_key` | 否 | 自动读 `{PROVIDER}_API_KEY` 环境变量；同 provider 多账号读 `{PROVIDER}_{序号}_API_KEY`（序号按在 `projects` 里的出现顺序） |
| `name` | 否 | 用 provider 名；数据库动态配置中作为唯一键 |
| `type` | 否 | 按 provider 推导（`openrouter`/`uniapi`/`wxrank` → `credits`，`glm` → `quota`，其余 → `balance`） |
| `owner_project` | 否 | 不分组 |
| `enabled` | 否 | 视为启用 |

`subscriptions` 的年付续费日可以直接写日期，不用记 MMDD 数字：

```json
{ "name": "域名续费", "cycle_type": "yearly", "renewal_day": "03-15", "amount": 88 }
```

`alert_days_before`（默认 3）表示提前几天开始提醒，**续费当天也会提醒**。

`email` 的 `port`（993）和 `use_ssl`（true）可省略，只要 `host` / `username` / `password`。匹配关键词默认覆盖中英文的欠费 / 续费 / 停机类用语，要调整时在 config.json 顶层加 `email_settings`：`alert_keywords` 整体替换，`extra_alert_keywords` 在默认之上追加。

Web 看板里有「邮箱扫描」页：看已配置的邮箱、选时间范围点「立即扫描」、查看本次命中的欠费 / 续费类邮件。开了 `ENABLE_DYNAMIC_CONFIG` 可以直接在页面上增删改邮箱；开了 `ENABLE_HISTORY_API` 还能看数据库里的历史告警邮件。页面触发的扫描是否真发通知和余额刷新一样，由 `ENABLE_WEB_ALARM` 决定；定时扫描由进程内的 `email_scan` 任务在 `EMAIL_SCAN_SCHEDULE` 时刻执行并发送真实通知。

**配完跑一下自检**，它会告诉你每个密钥取自哪个环境变量、缺了什么、日期被理解成哪天：

```bash
python -m services.monitor --show-config
```

```text
项目 (3)
  ✓ OpenRouter [openrouter/credits] 阈值 10000 — Key 来自 环境变量 OPENROUTER_API_KEY
  ✗ 火山-备用 [volc]: 缺少 API Key，请设置 VOLC_2_API_KEY
  ! 忘填阈值 [tikhub/balance] 阈值 None — Key 来自 环境变量 TIKHUB_API_KEY（阈值为 None，不会触发告警）

订阅 (1)
  ✓ 域名续费: 每年 3月15日，提前 3 天提醒，金额 88
```

有问题时退出码非零，可用于部署前校验。

支持的 Provider：

| 平台 | `provider` | `api_key` 格式 |
| --- | --- | --- |
| OpenRouter | `openrouter` | 普通 API Key |
| UniAPI | `uniapi` | 普通 API Key |
| 微信排名 | `wxrank` | 普通 API Key |
| TikHub | `tikhub` | 普通 API Key |
| DeepSeek | `deepseek` | 普通 API Key |
| 智谱 GLM Coding Plan | `glm` | 普通 API Key（`id.secret` 形式） |
| 火山引擎 | `volc` | `AccessKeyId:SecretAccessKey` |
| 阿里云 | `aliyun` | `AccessKeyId:AccessKeySecret` |

`glm` 查的不是充值余额（智谱没有公开的余额接口），而是 Coding Plan 套餐的剩余配额：接口按 5 小时 / 周 / 月等窗口给出若干条限额，取剩余比例最低的那个窗口，值是百分比（100 = 未使用，0 = 用光）。所以它的 `threshold` 也按百分比填，例如 `10` 表示剩余不足 10% 时告警。

## 环境变量

### 必填或常用

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WEB_API_KEY` | 无 | `/api/*` 接口认证密钥，前端通过 `X-API-Key` 发送 |
| `WEBHOOK_URL` | 无 | 告警机器人地址 |
| `WEBHOOK_TYPE` | `custom` | `feishu` / `dingtalk` / `wecom` / `custom` |
| `WEBHOOK_SOURCE` | `credit-monitor` | 告警来源标识 |
| `CONFIG_PATH` | `config.json` | 配置文件路径 |
| `BALANCE_REFRESH_INTERVAL_SECONDS` | `3600` | 看板刷新间隔（`dashboard_refresh` 任务，默认只查不发告警） |
| `ALERT_SCHEDULE` | `09:00,15:00` | 真实告警检查时刻（`alert_check` 任务），按进程时区，逗号分隔，`off` 关闭 |
| `EMAIL_SCAN_SCHEDULE` | `10:00` | 定时邮箱扫描时刻（`email_scan` 任务），`off` 关闭 |
| `EMAIL_SCAN_DAYS` | `1` | 定时邮箱扫描覆盖最近几天（1-30） |
| `MAX_CONCURRENT_CHECKS` | `20` | 并发检查数，钳制在 1-50 |
| `ALERT_COOLDOWN_SECONDS` | `86400` | 同一项目告警冷却时间 |
| `RESPONSE_CACHE_TTL` | `300` | 余额结果缓存秒数，防止手动刷新打爆上游 |

### Web 和 API

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WEB_PORT` | `8080` | Web 服务端口 |
| `WEB_ENABLE_CORS` | `false` | 是否启用 CORS |
| `CORS_ORIGINS` | 无 | CORS 白名单，逗号分隔；开启 CORS 时建议必填 |

注意：环境变量的值写错（如 `ENABLE_DATABASE=enabled`）会在启动时直接报错，便于及早发现配置问题；留空（`KEY=`）视为未设置。

### 数据库和动态配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ENABLE_DATABASE` | `false` | 启用数据库，用于历史记录和动态配置 |
| `DATABASE_URL` | `sqlite:///./data/balance_alert.db` | SQLAlchemy 数据库连接 |
| `ENABLE_DYNAMIC_CONFIG` | `false` | 从数据库读取 `projects` / `subscriptions` / `email` |
| `ENABLE_HISTORY_API` | `false` | 启用历史数据 API |
| `CONFIG_ENCRYPTION_KEY` | 无 | 加密数据库中的 `api_key` 和邮箱 `password` |
| `AUTO_ENCRYPT_ON_READ` | `true` | 读取明文数据库配置时自动回写为密文 |
| `STRICT_DATABASE_ERRORS` | `false` | 数据库异常是否向上抛出，排障时可打开 |

### 可选能力

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ENABLE_WEB_ALARM` | `false` | Web 后台刷新是否发送真实告警；默认只查询 |
| `ENABLE_SUBSCRIPTIONS` | `false` | 启用订阅提醒和订阅 API |
| `SUBSCRIPTION_ALERT_COOLDOWN_SECONDS` | `ALERT_COOLDOWN_SECONDS` | 订阅提醒冷却时间 |
| `ENABLE_PROMETHEUS` | `false` | 启动 Prometheus metrics 服务 |
| `METRICS_PORT` | `9100` | metrics 端口 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `LOG_FORMAT` | `text` | `text` 或 JSON 风格日志 |
| `LOG_FILE` | 无 | 输出到指定日志文件 |

## 数据库动态配置

适合生产环境或希望通过 Web UI 修改项目配置的场景。

1. 设置数据库环境变量：

```bash
ENABLE_DATABASE=true
ENABLE_DYNAMIC_CONFIG=true
DATABASE_URL=postgresql://user:password@host:5432/balance_alert
```

2. 启动服务。`ENABLE_DATABASE=true` 时应用启动会自动创建缺失的表，无需手动迁移。

3. 在 Web UI 或接口中维护项目配置。数据库里有项目时，应用会优先使用数据库项目；数据库为空时继续使用 `config.json`。已有 `config.json` 的项目可用 `python scripts/migrate_config_to_db.py` 一次性导入数据库。

### 敏感字段加密

数据库动态配置中的 `project_config.api_key` 和 `email_config.password` 支持应用层加密。启用方式：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

把输出写入 `.env` 或 Kubernetes Secret：

```bash
CONFIG_ENCRYPTION_KEY=生成出来的密钥
```

行为说明：

- 未设置 `CONFIG_ENCRYPTION_KEY` 时，数据库会保存明文。
- 新增或更新项目配置时，应用会写入 `enc:v1:...` 格式密文。
- 已有明文配置在 `AUTO_ENCRYPT_ON_READ=true` 时，会在应用通过配置仓库读取后自动回写为密文。
- 如果已经有密文，但运行时没有同一个 `CONFIG_ENCRYPTION_KEY`，应用无法解密，余额检查会失败。

## Kubernetes 生产配置

仓库内提供了生产示例：

- `k8s/common-prod.yaml`：Deployment、Service、Ingress
- `k8s/common-prod-secret.yaml`：本地生成的 Secret manifest，已被 `.gitignore` 忽略，不应提交

生成 Secret：

```bash
kubectl create secret generic balance-alert-secret \
  --from-env-file=.env \
  -n common-prod \
  --dry-run=client -o yaml > k8s/common-prod-secret.yaml
```

如果希望 Secret YAML 保留明文字段，使用 `stringData`。Kubernetes apply 后会自动转成 `data`。

应用顺序：

```bash
kubectl apply -f k8s/common-prod-secret.yaml
kubectl apply -f k8s/common-prod.yaml
kubectl -n common-prod rollout status deploy/balance-alert
```

表结构由应用启动时自动创建（`ENABLE_DATABASE=true`），无需手动迁移。

生产健康检查约定：

| Endpoint | 用途 | 特点 |
| --- | --- | --- |
| `/live` | `startupProbe` / `livenessProbe` | 只证明进程能响应，不依赖项目数据 |
| `/health` | `readinessProbe` | 会检查是否有数据、数据是否过期、定时任务上次是否成功（`jobs_healthy` / `failed_jobs`） |

如果没有有效项目配置，`/health` 会返回 `503 degraded`，Pod 会不 Ready，但不应该被 startup probe 反复重启。

## Docker

本地 Docker Compose：

```bash
docker-compose up -d
```

启用 Prometheus/Grafana：

```bash
docker-compose --profile monitoring up -d
```

只跑核心版时不需要数据库，也不需要 monitoring profile。

## 定时任务

所有定时工作都在 Web 进程内由 `core/scheduler.py` 调度，容器里不再有 cron。三个任务：

| 任务 | 触发 | 做什么 | 发告警？ |
| --- | --- | --- | --- |
| `dashboard_refresh` | 启动即跑，之后每 `BALANCE_REFRESH_INTERVAL_SECONDS` | 刷新看板的余额与订阅状态 | 默认不发，`ENABLE_WEB_ALARM=true` 才发 |
| `alert_check` | 每天 `ALERT_SCHEDULE`（默认 09:00 / 15:00） | 余额 + 订阅检查 | 发 |
| `email_scan` | 每天 `EMAIL_SCAN_SCHEDULE`（默认 10:00），最近 `EMAIL_SCAN_DAYS` 天 | 扫描邮箱里的欠费 / 续费邮件 | 发 |

时刻按进程本地时区，容器里由 `TZ` 决定。任何一个任务上次运行失败，`/health` 会返回 503 并在 `failed_jobs` 里列出来；`GET /api/jobs` 能看到每个任务的计划、上次运行、耗时和错误。`python -m services.monitor` / `python -m services.email_scanner` 仍可用于手动执行一次。

## Prometheus 指标

`ENABLE_PROMETHEUS=true` 后在 `METRICS_PORT`（默认 9100）暴露 `/metrics`。所有任务都在同一个进程里跑，所以看板刷新、定时告警、页面「立即扫描」的结果都会进指标；命令行手动执行的结果不会。

| 指标 | 标签 | 含义 |
| --- | --- | --- |
| `balance_alert_balance` / `_threshold` / `_ratio` / `_status` | `project` `provider` `type` | 当前余额、阈值、余额/阈值、1 正常 0 告警 |
| `balance_alert_check_status` | `project` `provider` `type` | 上次检查 1 成功 0 失败；失败时余额保留上次成功值 |
| `balance_alert_subscription_days` / `_amount` / `_status` | `name` `cycle_type` | 距续费天数、金额、1 正常 0 需续费 -1 本周期已续费 |
| `balance_alert_email_mailbox_status` | `mailbox` | 上次扫描 1 连接正常 0 失败 |
| `balance_alert_email_last_scan_emails` / `_alerts` | `mailbox` | 上次扫描的邮件数 / 命中告警数 |
| `balance_alert_email_scan_total` / `balance_alert_email_alerts_total` | `mailbox` | 累计扫描邮件数 / 累计命中数 |
| `balance_alert_job_last_run_timestamp` / `_last_success_timestamp` / `_last_status` / `_last_duration_seconds` | `task` | 定时任务上次运行时间、上次成功时间、1 成功 0 失败、耗时（标签叫 `task`，避免和 Prometheus 自带的 `job` 冲突） |
| `balance_alert_job_runs_total` | `task` `status` | 任务运行次数 |
| `balance_alert_notifications_total` | `kind` `status` | Webhook 通知次数，kind 为 balance / subscription / email / mailbox_error |
| `balance_alert_last_check_timestamp` | `check_type` | balance / subscription / email 最近一次更新时间 |

项目、订阅、邮箱被删除或改名后，旧的标签序列会在下一次更新时清掉。Grafana 面板见 `grafana/README.md`。

## 常用验证命令

本地：

```bash
python -m services.monitor --dry-run
curl http://localhost:8080/live
curl -H "X-API-Key: $WEB_API_KEY" http://localhost:8080/api/features
```

Kubernetes：

```bash
kubectl -n common-prod get pods -l app=balance-alert
kubectl -n common-prod logs deploy/balance-alert --tail=100
kubectl -n common-prod exec deploy/balance-alert -- curl -s http://127.0.0.1:8080/live
kubectl -n common-prod exec deploy/balance-alert -- curl -s http://127.0.0.1:8080/health
kubectl -n common-prod get events --sort-by=.lastTimestamp | tail -30
```

## 常见问题

### API Key 未配置，请设置 WEB_API_KEY

服务端没有读到 `WEB_API_KEY`。检查 `.env`、Kubernetes Secret 和 Deployment 是否已经重启。

Kubernetes 中建议显式引用：

```yaml
- name: WEB_API_KEY
  valueFrom:
    secretKeyRef:
      name: balance-alert-secret
      key: WEB_API_KEY
      optional: false
```

### `/health` 返回 `503 degraded`

常见原因：

- 没有有效项目配置，`has_data=false`
- 数据库动态配置没打开，`ENABLE_DYNAMIC_CONFIG=false`
- 数据库项目读取失败
- 某个定时任务上次运行失败，`failed_jobs` 里有名字（详情看 `GET /api/jobs`）

先看：

```bash
kubectl -n common-prod exec deploy/balance-alert -- curl -s http://127.0.0.1:8080/health
kubectl -n common-prod logs deploy/balance-alert --tail=200
```

### startup probe failed: HTTP probe failed with statuscode: 503

说明 startup probe 打到了 `/health`。启动探针应该使用 `/live`，因为启动阶段不能依赖余额数据是否已经初始化。

### 数据库里的 `api_key` 没有加密

确认运行中的 Pod 或进程有 `CONFIG_ENCRYPTION_KEY`：

```bash
kubectl -n common-prod exec deploy/balance-alert -- printenv CONFIG_ENCRYPTION_KEY
```

如果变量存在但旧数据仍是明文，触发一次通过配置仓库的读取，例如刷新 Web 数据或调用项目配置 API。自动回写依赖 `AUTO_ENCRYPT_ON_READ=true`。

## 项目结构

```text
providers/             平台余额适配器
services/monitor.py    核心检查和告警流程
services/webhook_adapter.py
services/subscription_checker.py
services/email_scanner.py
core/                  配置、日志、状态管理、密钥加密、进程内定时任务（scheduler.py）
web/                   Flask Web 看板和 API
static/ templates/     前端页面
database/              可选历史库和动态配置（启动时自动建表）
k8s/                   Kubernetes 部署清单（common-prod.yaml）
grafana/               可选监控面板
```
