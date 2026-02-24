# API 使用指南

## 基础信息

- **Base URL**: `http://localhost:8080`
- **格式**: JSON
- **认证**: API Key (Bearer Token)

## 认证

```bash
# 设置 API Key
export API_KEY="your-secret-key"

# 请求方式1：Header
curl -H "Authorization: Bearer your-key" http://localhost:8080/api/credits

# 请求方式2：Query
curl "http://localhost:8080/api/credits?api_key=your-key"
```

## 核心 API

### 1. 健康检查

```bash
GET /health
```

**响应**：
```json
{
  "status": "healthy",
  "has_data": true,
  "last_update": "2024-02-24T10:30:00Z"
}
```

### 2. 获取所有项目余额

```bash
GET /api/credits
GET /api/credits?force_refresh=true  # 强制刷新
```

**响应**：
```json
{
  "projects": [
    {
      "name": "OpenRouter Main",
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

### 3. 手动刷新余额

```bash
POST /api/refresh
Content-Type: application/json

{
  "project_name": "OpenRouter Main"  // 可选：仅刷新指定项目
}
```

**限制**：30秒冷却时间

### 4. 获取订阅状态

```bash
GET /api/subscriptions
```

**响应**：
```json
{
  "subscriptions": [
    {
      "name": "GitHub Copilot",
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

### 5. 添加订阅

```bash
POST /api/subscription/add
Content-Type: application/json

{
  "name": "Netflix Premium",
  "cycle_type": "monthly",
  "renewal_day": 15,
  "alert_days_before": 3,
  "amount": 99.0,
  "currency": "CNY"
}
```

### 6. 删除订阅

```bash
POST /api/subscription/delete
Content-Type: application/json

{
  "name": "Netflix Premium"
}
```

## 历史数据 API

需启用数据库：`ENABLE_DATABASE=true`

### 7. 查询余额历史

```bash
GET /api/history/balance?project_id=abc123&days=7
```

**查询参数**：
- `project_id`: 项目ID（可选）
- `provider`: Provider类型（可选）
- `days`: 查询天数（默认7）
- `limit`: 返回记录数（默认100）

### 8. 获取趋势分析

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

### 9. 查询告警历史

```bash
GET /api/history/alerts?days=7&limit=50
```

### 10. 获取告警统计

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
| 401 | 未授权（API Key 无效） |
| 404 | 资源不存在 |
| 429 | 请求过多（超出速率限制） |
| 500 | 服务器错误 |

## 速率限制

| 端点 | 限制 |
|------|------|
| 全局 | 100 请求/分钟 |
| `/api/refresh` | 2 请求/分钟 + 30秒冷却 |
| `/api/subscription/*` | 20 请求/分钟 |
| `/api/history/*` | 50 请求/分钟 |

**超出限制响应**：
```
HTTP/1.1 429 Too Many Requests
X-RateLimit-Remaining: 0

{
  "status": "error",
  "message": "Rate limit exceeded"
}
```

## Python 示例

```python
import requests

class BalanceAlertClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}'
        })

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
client = BalanceAlertClient('http://localhost:8080', 'your-api-key')
projects = client.get_credits()
for p in projects:
    print(f"{p['name']}: {p['balance']} {p['currency']}")
```

## cURL 速查表

```bash
# 健康检查
curl http://localhost:8080/health

# 获取余额
curl -H "Authorization: Bearer KEY" \
     http://localhost:8080/api/credits

# 刷新余额
curl -X POST -H "Authorization: Bearer KEY" \
     http://localhost:8080/api/refresh

# 添加订阅
curl -X POST -H "Authorization: Bearer KEY" \
     -H "Content-Type: application/json" \
     -d '{"name":"Netflix","cycle_type":"monthly","renewal_day":15,"amount":99}' \
     http://localhost:8080/api/subscription/add

# 查询趋势
curl -H "Authorization: Bearer KEY" \
     "http://localhost:8080/api/history/trend/abc123?days=30"
```

## Swagger 文档

访问交互式 API 文档（如果已启用）：

```
http://localhost:8080/apidocs
```

---

**最后更新**: 2024-02-24
