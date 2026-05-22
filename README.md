# Balance Alert

Balance Alert 是一个余额监控和告警工具：定时检查多个平台的余额或 credits，低于阈值时发送 Webhook 告警，并提供 Web 看板查看当前状态。

这份 README 重点说明怎么配置。项目默认只启用核心能力：

- 余额检查
- Webhook 告警
- Web 看板

数据库历史、数据库动态配置、订阅提醒、邮箱扫描、Prometheus/Grafana 都是可选能力，需要通过环境变量显式打开。

## 配置总览

应用有三类配置来源：

| 来源 | 放什么 | 适合场景 |
| --- | --- | --- |
| `config.json` | 项目列表、provider、阈值、Webhook 结构化配置 | 本地运行、简单部署、配置随文件发布 |
| `.env` / Kubernetes Secret | API Key、Webhook URL、数据库连接、功能开关 | 敏感信息、环境差异、生产部署 |
| 数据库动态配置 | `projects` / `subscriptions` / `email` 三类配置 | Web UI 维护配置、生产动态更新 |

配置加载规则：

1. 默认读取 `CONFIG_PATH` 指定的配置文件，未设置时读取 `config.json`。
2. 配置文件里的 `${VAR}` 会被同名环境变量替换，适合把密钥留在 `.env` 或 Secret。
3. `BALANCE_REFRESH_INTERVAL_SECONDS`、`MAX_CONCURRENT_CHECKS` 等环境变量会覆盖 `settings` 中的同名设置。
4. 当 `ENABLE_DATABASE=true` 且 `ENABLE_DYNAMIC_CONFIG=true` 时，如果数据库里有对应数据，数据库中的 `projects` / `subscriptions` / `email` 会覆盖配置文件中的同名段落。

推荐原则：

