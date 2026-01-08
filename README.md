# 💰 余额积分与订阅监控系统

多平台余额与积分监控告警系统，支持实时 Web 界面和定时告警通知。

## ✨ 功能特性

- 🌐 **实时 Web 界面** - 可视化展示所有项目的余额/积分状态
- ⏰ **定时自动检查** - 每天定时运行，自动监控
- 🔔 **智能告警** - 余额/积分不足时自动发送 webhook 通知
- 📅 **订阅续费提醒** - 按月订阅服务续费提前通知
- 🔌 **多平台支持** - 支持火山云、阿里云、OpenRouter、微信排名等
- 📊 **灵活配置** - 每个项目独立配置阈值和告警规则
- 🐳 **Docker 部署** - 一键启动，开箱即用

## 🎯 支持的平台

| 平台 | 类型 | 说明 |
|------|------|------|
| 🌋 火山云 (Volc) | 余额 | 支持火山引擎账户余额监控 |
| ☁️ 阿里云 (Aliyun) | 余额 | 支持阿里云账户余额监控 |
| 🤖 OpenRouter | 积分 | 支持 OpenRouter API 积分监控 |
| 📱 微信排名 (WxRank) | 积分 | 支持微信公众号积分监控 |

## 🚀 快速开始

### 方式一：Docker 部署（推荐）

```bash
# 1. 克隆项目
git clone <your-repo>
cd check_credits

# 2. 配置项目
# 编辑 config.json，添加你的项目配置

# 3. 构建并启动
./run.sh build
./run.sh start

# 4. 访问 Web 界面
# 打开浏览器访问: http://localhost:8080
```

### 方式二：本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置项目
# 编辑 config.json

# 3. 运行 Web 服务器
python3 web_server.py

# 或者直接检查一次
python3 monitor.py
```

## 📧 Webhook 配置

系统支持多种 webhook 类型，可以发送告警到不同的平台。

### 支持的 Webhook 类型

| 类型 | 说明 | 配置值 |
|------|------|--------|
| 🟦 **飞书** | 飞书机器人 | `feishu` |
| 🟦 **钉钉** | 钉钉机器人 | `dingtalk` |
| 🟩 **企业微信** | 企业微信机器人 | `wecom` |
| ⚙️ **自定义** | 自定义 JSON 格式 | `custom` (默认) |

### 配置示例

#### 飞书机器人
```json
{
  "webhook": {
    "url": "https://open.feishu.cn/open-apis/bot/v2/hook/your-token",
    "type": "feishu",
    "source": "credit-monitor"
  }
}
```

飞书消息格式：
```json
{
  "msg_type": "text",
  "content": {
    "text": "【余额告警】\n\n项目: xxx\n服务商: xxx\n..."
  }
}
```

#### 钉钉机器人
```json
{
  "webhook": {
    "url": "https://oapi.dingtalk.com/robot/send?access_token=your-token",
    "type": "dingtalk",
    "source": "credit-monitor"
  }
}
```

#### 企业微信机器人
```json
{
  "webhook": {
    "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key",
    "type": "wecom",
    "source": "credit-monitor"
  }
}
```

#### 自定义格式
```json
{
  "webhook": {
    "url": "https://your-webhook-url.com/notify",
    "type": "custom",
    "source": "credit-monitor"
  }
}
```

自定义消息格式：
```json
{
  "Type": "AlarmNotification",
  "RuleName": "xxx余额告警",
  "Level": "critical",
  "Resources": [{
    "ProjectName": "xxx",
    "Provider": "xxx",
    "CurrentValue": 1000,
    "Threshold": 5000,
    "Unit": "￥",
    "Message": "..."
  }]
}
```

### 测试 Webhook

```bash
# 测试模式（不发送真实告警）
python3 monitor.py --dry-run

