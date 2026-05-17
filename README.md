# Balance Alert

一个轻量的余额监控告警工具：定时检查多个平台余额，低于阈值时通过 Webhook 通知，并提供一个只读 Web 看板查看当前状态。

默认核心版只启用三件事：

- 余额检查
- Webhook 告警
- Web 看板

订阅提醒、邮箱扫描、历史数据库、Prometheus/Grafana、动态配置管理仍保留在代码中，但默认关闭，需要时再显式启用。

## 支持平台

| 平台 | Provider |
| --- | --- |
| 火山云 | `volc` |
| 阿里云 | `aliyun` |
| OpenRouter | `openrouter` |
| UniAPI | `uniapi` |
| 微信排名 | `wxrank` |
| TikHub | `tikhub` |

## 快速开始

```bash
pip install -r requirements.txt
cp config.json.example config.json
cp .env.example .env
```

编辑 `.env`，填入 Webhook 和 API Key：

```bash
WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN
WEBHOOK_TYPE=feishu
WEBHOOK_SOURCE=balance-alert
WEB_API_KEY=change-me

OPENROUTER_API_KEY=sk-or-v1-xxx
ALIYUN_1_API_KEY=LTAI-xxx:secret-xxx
VOLC_1_API_KEY=AK-xxx:SK-xxx
```

启动 Web 看板：

```bash
python main.py
```

访问：

```text
http://localhost:8080
```

执行一次检查：

```bash
python services/monitor.py --dry-run
```

## 配置方式

核心版只使用两种配置来源：

- `CONFIG_PATH` 指定的配置文件（默认 `config.json`）：项目、阈值、平台类型等结构化配置
- `.env`：API Key、Webhook URL 等敏感信息

配置文件支持 `${VAR}` 环境变量占位符，例如：

```json
{
  "name": "OpenRouter",
  "provider": "openrouter",
  "api_key": "${OPENROUTER_API_KEY}",
  "threshold": 100,
  "type": "credits",
  "enabled": true
}
```

## 常用环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WEB_PORT` | `8080` | Web 看板端口 |
| `WEB_API_KEY` | 无 | `/api/*` 接口访问密钥 |
| `WEBHOOK_URL` | 无 | 告警机器人地址 |
| `WEBHOOK_TYPE` | `custom` | `feishu` / `dingtalk` / `wecom` / `custom` |
| `CONFIG_PATH` | `config.json` | 配置文件路径 |
| `BALANCE_REFRESH_INTERVAL_SECONDS` | `3600` | 后台刷新间隔 |
| `MAX_CONCURRENT_CHECKS` | 配置文件值 | 并发检查数 |
| `ENABLE_WEB_ALARM` | `false` | Web 后台刷新是否发送真实告警 |

## 可选能力

安装可选依赖：

```bash
pip install -r requirements-optional.txt
```

按需打开功能：

| 变量 | 功能 |
| --- | --- |
| `ENABLE_SUBSCRIPTIONS=true` | 启用订阅提醒和订阅 API |
| `ENABLE_DATABASE=true` | 启用数据库历史记录 |
| `ENABLE_DYNAMIC_CONFIG=true` | 启用数据库动态配置覆盖 |
| `ENABLE_HISTORY_API=true` | 启用历史数据 API |
| `ENABLE_PROMETHEUS=true` | 启动 Prometheus metrics 服务 |
| `WEB_ENABLE_CORS=true` | 启用 CORS，需配合 `CORS_ORIGINS` |

### 数据库敏感字段加密

如果启用了数据库动态配置，建议同时设置 `CONFIG_ENCRYPTION_KEY`。设置后，`project_config.api_key` 和 `email_config.password` 会以 `enc:v1:...` 形式加密存储，应用读取时自动解密。

生成密钥：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

写入 `.env`：

```bash
CONFIG_ENCRYPTION_KEY=生成出来的密钥
```

已有明文数据会在下次通过配置仓库读取时自动回写为密文；如果使用 Alembic 管理数据库，先执行：

```bash
alembic upgrade head
```

## Docker

```bash
docker-compose up -d
```

如果只跑核心版，不需要启动 monitoring profile，也不需要配置数据库。

## 项目结构

```text
providers/             平台余额适配器
services/monitor.py    核心检查和告警流程
services/webhook_adapter.py
core/                  配置、日志、状态管理
web/                   Flask Web 看板和 API
static/ templates/     前端页面
database/ alembic/     可选历史库和动态配置
grafana/ k8s/          可选运维资产
```