- 不要把真实密钥写进 `config.json`，使用 `${OPENROUTER_API_KEY}` 这类占位符。
- Web 登录密钥使用 `WEB_API_KEY`，不要复用云厂商或 Provider 的业务 API Key。
- 生产环境如果使用数据库动态配置，建议同时设置 `CONFIG_ENCRYPTION_KEY`。

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
python services/monitor.py --dry-run
```

## 配置文件

`config.json` 的顶层结构如下：

```json
{
  "settings": {
    "balance_refresh_interval_seconds": 3600,
    "max_concurrent_checks": 5
  },
  "webhook": {
    "url": "${WEBHOOK_URL}",
    "source": "${WEBHOOK_SOURCE}",
    "type": "${WEBHOOK_TYPE}"
  },
  "email": [],
  "subscriptions": [],
  "projects": []
}
```

`projects` 是余额监控的核心配置。单个项目示例：

```json
{
  "name": "OpenRouter",
  "owner_project": "AI 平台",
  "provider": "openrouter",
  "api_key": "${OPENROUTER_API_KEY}",
  "threshold": 10000,
  "type": "credits",
  "enabled": true
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 项目显示名称，数据库动态配置中也作为唯一名称 |
| `owner_project` | 否 | 归属项目或业务线，用于分组展示 |
| `provider` | 是 | 平台类型，见下方 provider 表 |
| `api_key` | 是 | API Key，推荐使用 `${VAR}` 占位符 |
| `threshold` | 否 | 告警阈值，余额低于该值时触发告警 |
| `type` | 否 | `balance` 或 `credits`，用于展示和告警语义 |
| `enabled` | 否 | 是否启用，默认按启用处理 |

支持的 Provider：

| 平台 | `provider` | `api_key` 格式 |
| --- | --- | --- |
| OpenRouter | `openrouter` | 普通 API Key |
| UniAPI | `uniapi` | 普通 API Key |
| 微信排名 | `wxrank` | 普通 API Key |
| TikHub | `tikhub` | 普通 API Key |
| 火山引擎 | `volc` | `AccessKeyId:SecretAccessKey` |
| 阿里云 | `aliyun` | `AccessKeyId:AccessKeySecret` |

## 环境变量

### 必填或常用

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WEB_API_KEY` | 无 | `/api/*` 接口认证密钥，前端通过 `X-API-Key` 发送 |
| `WEBHOOK_URL` | 无 | 告警机器人地址 |
| `WEBHOOK_TYPE` | `custom` | `feishu` / `dingtalk` / `wecom` / `custom` |
| `WEBHOOK_SOURCE` | `credit-monitor` | 告警来源标识 |
| `CONFIG_PATH` | `config.json` | 配置文件路径 |
| `BALANCE_REFRESH_INTERVAL_SECONDS` | `3600` | Web 后台刷新间隔 |
| `MAX_CONCURRENT_CHECKS` | 配置文件值 | 并发检查数，上限由程序限制 |
| `ALERT_COOLDOWN_SECONDS` | `86400` | 同一项目告警冷却时间 |

### Web 和 API

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WEB_PORT` | `8080` | Web 服务端口 |
| `WEB_HOST` | `0.0.0.0` | Web 监听地址 |
| `WEB_ENABLE_CORS` | `false` | 是否启用 CORS |
| `CORS_ORIGINS` | 无 | CORS 白名单，逗号分隔；开启 CORS 时建议必填 |
| `WEB_AUTH_API_KEY` | 无 | `WEB_API_KEY` 的兼容别名 |
| `ALLOW_LEGACY_WEB_API_KEY` | `false` | 是否允许旧变量 `API_KEY` 作为 Web 认证密钥，不推荐生产使用 |

### 数据库和动态配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ENABLE_DATABASE` | `false` | 启用数据库，用于历史记录和动态配置 |
| `DATABASE_URL` | `sqlite:///./data/balance_alert.db` | SQLAlchemy 数据库连接 |
| `ENABLE_DYNAMIC_CONFIG` | `false` | 从数据库读取 `projects` / `subscriptions` / `email` |
| `ENABLE_HISTORY_API` | `false` | 启用历史数据 API |
| `CONFIG_ENCRYPTION_KEY` | 无 | 加密数据库中的 `api_key` 和邮箱 `password` |
| `BALANCE_ALERT_ENCRYPTION_KEY` | 无 | `CONFIG_ENCRYPTION_KEY` 的兼容别名 |
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

2. 初始化或升级表结构：

```bash
alembic upgrade head
```

如果已有表结构是手工创建的，且确认已经和当前模型一致，只是缺少 Alembic 版本记录，可以用：

```bash
alembic stamp head
```

3. 启动服务后，在 Web UI 或接口中维护项目配置。数据库里有项目时，应用会优先使用数据库项目；数据库为空时继续使用 `config.json`。

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
kubectl -n common-prod exec deploy/balance-alert -- alembic upgrade head
kubectl -n common-prod rollout status deploy/balance-alert
```

只有在确认表结构已经是当前版本、但 `alembic_version` 记录不准时，才使用：

```bash
kubectl -n common-prod exec deploy/balance-alert -- alembic stamp head
```

生产健康检查约定：

| Endpoint | 用途 | 特点 |
| --- | --- | --- |
| `/live` | `startupProbe` / `livenessProbe` | 只证明进程能响应，不依赖项目数据 |
| `/health` | `readinessProbe` | 会检查是否有数据、数据是否过期、cron 是否健康 |

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

## 常用验证命令

本地：

```bash
python services/monitor.py --dry-run
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

检查数据库版本：

```bash
alembic current
alembic heads
```

## 常见问题

### API Key 未配置，请设置 WEB_API_KEY

服务端没有读到 `WEB_API_KEY` 或 `WEB_AUTH_API_KEY`。检查 `.env`、Kubernetes Secret 和 Deployment 是否已经重启。

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
- 数据库项目读取失败，例如迁移没跑
- cron 失败日志非空

先看：

```bash
kubectl -n common-prod exec deploy/balance-alert -- curl -s http://127.0.0.1:8080/health
kubectl -n common-prod logs deploy/balance-alert --tail=200
```

### startup probe failed: HTTP probe failed with statuscode: 503

说明 startup probe 打到了 `/health`。启动探针应该使用 `/live`，因为启动阶段不能依赖余额数据是否已经初始化。

### Alembic 报 DuplicateColumn

通常是数据库表结构已经被手工改过，但 `alembic_version` 记录落后。先确认实际列和索引，再用 `alembic stamp head` 校准版本，不要盲目重跑迁移。

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
services/config_service.py
services/webhook_adapter.py
core/                  配置、日志、状态管理、密钥加密
web/                   Flask Web 看板和 API
static/ templates/     前端页面
database/ alembic/     可选历史库和动态配置
k8s/                   Kubernetes 部署示例
grafana/               可选监控面板
```