# 实际发送告警
python3 monitor.py
```

---

## 📝 配置说明

### config.json 配置文件

```json
{
  "webhook": {
    "url": "http://your-webhook-url",
    "source": "credit-monitor"
  },
  "subscriptions": [
    {
      "name": "订阅名称",
      "renewal_day": 续费日（每月几号）,
      "alert_days_before": 提前几天提醒,
      "amount": 续费金额,
      "currency": "货币单位",
      "enabled": true
    }
  ],
  "projects": [
    {
      "name": "项目名称",
      "provider": "服务商标识",
      "api_key": "API密钥",
      "threshold": 告警阈值,
      "type": "balance/credits",
      "enabled": true
    }
  ]
}
```

### 配置字段说明

#### 项目配置 (projects)

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `name` | ✅ | 项目名称 | "火山云-生产环境" |
| `provider` | ✅ | 服务商标识 | volc / aliyun / openrouter / wxrank |
| `api_key` | ✅ | API 密钥 | 各平台的密钥格式见下文 |
| `threshold` | ✅ | 告警阈值 | 低于此值时触发告警 |
| `type` | ⭕ | 类型 | balance(余额) / credits(积分) |
| `enabled` | ⭕ | 是否启用 | true / false，默认 true |

#### 订阅配置 (subscriptions)

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `name` | ✅ | 订阅名称 | "OpenAI Plus" |
| `renewal_day` | ✅ | 每月续费日期 | 6 (每月 6 号) |
| `alert_days_before` | ✅ | 提前多少天提醒 | 3 (提前 3 天) |
| `amount` | ✅ | 续费金额 | 20 |
| `currency` | ⭕ | 货币单位 | "USD" / "CNY"，默认 CNY |
| `enabled` | ⭕ | 是否启用 | true / false，默认 true |

### API 密钥格式

#### 火山云 (volc)
格式：`AK:SK`（用冒号分隔）
```json
"api_key": "AKLT***:Tmp***"
```

#### 阿里云 (aliyun)
格式：`AccessKeyId:AccessKeySecret`（用冒号分隔）
```json
"api_key": "LTAI5t***:34PXW3***"
```

#### OpenRouter
格式：完整的 API Key
```json
"api_key": "sk-or-v1-***"
```

#### 微信排名 (wxrank)
格式：直接使用 key
```json
"api_key": "a7136e65***"
```

### 配置示例

```json
{
  "webhook": {
    "url": "https://your-webhook.com/notify",
    "source": "credit-monitor"
  },
  "subscriptions": [
    {
      "name": "OpenAI Plus",
      "renewal_day": 6,
      "alert_days_before": 3,
      "amount": 20,
      "currency": "USD",
      "enabled": true
    },
    {
      "name": "GitHub Copilot",
      "renewal_day": 15,
      "alert_days_before": 5,
      "amount": 10,
      "currency": "USD",
      "enabled": true
    }
  ],
  "projects": [
    {
      "name": "火山云-生产环境",
      "provider": "volc",
      "api_key": "AKLTxxx:TmpBxxx",
      "threshold": 7000,
      "type": "balance",
      "enabled": true
    },
    {
      "name": "OpenRouter-AI服务",
      "provider": "openrouter",
      "api_key": "sk-or-v1-xxx",
      "threshold": 10000,
      "type": "credits",
      "enabled": true
    }
  ]
}
```

## 🎮 使用方法

### Docker 命令

```bash
# 构建镜像
./run.sh build

# 启动服务（Web + 定时任务）
./run.sh start

# 本地运行 Web 服务器
./run.sh web

# 停止服务
./run.sh stop

# 重启服务
./run.sh restart

# 查看容器日志
./run.sh logs

# 查看定时任务日志
./run.sh cron-logs

# 立即执行一次检查
./run.sh run-now

# 进入容器 Shell
./run.sh shell

# 清理容器和镜像
./run.sh clean
```

### 本地运行命令

```bash
# 启动 Web 服务器
python3 web_server.py

# 执行一次检查（发送告警）
python3 monitor.py

# 测试模式（不发送告警）
python3 monitor.py --dry-run

# 检查指定项目
python3 monitor.py --project "项目名称"
```

## 🌐 Web 界面

启动服务后访问 http://localhost:8080

### 功能特性

- 📊 实时显示所有项目的余额/积分状态
- 🔄 支持手动刷新数据
- 📈 可视化进度条显示余额比例
- ⚠️ 自动标识余额不足的项目
- 🎨 美观的卡片式布局

### 自动刷新

- Web 界面每 **30 秒** 自动刷新一次数据
- 后台每 **5 分钟** 重新查询一次余额
- 可以点击"刷新数据"按钮立即更新

## ⏰ 定时任务

### 默认定时

- 每天 **上午 9:00** 执行检查
- 每天 **下午 15:00** 执行检查

### 修改定时

编辑 `crontab` 文件：

```bash
# 每天 9 点和 15 点运行
0 9,15 * * * cd /app && python monitor.py >> /app/logs/cron.log 2>&1

