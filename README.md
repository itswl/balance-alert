# 💰 余额监控系统

多平台余额监控告警系统，支持实时 Web 界面和自动告警通知。
## ✨ 核心功能

- 🌐 **Web 界面** - 实时查看所有项目余额状态
- 🔔 **自动告警** - 余额不足时自动通知（支持飞书/钉钉/企业微信）
- 📅 **订阅管理** - 续费提醒（周/月/年周期）
- 📧 **邮箱扫描** - 自动识别欠费邮件
- 🔌 **多平台** - 火山云、阿里云、OpenRouter、TikHub 等
- 🐳 **容器化** - Docker 一键部署

## 🎯 支持的平台

| 平台 | 类型 | 说明 |
|------|------|------|
| 🌋 火山云 (Volc) | 余额 | 支持火山引擎账户余额监控 |
| ☁️ 阿里云 (Aliyun) | 余额 | 支持阿里云账户余额监控 |
| 🤖 OpenRouter | 余额 | 支持 OpenRouter API 余额监控 |
| 🔷 UniAPI | 余额 | 支持 UniAPI 账户余额监控 |
| 📱 微信排名 (WxRank) | 余额 | 支持微信公众号余额监控 |
| 🎬 TikHub | 余额 | 支持 TikHub API 余额监控 |

## 🚀 快速开始

### Docker 部署（推荐）

```bash
# 1. 配置环境变量和 API Key
cp .env.example .env
vim .env  # 填入真实的 API Key 和 Webhook URL

# 2. 编辑项目配置
vim config.json

# 3. 启动服务
docker-compose up -d

# 4. 访问 Web 界面
open http://localhost:8080
```

**环境变量配置**：

```bash
# Webhook 告警
WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN
WEBHOOK_TYPE=feishu
WEBHOOK_SOURCE=credit-monitor

# 项目 API Key（与 config.json 中的 ${VAR} 对应）
OPENROUTER_API_KEY=sk-or-v1-xxx
UNIAPI_API_KEY=uniapi-key-xxx
WXRANK_API_KEY=wxrank-key-xxx
VOLC_1_API_KEY=AK-xxx:SK-xxx
VOLC_2_API_KEY=AK-xxx:SK-xxx
ALIYUN_1_API_KEY=LTAI-xxx:secret-xxx
ALIYUN_2_API_KEY=LTAI-xxx:secret-xxx
TIKHUB_API_KEY=tikhub-token-xxx

# 邮箱密码（如启用邮箱扫描，建议只放 env）
EMAIL_PASSWORD=your-password
```

**API Key 格式要求**：

| 服务商 | 格式 | 示例 |
|--------|------|------|
| OpenRouter | `sk-or-v1-xxx` | `sk-or-v1-1234abcd` |
| 微信排名 | 直接使用 | `wxrank-key-123` |
| 火山云 | `AK:SK` | `AK-123:SK-456` |
| 阿里云 | `KeyId:Secret` | `LTAI-xxx:secret-xxx` |
| TikHub | Bearer Token | `tikhub-token-xxx` |

**故障排查**：

```bash
# 查看容器日志
docker-compose logs -f

# 检查环境变量是否生效
docker exec credit-monitor env | grep -E 'API_KEY|WEBHOOK'

# 验证配置文件
docker exec credit-monitor cat /app/config.json
```

### 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
export WEBHOOK_URL="https://your-webhook-url"
export OPENROUTER_API_KEY="your-api-key"

# 3. 运行 Web 服务
python main.py

# 或执行一次检查
python services/monitor.py
```

## 📧 Webhook 告警配置

支持飞书、钉钉、企业微信机器人通知。

```bash
# 环境变量方式
WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN
WEBHOOK_TYPE=feishu  # 或 dingtalk, wecom, custom
```

```json
// config.json 方式
{
  "webhook": {
    "url": "${WEBHOOK_URL}",
    "type": "${WEBHOOK_TYPE}",
    "source": "credit-monitor"
  }
}
```

---

## 📝 配置说明

系统的配置分为 **静态配置** 和 **动态配置** 两部分：

### 1. 静态配置 (`.env` 或 `config.json`)
主要用于配置系统基础参数，如 Webhook 地址、发件邮箱信息、系统参数等。这部分配置在容器运行期间是只读的。

推荐使用环境变量 `.env` 进行配置：
```bash
# Webhook 配置
WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN
WEBHOOK_TYPE=feishu
```

### 配置优先级（从低到高）

1. `config.json`（基础配置；支持 `${VAR}` 占位符）
2. 环境变量覆盖系统设置：`BALANCE_REFRESH_INTERVAL_SECONDS / MAX_CONCURRENT_CHECKS / MIN_REFRESH_INTERVAL_SECONDS / ENABLE_SMART_REFRESH / SMART_REFRESH_THRESHOLD_PERCENT`
3. 数据库动态配置覆盖：`projects/subscriptions/email`（数据库有数据则整段以数据库为准）

`config.json` 与数据库配置中的字符串字段都支持 `${VAR}` 占位符替换（环境变量不存在则保留原样）。

### 2. 动态配置 (数据库)
为了兼容 Kubernetes/Docker 的只读挂载规范，并支持高并发的页面修改：
**项目配置（API 密钥、告警阈值）**和**订阅配置（续费提醒）**均已迁移至 SQLite 数据库 (`data/balance_alert.db`) 中管理。

- **初始化**：数据库表会在 Web 服务器启动时自动创建。若数据库配置表为空，则会使用静态配置（`.env`/`config.json`）作为运行时配置来源。
- **日常管理**：通过 Web UI 增删改项目/订阅/邮箱配置后，会写入数据库；此后运行时会优先使用数据库中的 `projects/subscriptions/email`。

> 💡 **版本升级提示**：如果你是从旧版本升级上来的，请在拉取最新代码后进入容器执行 `alembic upgrade head`，或直接执行 `python scripts/migrate_config_to_db.py` 自动完成数据的无缝迁移。

## 🎮 常用命令

```bash
# Docker 部署
docker-compose up -d          # 启动
docker-compose logs -f        # 查看日志
docker-compose restart        # 重启
docker-compose down           # 停止

# 本地运行
python main.py          # 启动 Web 服务
python services/monitor.py             # 执行检查
python services/monitor.py --dry-run   # 测试模式（不发送告警）
```

## 🌐 Web 界面

访问 `http://localhost:8080` 查看：
- 📊 所有项目余额状态
- 📅 订阅续费提醒
- 🔄 手动刷新数据
- ⚠️ 余额不足告警

## ⏰ 定时任务

默认每天 9:00 和 15:00 执行检查，修改 `crontab` 文件可自定义时间。

```bash
# 每 6 小时运行一次
0 */6 * * * cd /app && python services/monitor.py >> /app/logs/cron.log 2>&1
```

## 📊 监控集成

支持 Prometheus + Grafana 监控：

```bash
# 启动监控栈
docker compose --profile monitoring up -d

# 访问
# Grafana: http://localhost:3000 (账号和密码来自 .env 中的 GRAFANA_ADMIN_USER/GRAFANA_ADMIN_PASSWORD)
# Prometheus: http://localhost:9090
# Metrics: http://localhost:9100/metrics
```

详见 [PROMETHEUS_GRAFANA.md](docs/PROMETHEUS_GRAFANA.md)

## 📚 文档

- [API 文档](docs/API.md) - REST API 使用指南
- [架构文档](docs/ARCHITECTURE.md) - 系统架构设计
- [贡献指南](docs/CONTRIBUTING.md) - 开发和贡献指南

## 📄 许可证

MIT License
