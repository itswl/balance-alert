# API 使用指南

## 基础信息

- **Base URL**: `http://localhost:8080`
- **格式**: JSON
- **认证**: API Key

## 认证

所有 `/api/*` 接口都需要 API Key。前端会将输入的 API Key 保存在浏览器 `localStorage`，后续请求会自动通过 `X-API-Key` 请求头发送。

```bash
export WEB_API_KEY="your-secret-key"

curl -H "X-API-Key: your-secret-key" http://localhost:8080/api/credits
```

## 核心 API

### 1. 健康检查

```bash
GET /health
GET /ready
GET /live
```

**响应**：
```json
{
  "status": "healthy",
  "has_data": true,
  "last_update": "2024-02-24T10:30:00Z"
}
```

### 2. 查询功能开关

```bash
GET /api/features
```

**响应**：
```json
{
  "status": "success",
  "features": {
    "subscriptions": false,
    "dynamic_config": false,
    "history": false
  }
}
```

### 3. 获取所有项目余额

```bash
GET /api/credits
```

**响应**：
```json
{
  "projects": [
    {
      "name": "OpenRouter Main",
      "owner_project": "AI 平台",
      "provider": "openrouter",
      "balance": 150.75,
      "threshold": 100.0,
      "currency": "USD",
      "need_alarm": false,
      "last_update": "2024-02-24T10:30:00Z"
    }
  ],
  "last_update": "2024-02-24T10:30:00Z"
}
```

### 4. 手动刷新余额

```bash
GET /api/refresh
POST /api/refresh
Content-Type: application/json

{
  "project_name": "OpenRouter Main"  // 可选：仅刷新指定项目
}
```

**限制**：30 秒冷却时间（触发时返回 429）

## 订阅 API（可选）

需启用：`ENABLE_SUBSCRIPTIONS=true`

### 5. 获取订阅状态

```bash
GET /api/subscriptions
```

**响应**：
```json
{
  "subscriptions": [
    {
      "name": "GitHub Copilot",
      "owner_project": "AI 平台",
      "cycle_type": "monthly",
      "renewal_date": "2024-03-01",
      "days_until_renewal": 5,
      "amount": 10.0,
      "currency": "USD",
      "need_renewal": true
    }
  ]
}
```

### 6. 添加订阅

```bash
POST /api/subscription/add
Content-Type: application/json

{
  "name": "Netflix Premium",
  "owner_project": "AI 平台",
  "cycle_type": "monthly",
  "renewal_day": 15,
  "alert_days_before": 3,
  "amount": 99.0,
  "currency": "CNY"
}
```

### 7. 删除订阅

```bash
POST /api/subscription/delete
DELETE /api/subscription/delete
Content-Type: application/json

{
  "name": "Netflix Premium"
}
```

## 动态配置 API（可选）

需启用：`ENABLE_DYNAMIC_CONFIG=true` 且 `ENABLE_DATABASE=true`

### 8. 获取项目配置

```bash
GET /api/config/projects
```

### 9. 更新项目阈值

```bash
POST /api/config/threshold
Content-Type: application/json

{
  "project_name": "OpenRouter Main",
  "new_threshold": 100
}
```

### 10. 获取邮箱配置

```bash
GET /api/config/emails
```

### 11. 添加/更新邮箱配置

```bash
POST /api/config/email
Content-Type: application/json

{
  "name": "mail-1",
  "host": "imap.example.com",
  "username": "user@example.com",
  "password": "${EMAIL_PASSWORD}"
}
```

### 12. 删除邮箱配置

```bash
POST /api/config/email/delete
Content-Type: application/json

{
  "name": "mail-1"
}
```

## 历史数据 API

需启用：`ENABLE_HISTORY_API=true` 且 `ENABLE_DATABASE=true`

### 13. 查询余额历史

```bash
GET /api/history/balance?project_id=abc123&days=7
```

**查询参数**：
- `project_id`: 项目ID（可选）
- `provider`: Provider类型（可选）
- `days`: 查询天数（默认7）
- `limit`: 返回记录数（默认100）

### 14. 获取趋势分析

```bash
GET /api/history/trend/<project_id>?days=30
```

**响应**：
```json
{
  "data": {
    "current_balance": 150.75,
    "min_balance": 120.00,
    "max_balance": 200.50,
    "avg_balance": 165.30,
    "change": -15.25,
    "change_percent": -9.19,
    "history": [...]
  }
}
```

### 15. 查询告警历史

```bash
GET /api/history/alerts?days=7&limit=50
```

### 16. 获取告警统计

```bash
GET /api/history/stats?days=30
```

## 错误处理

### 标准错误响应

```json
{
  "status": "error",
  "message": "错误描述",
  "errors": ["详细错误1"]  // 可选
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求错误（参数验证失败） |
| 401 | API Key 无效或未提供 |
| 404 | 资源不存在 |
| 429 | 刷新过于频繁（冷却中） |
| 503 | API Key 未配置或服务不可用 |
| 500 | 服务器错误 |

## Python 示例

```python
import requests

class BalanceAlertClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({'X-API-Key': api_key})

    def get_credits(self):
        """获取所有项目余额"""
        resp = self.session.get(f'{self.base_url}/api/credits')
        resp.raise_for_status()
        return resp.json()['projects']

    def refresh(self, project_name=None):
        """刷新余额"""
        data = {'project_name': project_name} if project_name else {}
        resp = self.session.post(f'{self.base_url}/api/refresh', json=data)
        resp.raise_for_status()
        return resp.json()

# 使用
client = BalanceAlertClient('http://localhost:8080', 'your-secret-key')
projects = client.get_credits()
for p in projects:
    print(f"{p['name']}: {p['balance']} {p['currency']}")
```

## cURL 速查表

```bash
# 健康检查
curl http://localhost:8080/health
curl http://localhost:8080/ready
curl http://localhost:8080/live

# 功能开关
curl -H "X-API-Key: your-secret-key" http://localhost:8080/api/features

# 获取余额
curl -H "X-API-Key: your-secret-key" http://localhost:8080/api/credits

# 刷新余额
curl -X POST -H "X-API-Key: your-secret-key" http://localhost:8080/api/refresh

# 添加订阅
curl -X POST -H "X-API-Key: your-secret-key" -H "Content-Type: application/json" \
     -d '{"name":"Netflix","cycle_type":"monthly","renewal_day":15,"amount":99}' \
     http://localhost:8080/api/subscription/add

# 查询趋势
curl -H "X-API-Key: your-secret-key" "http://localhost:8080/api/history/trend/abc123?days=30"
```

**最后更新**: 2026-05-17
