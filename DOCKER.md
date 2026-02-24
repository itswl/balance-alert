# Docker 部署指南

## 环境变量配置

### 问题：占位符未被替换

如果你在日志中看到类似的错误：

```
Invalid URL '${WEBHOOK_URL}': No scheme supplied
your submitted API token is ${PROJECT_7_API_KEY}
```

这说明 `config.json` 中的环境变量占位符没有被替换成实际值。

### 解决方案1：使用 .env 文件（推荐）

1. **复制环境变量模板**：

```bash
cp .env.example .env
```

2. **编辑 .env 文件，填入真实值**：

```bash
vim .env
```

示例：
```bash
# Webhook 配置
WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_ACTUAL_TOKEN

# 项目 API Key
PROJECT_1_API_KEY=sk-or-v1-actual-key-here
PROJECT_2_API_KEY=wxrank-actual-key-here
PROJECT_3_API_KEY=AK-xxx:SK-xxx
PROJECT_4_API_KEY=AK-xxx:SK-xxx
PROJECT_5_API_KEY=LTAI-xxx:secret-xxx
PROJECT_6_API_KEY=LTAI-xxx:secret-xxx
PROJECT_7_API_KEY=tikhub-actual-key-here
```

3. **修改 docker-compose.yml，加载 .env 文件**：

```yaml
version: '3.8'

services:
  credit-monitor:
    build: .
    image: credit-monitor:latest
    container_name: credit-monitor
    restart: unless-stopped
    ports:
      - "8080:8080"
      - "9100:9100"
    volumes:
      - ./config.json:/app/config.json
      - ./logs:/app/logs
      - ./data:/app/data  # 数据库持久化
    env_file:
      - .env  # ← 添加这一行
    environment:
      - TZ=Asia/Shanghai
    command: /app/start.sh
```

4. **重启容器**：

```bash
docker-compose down
docker-compose up -d
```

### 解决方案2：直接在 docker-compose.yml 中配置

如果不想用 .env 文件，可以直接在 docker-compose.yml 中设置：

```yaml
services:
  credit-monitor:
    # ... 其他配置
    environment:
      - TZ=Asia/Shanghai
      - WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN
      - PROJECT_1_API_KEY=sk-or-v1-your-key
      - PROJECT_2_API_KEY=wxrank-your-key
      - PROJECT_3_API_KEY=AK-xxx:SK-xxx
      - PROJECT_4_API_KEY=AK-xxx:SK-xxx
      - PROJECT_5_API_KEY=LTAI-xxx:secret-xxx
      - PROJECT_6_API_KEY=LTAI-xxx:secret-xxx
      - PROJECT_7_API_KEY=tikhub-your-key
```

**⚠️ 注意**：这种方式会将密钥明文写在 docker-compose.yml 中，不建议提交到 Git。

### 解决方案3：纯配置文件模式（不推荐）

如果你不想用环境变量，可以直接在 `config.json` 中填写真实值：

```json
{
  "webhook": {
    "url": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_ACTUAL_TOKEN",
    "type": "feishu"
  },
  "projects": [
    {
      "name": "OpenRouter",
      "provider": "openrouter",
      "api_key": "sk-or-v1-your-actual-key-here",
      "threshold": 100.0
    }
  ]
}
```

**⚠️ 警告**：这种方式会将 API Key 明文存储，有安全风险，且容易误提交到 Git。

## API Key 格式要求

根据日志中的错误，不同服务商有不同的格式要求：

| 服务商 | Provider | API Key 格式 | 示例 |
|--------|----------|--------------|------|
| OpenRouter | `openrouter` | `sk-or-v1-xxx` | `sk-or-v1-1234567890abcdef` |
| WxRank | `wxrank` | 任意字符串 | `wxrank-api-key-12345` |
| 火山引擎 | `volc` | `AK:SK` | `AK-1234:SK-5678` |
| 阿里云 | `aliyun` | `AccessKeyId:AccessKeySecret` | `LTAI-xxx:secret-xxx` |
| TikHub | `tikhub` | 任意字符串 | `tikhub-api-key-12345` |

