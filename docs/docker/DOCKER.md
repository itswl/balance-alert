# Docker 部署指南

## 快速开始

```bash
# 1. 配置环境变量
cp .env.example .env
vim .env  # 填入真实值

# 2. 启动服务
docker-compose up -d

# 3. 查看日志
docker-compose logs -f
```

## 环境变量配置

### 必填变量

```bash
# Webhook 告警
WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN
WEBHOOK_TYPE=feishu  # 或 dingtalk, wecom

# 项目 API Key（根据 config.json 中的项目配置）
PROJECT_1_API_KEY=sk-or-v1-xxx
PROJECT_2_API_KEY=wxrank-key-xxx
PROJECT_3_API_KEY=AK-xxx:SK-xxx
```

### API Key 格式

| 服务商 | 格式 | 示例 |
|--------|------|------|
| OpenRouter | `sk-or-v1-xxx` | `sk-or-v1-1234abcd` |
| 火山云 | `AK:SK` | `AK-123:SK-456` |
| 阿里云 | `KeyId:Secret` | `LTAI-xxx:secret-xxx` |
| 微信排名 | 直接使用 | `wxrank-key-123` |
| TikHub | Bearer Token | `tikhub-token-xxx` |

### 可选变量

```bash
# 邮箱配置（如需邮箱扫描功能）
EMAIL_1_HOST=imap.feishu.cn
EMAIL_1_USERNAME=user@example.com
EMAIL_1_PASSWORD=your-password

# 系统配置
BALANCE_REFRESH_INTERVAL_SECONDS=3600  # 刷新间隔
MAX_CONCURRENT_CHECKS=20               # 并发数
ENABLE_DATABASE=true                   # 启用数据库
```

## 故障排查

### 环境变量未生效

```bash
# 检查容器中的环境变量
docker exec credit-monitor env | grep PROJECT

# 应该看到实际值，而不是 ${PROJECT_X_API_KEY}
```

### API Key 格式错误

火山云和阿里云必须用冒号分隔 AK 和 SK：

```bash
# ✅ 正确
PROJECT_3_API_KEY=AK-123:SK-456

# ❌ 错误
PROJECT_3_API_KEY=AK-123
```

### Webhook 无法发送

```bash
# 检查 Webhook URL 是否正确设置
docker exec credit-monitor env | grep WEBHOOK_URL

# 查看告警日志
docker-compose logs | grep webhook
```

## 数据持久化

```yaml
# docker-compose.yml
volumes:
  - ./config.json:/app/config.json:ro  # 配置文件
  - ./logs:/app/logs                   # 日志
  - ./data:/app/data                   # 数据库
```

## 安全建议

1. **永不提交 .env 文件到 Git**
   ```bash
   # 确保 .gitignore 包含
   .env
   ```

2. **使用环境变量存储敏感信息**
   - config.json 中使用占位符：`${PROJECT_1_API_KEY}`
   - .env 文件中填入真实值

3. **限制文件权限**
   ```bash
   chmod 600 .env
   chmod 600 config.json
   ```

4. **定期轮换 API Key**

---

**参考**: [README.md](README.md) 查看完整部署指南
