# 💰 余额积分监控系统

多平台余额/积分监控告警系统，支持实时 Web 界面和自动告警通知。

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
| 🤖 OpenRouter | 积分 | 支持 OpenRouter API 积分监控 |
| 🔷 UniAPI | 积分 | 支持 UniAPI 账户积分监控 |
| 📱 微信排名 (WxRank) | 积分 | 支持微信公众号积分监控 |
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

# 项目 API Key（根据 config.json 中的项目数量配置）
PROJECT_1_API_KEY=sk-or-v1-xxx          # OpenRouter
PROJECT_2_API_KEY=wxrank-key-xxx        # 微信排名
PROJECT_3_API_KEY=AK-xxx:SK-xxx         # 火山云（用冒号分隔）
PROJECT_4_API_KEY=LTAI-xxx:secret-xxx   # 阿里云（用冒号分隔）
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
docker exec credit-monitor env | grep PROJECT

# 验证配置文件
docker exec credit-monitor cat /app/config.json
```

### 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
export WEBHOOK_URL="https://your-webhook-url"
export PROJECT_1_API_KEY="your-api-key"

# 3. 运行 Web 服务
python main.py

# 或执行一次检查
python monitor.py
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

### config.json 示例

```json
{
  "webhook": {
    "url": "${WEBHOOK_URL}",
    "type": "${WEBHOOK_TYPE}",
    "source": "credit-monitor"
  },
  "projects": [
    {
      "name": "OpenRouter",
      "provider": "openrouter",
      "api_key": "${PROJECT_1_API_KEY}",
      "threshold": 100.0,
      "type": "credits",
      "enabled": true
    },
    {
      "name": "火山云",
      "provider": "volc",
      "api_key": "${PROJECT_2_API_KEY}",
      "threshold": 5000,
      "type": "balance",
      "enabled": true
    }
  ],
  "subscriptions": [
    {
      "name": "OpenAI Plus",
      "cycle_type": "monthly",
      "renewal_day": 15,
      "alert_days_before": 3,
      "amount": 20.0,
      "currency": "USD"
    }
  ]
}
```

**字段说明**：
- `name`: 项目名称
- `provider`: 服务商（volc/aliyun/openrouter/tikhub/wxrank/uniapi）
- `api_key`: 使用环境变量占位符 `${PROJECT_X_API_KEY}`
- `threshold`: 告警阈值
- `type`: balance（余额）或 credits（积分）
- `cycle_type`: weekly/monthly/yearly
- `renewal_day`: 续费日期（1-31）

## 🎮 常用命令

```bash
# Docker 部署
docker-compose up -d          # 启动
docker-compose logs -f        # 查看日志
docker-compose restart        # 重启
docker-compose down           # 停止

# 本地运行
python main.py          # 启动 Web 服务
python monitor.py             # 执行检查
python monitor.py --dry-run   # 测试模式（不发送告警）
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
0 */6 * * * cd /app && python monitor.py >> /app/logs/cron.log 2>&1
```

## 📊 监控集成

支持 Prometheus + Grafana 监控：

```bash
# 启动监控栈
docker compose --profile monitoring up -d

# 访问
# Grafana: http://localhost:3000 (admin/admin123)
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
