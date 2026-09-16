# Balance Alert

监控多个平台的余额或配额，算出还能用几天，快见底或消耗突然放大时发 Webhook；顺带管订阅续费提醒，扫描邮箱里的欠费、续费邮件，每周推一份消耗汇总。一个 Python 进程里跑 Flask 看板 + API、进程内定时任务和 Prometheus 指标。

默认只开余额检查、Webhook 告警和 Web 看板；数据库、动态配置、订阅、Prometheus 用 `ENABLE_*` 开关按需打开。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env                        # 填 WEB_API_KEY、WEBHOOK_URL 和各平台的 *_API_KEY
python -m services.monitor --show-config    # 自检：每个密钥从哪来、缺什么、时刻怎么理解
python main.py                              # http://localhost:8080
```

**不需要配置文件**：环境变量里有 `DEEPSEEK_API_KEY` 就会自动监控 DeepSeek，阈值取 `DEEPSEEK_THRESHOLD`。
要一次声明很多账户，或者想把清单纳入版本管理，再 `cp config.json.example config.json`。

`.env` 的值后面不要写行内注释，注释单独一行。

## 配置

三层各管一摊，一个值只有一个家。业务清单三种来路都行，按需要挑一种，也可以混用：

| 来源 | 放什么 | 适合 |
| --- | --- | --- |
| 环境变量（`.env` / K8s Secret） | 密钥、Webhook、数据库连接、功能开关、定时任务时刻；**设了 `{PROVIDER}_API_KEY` 就自动成为一个受监控项目** | 一个平台一个账号的常见场景，零配置 |
| `config.json` | 业务清单 `projects` / `subscriptions` / `email`，支持 `${VAR}` 占位符 | 一次声明很多账户、想纳入版本管理 |
| 数据库动态配置 | 同三段清单，可在页面上增删改 | 生产环境，需 `ENABLE_DATABASE` + `ENABLE_DYNAMIC_CONFIG` |

优先级：数据库里某一段有数据就覆盖文件里的同名段落；环境变量自动发现的项目追加在最后，**已经声明过的 provider 不会被重复添加**。

### 环境变量自动发现

| 变量 | 作用 |
| --- | --- |
| `{PROVIDER}_API_KEY` | 有值就监控这个平台，项目名即 provider 名 |
| `{PROVIDER}_THRESHOLD` | 告警阈值，不填则只看不告警（自检会提示） |
| `{PROVIDER}_OWNER_PROJECT` | 分组标签，可选 |

同一平台多个账号用 `{PROVIDER}_1_API_KEY`、`{PROVIDER}_2_API_KEY`，项目名自动变成 `volc-1`、`volc-2`，阈值对应 `VOLC_1_THRESHOLD`。

自动发现的项目在页面上是只读的，点编辑保存一次就会固化进数据库，之后以数据库为准；要移除它得先去掉对应的环境变量。

### projects

一个项目最少两个字段。密钥自动读环境变量 `{PROVIDER}_API_KEY`；同一 provider 多个账号用 `{PROVIDER}_{序号}_API_KEY`，序号按在 `projects` 里的出现顺序：

```json
{ "provider": "openrouter", "threshold": 10000 }
{ "name": "火山-主账号", "provider": "volc", "threshold": 7000, "owner_project": "云服务" }
```

| 字段 | 说明 |
| --- | --- |
| `provider` | 必填，见下表 |
| `threshold` | 低于它告警；不填永不告警，自检会提示 |
| `name` | 默认用 provider 名；动态配置里是唯一键 |
| `type` | 展示用，按 provider 推导：`credits` / `balance` / `quota` |
| `owner_project` / `enabled` | 分组标签 / 是否启用，默认启用 |

| 平台 | `provider` | 密钥格式 |
| --- | --- | --- |
| OpenRouter、UniAPI、微信排名、TikHub、DeepSeek | `openrouter` `uniapi` `wxrank` `tikhub` `deepseek` | 普通 API Key |
| 智谱 GLM Coding Plan | `glm` | `id.secret`。查的是套餐剩余配额百分比，`threshold` 按百分比填，如 `10` |
| 火山引擎 | `volc` | `AccessKeyId:SecretAccessKey` |
| 阿里云 | `aliyun` | `AccessKeyId:AccessKeySecret` |

### subscriptions 与 email

```json
{ "name": "域名续费", "cycle_type": "yearly", "renewal_day": "03-15", "amount": 88 }
{ "host": "imap.example.com", "username": "me@example.com", "password": "${EMAIL_PASSWORD}" }
```

订阅 `cycle_type` 为 `weekly` / `monthly` / `yearly`，年付的 `renewal_day` 直接写 `"03-15"`；`alert_days_before` 默认 3，续费当天也提醒。邮箱的 `port`（993）和 `use_ssl`（true）可省。匹配关键词默认覆盖中英文的欠费、续费、停机用语，要改就在 config.json 顶层加 `email_settings`：`alert_keywords` 整体替换，`extra_alert_keywords` 追加。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `WEB_API_KEY` | 无 | `/api/*` 的访问密钥；未设置时接口一律 503 |
| `WEBHOOK_URL` / `WEBHOOK_TYPE` / `WEBHOOK_SOURCE` | 无 / `custom` / `credit-monitor` | 告警机器人；类型 `feishu` `dingtalk` `wecom` `custom` |
| `{PROVIDER}_API_KEY` | 无 | 各平台密钥，见上表 |
| `CONFIG_PATH` | `config.json` | 配置文件路径 |
| `BALANCE_REFRESH_INTERVAL_SECONDS` | `3600` | 看板刷新间隔 |
| `ALERT_SCHEDULE` | `09:00,15:00` | 真实告警检查时刻，逗号分隔，`off` 关闭 |
| `EMAIL_SCAN_SCHEDULE` / `EMAIL_SCAN_DAYS` | `10:00` / `1` | 定时邮箱扫描时刻、覆盖最近几天（1-30） |
| `WEEKLY_REPORT_SCHEDULE` | `Mon 09:00` | 周报时刻，格式「星期 时刻」，星期可写 `Mon` / `周一` / `1`，`off` 关闭 |
| `BURN_RATE_WINDOW_DAYS` | `7` | 算日均消耗看最近几天 |
| `RUNWAY_ALERT_DAYS` | `7` | 按当前速率还剩几天就告警，`0` 关闭 |
| `SPEND_SPIKE_RATIO` / `SPEND_SPIKE_MIN_AMOUNT` | `3` / `1` | 今日消耗达日常中位数的几倍算突增、低于多少绝对值不报，比例设 `0` 关闭 |
| `ENABLE_WEB_ALARM` | `false` | 看板刷新和页面操作是否也发真实告警 |
| `ALERT_COOLDOWN_SECONDS` / `SUBSCRIPTION_ALERT_COOLDOWN_SECONDS` | `86400` | 同一告警的冷却时长，需数据库 |
| `MAX_CONCURRENT_CHECKS` / `RESPONSE_CACHE_TTL` | `20` / `300` | 并发检查数（1-50）、余额结果缓存秒数 |
| `ENABLE_DATABASE` / `DATABASE_URL` | `false` / `sqlite:///./data/balance_alert.db` | 历史记录与动态配置的前提；启动自动建表，支持 PostgreSQL、MySQL |
| `ENABLE_DYNAMIC_CONFIG` | `false` | 业务清单改从数据库读 |
| `ENABLE_HISTORY_API` | `false` | 历史数据接口、趋势图、历史告警邮件 |
| `ENABLE_SUBSCRIPTIONS` | `false` | 订阅提醒 |
| `CONFIG_ENCRYPTION_KEY` | 无 | 设置后数据库里的 `api_key` 和邮箱密码加密存储（`enc:v1:` 前缀），接受 Fernet key 或任意口令；`AUTO_ENCRYPT_ON_READ`（默认 true）把读到的旧明文回写成密文 |
| `ENABLE_PROMETHEUS` / `METRICS_PORT` | `false` / `9100` | 指标端口 |
| `WEB_PORT` / `WEB_ENABLE_CORS` / `CORS_ORIGINS` | `8080` / `false` / 无 | Web 服务 |
| `LOG_LEVEL` / `LOG_FORMAT` / `LOG_FILE` | `INFO` / `text` / 无 | 日志；格式可选 `json` |
| `STRICT_DATABASE_ERRORS` | `false` | 数据库异常向上抛，排障时用 |

值写错（如 `ENABLE_DATABASE=enabled`）启动即报错；留空视为未设置。已有 `config.json` 要导入数据库：`python scripts/migrate_config_to_db.py`。

## 定时任务

都在 Web 进程内调度（`core/scheduler.py`），容器里没有 cron，时刻按容器 `TZ`：

| 任务 | 触发 | 发告警 |
| --- | --- | --- |
| `dashboard_refresh` | 启动即跑，之后每 `BALANCE_REFRESH_INTERVAL_SECONDS` 刷新看板 | 仅 `ENABLE_WEB_ALARM=true` 时 |
| `alert_check` | 每天 `ALERT_SCHEDULE`，检查余额与订阅 | 是 |
| `email_scan` | 每天 `EMAIL_SCAN_SCHEDULE`，扫最近 `EMAIL_SCAN_DAYS` 天的邮件 | 是 |
| `weekly_report` | 每周 `WEEKLY_REPORT_SCHEDULE`，汇总一周消耗、跑道与待续费 | 是 |

任一任务上次失败，`/health` 返回 503 并在 `failed_jobs` 列出，`GET /api/jobs` 看详情。手动跑一次：`python -m services.monitor --dry-run`、`python -m services.email_scanner --days 1`。

## 消耗与跑道

余额历史是一串快照，相邻两点余额下降就是消耗，上升就是充值。据此算出**日均消耗**和**跑道**（按当前速率还能用几天），比静态阈值更早也更准：同样是 430 元，日烧 5 元和日烧 200 元完全是两回事。

在此之上有两类告警，都需要 `ENABLE_DATABASE=true` 攒历史，数据不足时自动沉默，退回纯阈值告警：

- **跑道见底**：预计剩余天数低于 `RUNWAY_ALERT_DAYS` 时提醒，附上预计耗尽日期。已经在报余额不足的账户不重复打扰。
- **消耗突增**：今日消耗达到近 `BURN_RATE_WINDOW_DAYS` 天中位数的 `SPEND_SPIKE_RATIO` 倍时提醒。key 泄露、任务跑飞通常先表现为这个。

估算至少需要 4 个数据点、跨度 6 小时；跨度不足一天的结果标为低置信度，不用于告警。看板上每张卡片显示「还可用 N 天」，概览显示全部账户里最先见底的那个。每周的 `weekly_report` 会把本周消耗、跑道排名、未来 30 天的订阅支出汇成一张卡片推出去。

## 看板与 API

看板四个视图：全部项目、仅告警、订阅管理、邮箱扫描；地址栏加 `#alerts` `#subscriptions` `#email` 可直达。首次打开填 `WEB_API_KEY`。开了动态配置能在页面上增删改项目、订阅和邮箱，`config.json` 就完全不用碰了；开了历史 API 有趋势图和历史告警邮件。接口清单见 [docs/API.md](docs/API.md)。

## 部署

**Docker**：镜像不锁架构，arm64 与 amd64 都能构建；基础镜像和 pip 源是 build-arg。

```bash
docker build -t balance-alert .
docker build --build-arg BASE_IMAGE=<国内镜像>/python:3.11-slim \
             --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple -t balance-alert .
docker buildx build --platform linux/amd64,linux/arm64 -t <registry>/balance-alert --push .
docker-compose up -d                         # 核心版
docker-compose --profile monitoring up -d    # 带 Prometheus + Grafana
```

**Kubernetes**：`k8s/common-prod.yaml` 含 Deployment、Service、Ingress，apply 前替换 `YOUR_REGISTRY` 与 `YOUR_DOMAIN`。

```bash
kubectl create secret generic balance-alert-secret --from-env-file=.env -n common-prod --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f k8s/common-prod.yaml
kubectl -n common-prod rollout status deploy/balance-alert
```

探针约定：`/live` 给 startup 与 liveness，只证明进程活着；`/health` 给 readiness，没数据、数据过期或任务失败时 503。改了 Secret 要 `kubectl rollout restart`。

## 监控

`ENABLE_PROMETHEUS=true` 后 `:9100/metrics` 暴露余额、订阅、邮箱扫描、定时任务、通知发送五组指标。指标含义、Grafana 面板和建议的自监控告警规则见 [grafana/README.md](grafana/README.md)。

## 排障

- **接口 503「API Key 未配置」**：进程没读到 `WEB_API_KEY`，检查 `.env` 或 Secret 后重启。
- **`/health` 503**：看返回体。`has_data=false` 是没有有效项目，`is_stale=true` 是刷新卡住，`failed_jobs` 非空去 `GET /api/jobs` 看错误原文。
- **startup probe 打到 `/health` 反复重启**：启动探针应指向 `/live`。
- **数据库里的密钥没加密**：确认进程有 `CONFIG_ENCRYPTION_KEY`；旧明文会在下一次读取时回写为密文。
- **不确定配置到底生效了什么**：`python -m services.monitor --show-config`。

## 项目结构

```text
main.py                 入口：Flask + 进程内调度器 + 指标
core/                   settings（环境变量）、config_loader（三层配置）、scheduler、timeutil、state_manager、secret_crypto
providers/              各平台余额适配器；base.py 的 ProviderSpec 用几行声明就能接一个新平台
services/               monitor（余额检查）、runway（消耗与跑道）、weekly_report、subscription_checker、email_scanner、webhook_adapter、prometheus_exporter
web/                    Flask 应用与蓝图（core / subscription / email / project / history）、请求校验
static/ templates/      看板前端，原生 JS
database/               SQLAlchemy 模型与仓库，启动自动建表
grafana/ prometheus.yml 监控面板与抓取配置
k8s/                    生产部署清单
tests/                  pytest
```