# 每 6 小时运行一次
0 */6 * * * cd /app && python monitor.py >> /app/logs/cron.log 2>&1

# 每天凌晨 1 点运行
0 1 * * * cd /app && python monitor.py >> /app/logs/cron.log 2>&1
```

修改后重新构建镜像：
```bash
./run.sh stop
./run.sh build
./run.sh start
```

## 🔔 告警机制

### 告警模式

#### 1. Web 模式（默认）
- Web 服务器**仅查询**，不发送告警
- 避免频繁刷新导致重复告警

#### 2. 定时任务模式
- 定时任务会**发送真实告警**
- 按计划定期检查和通知

#### 3. 启用 Web 告警（可选）

如果需要 Web 也发送告警，设置环境变量：

```bash
# 本地运行
ENABLE_WEB_ALARM=true python3 web_server.py

# Docker 运行
# 编辑 docker-compose.yml，添加环境变量
environment:
  - ENABLE_WEB_ALARM=true
```

### Webhook 数据格式

```json
{
  "Type": "AlarmNotification",
  "RuleName": "项目名称余额告警",
  "Level": "critical",
  "Resources": [
    {
      "ProjectName": "项目名称",
      "Provider": "服务商",
      "CurrentCredits": 当前余额,
      "Threshold": 告警阈值,
      "Message": "余额不足，当前余额: xxx, 阈值: xxx"
    }
  ]
}
```

## 📂 项目结构

```
check_credits/
├── config.json              # 配置文件
├── monitor.py               # 监控主程序
├── web_server.py           # Web 服务器
├── providers/              # 服务商适配器
│   ├── __init__.py
│   ├── volc.py            # 火山云
│   ├── aliyun.py          # 阿里云
│   ├── openrouter.py      # OpenRouter
│   └── wxrank.py          # 微信排名
├── templates/              # Web 模板
│   └── index.html
├── Dockerfile              # Docker 镜像
├── docker-compose.yml      # Docker Compose 配置
├── docker-compose.web.yml  # 分离部署配置
├── crontab                # 定时任务配置
├── requirements.txt        # Python 依赖
├── run.sh                 # 管理脚本
└── README.md              # 说明文档
```

## 🔧 高级配置

### 自定义端口

编辑 `docker-compose.yml`：

```yaml
ports:
  - "8080:8080"  # 改为 8080 端口
```

编辑 `web_server.py`：

```python
app.run(host='0.0.0.0', port=8080, debug=False)
```

### 添加新的服务商

1. 在 `providers/` 目录创建新文件 `yourprovider.py`
2. 实现 `YourProvider` 类，包含 `get_credits()` 方法
3. 在 `providers/__init__.py` 中注册
4. 在 `config.json` 中添加项目配置

参考现有适配器实现。

## 📊 日志查看

### 容器日志

```bash
# 查看容器实时日志
docker logs -f credit-monitor

# 查看最近 100 行
docker logs --tail 100 credit-monitor
```

### 定时任务日志

```bash
# 查看定时任务执行日志
docker exec credit-monitor cat /app/logs/cron.log

# 实时查看
docker exec credit-monitor tail -f /app/logs/cron.log
```

### 本地日志

日志文件位置：`./logs/cron.log`

## 🐛 故障排查

### Web 界面无法访问

```bash
# 检查容器是否运行
docker ps | grep credit-monitor

# 查看容器日志
docker logs credit-monitor

# 检查端口占用
lsof -i :8080
```

### 告警未发送

1. 检查 `config.json` 中 webhook 配置是否正确
2. 查看日志确认是否触发告警条件
3. 确认不是测试模式（dry_run）

### API 密钥错误

检查各平台密钥格式是否正确：
- 火山云/阿里云：用冒号分隔 AK 和 SK
- OpenRouter：完整的 sk-or-v1-xxx
- 微信排名：直接使用 key

## 📄 许可证

本项目仅供学习和个人使用。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📮 联系方式

如有问题，请提交 Issue。