### 火山引擎 API Key 格式

```bash
# 错误格式
PROJECT_3_API_KEY=AK-1234567890

# 正确格式（用冒号分隔 AK 和 SK）
PROJECT_3_API_KEY=AK-1234567890:SK-0987654321
```

### 阿里云 API Key 格式

```bash
# 错误格式
PROJECT_5_API_KEY=LTAI5tAbCdEfGhIjKlMn

# 正确格式（用冒号分隔 AccessKeyId 和 AccessKeySecret）
PROJECT_5_API_KEY=LTAI5tAbCdEfGhIjKlMn:OpQrStUvWxYz1234567890
```

## 数据持久化

为了保留数据库和日志，建议挂载以下目录：

```yaml
volumes:
  - ./config.json:/app/config.json  # 配置文件
  - ./logs:/app/logs                # 日志目录
  - ./data:/app/data                # 数据库目录
```

这样即使容器重启，数据也不会丢失。

## 完整的 docker-compose.yml 示例

```yaml
version: '3.8'

services:
  credit-monitor:
    build: .
    image: credit-monitor:latest
    container_name: credit-monitor
    restart: unless-stopped

    ports:
      - "8080:8080"   # Web UI
      - "9100:9100"   # Prometheus Metrics

    volumes:
      - ./config.json:/app/config.json:ro  # 只读挂载配置
      - ./logs:/app/logs                    # 日志持久化
      - ./data:/app/data                    # 数据库持久化

    env_file:
      - .env  # 从 .env 文件加载环境变量

    environment:
      - TZ=Asia/Shanghai
      - ENABLE_DATABASE=true           # 启用数据库
      - LOG_LEVEL=INFO                 # 日志级别
      - ENABLE_WEB_ALARM=false         # Web 不发送告警

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

    command: /app/start.sh
```

## 验证配置

启动后检查日志，确认没有以下错误：

```bash
# 查看日志
docker-compose logs -f

# 应该看到类似的成功信息：
# ✅ 数据库已初始化
# [INFO] 开始监控 7 个项目...
# [INFO] [OpenRouter] 当前余额: 123.45

# 不应该看到：
# ❌ Invalid URL '${WEBHOOK_URL}'
# ❌ your submitted API token is ${PROJECT_X_API_KEY}
```

## 故障排查

### 1. 环境变量未生效

**检查**：
```bash
docker exec credit-monitor env | grep PROJECT
```

**应该看到**：
```
PROJECT_1_API_KEY=sk-or-v1-actual-key
PROJECT_2_API_KEY=wxrank-actual-key
```

**不应该看到空值或占位符**。

### 2. API Key 格式错误

**错误日志**：
```
❌ 火山云 API Key 格式错误，应为 'AK:SK' 格式
```

**解决**：检查环境变量，确保使用冒号分隔：
```bash
# 正确
PROJECT_3_API_KEY=AK-123:SK-456

# 错误
PROJECT_3_API_KEY=AK-123
```

### 3. Webhook 发送失败

**错误日志**：
```
Invalid URL '${WEBHOOK_URL}': No scheme supplied
```

**解决**：在 .env 中设置真实的 Webhook URL：
```bash
WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_ACTUAL_TOKEN
```

## 安全建议

1. **永远不要提交 .env 到 Git**：
   ```bash
   # .gitignore 中应包含
   .env
   config.json  # 如果包含真实密钥
   ```

2. **使用环境变量而非配置文件存储密钥**：
   - ✅ 推荐：`config.json` 中用 `${PROJECT_1_API_KEY}`，值存在 `.env`
   - ❌ 不推荐：`config.json` 中直接写 `"api_key": "sk-or-v1-real-key"`

3. **定期轮换 API Key**

4. **限制文件权限**：
   ```bash
   chmod 600 .env
   chmod 600 config.json
   ```

---

**最后更新**: 2024-02-24
**维护者**: 项目团队
