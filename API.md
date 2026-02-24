# API 使用指南

Balance Alert 提供完整的 REST API 用于查询余额、管理订阅和查看历史数据。

## 目录

- [认证](#认证)
- [核心 API](#核心-api)
- [订阅管理 API](#订阅管理-api)
- [历史数据 API](#历史数据-api)
- [配置 API](#配置-api)
- [错误处理](#错误处理)
- [速率限制](#速率限制)
- [示例代码](#示例代码)

## 基础信息

**Base URL**: `http://localhost:8080`

**请求格式**: JSON

**响应格式**: JSON

**时区**: UTC

## 认证

### API Key 认证（推荐）

在环境变量中设置 API Key：

```bash
export API_KEY="your-secret-key-here"
```

请求时携带 Token：

**方式1：Authorization Header**
```bash
curl -H "Authorization: Bearer your-secret-key-here" \
     http://localhost:8080/api/credits
```

**方式2：Query Parameter**
```bash
curl "http://localhost:8080/api/credits?api_key=your-secret-key-here"
```

### JWT 认证（高级）

启用 JWT 认证：

```bash
export ENABLE_JWT=true
export JWT_SECRET_KEY="your-jwt-secret"
```

获取 Token：

```bash
curl -X POST http://localhost:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "secret"}'
```

响应：

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 3600
}
```

使用 Token：

```bash
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
     http://localhost:8080/api/credits
```

---

## 核心 API

### 1. 健康检查

检查服务运行状态。

**请求**

```
GET /health
```

**响应**

```json
{
  "status": "healthy",
  "has_data": true,
  "last_update": "2024-02-24T10:30:00Z",
  "uptime_seconds": 3600,
  "version": "1.0.0"
}
```

**状态码**

- `200 OK` - 服务正常且有数据
- `503 Service Unavailable` - 服务启动中或数据过期

---

### 2. 获取所有项目余额

获取所有配置项目的最新余额。

**请求**

```
GET /api/credits
```

**查询参数**（可选）
- `force_refresh=true` - 强制刷新（忽略缓存）

**响应**

```json
{
  "projects": [
    {
      "name": "OpenRouter Main",
      "provider": "openrouter",
      "balance": 150.75,
      "threshold": 100.0,
      "currency": "USD",
      "type": "credits",
      "need_alarm": false,
      "last_update": "2024-02-24T10:30:00Z"
    },
    {
      "name": "Claude API",
      "provider": "anthropic",
      "balance": 45.20,
      "threshold": 50.0,
      "currency": "USD",
      "type": "balance",
      "need_alarm": true,
      "last_update": "2024-02-24T10:30:00Z"
    }
  ],
  "last_update": "2024-02-24T10:30:00Z",
  "next_refresh": "2024-02-24T11:30:00Z"
}
```

**字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 项目名称 |
| provider | string | Provider 类型（openrouter, anthropic, etc.） |
| balance | float | 当前余额或积分 |
| threshold | float | 告警阈值 |
| currency | string | 货币单位（USD, CNY） |
| type | string | 类型（balance=余额, credits=积分） |
| need_alarm | boolean | 是否需要告警（balance < threshold） |
| last_update | string | 最后更新时间（ISO 8601） |

**cURL 示例**

```bash
curl -X GET 'http://localhost:8080/api/credits' \
  -H 'Authorization: Bearer your-api-key'
```

**Python 示例**

```python
import requests

response = requests.get(
    'http://localhost:8080/api/credits',
    headers={'Authorization': 'Bearer your-api-key'}
)
data = response.json()

for project in data['projects']:
    print(f"{project['name']}: {project['balance']} {project['currency']}")
```

---

### 3. 手动刷新余额

触发一次立即刷新所有项目余额。

**请求**

```
POST /api/refresh
```

**请求体**（可选）

```json
{
  "project_name": "OpenRouter Main"  // 可选：仅刷新指定项目
}
```

**响应**

```json
{
  "status": "success",
  "message": "刷新完成",
  "refreshed_count": 5,
  "execution_time_seconds": 1.23
}
```

**限制**

- 刷新冷却时间：30 秒（防止频繁调用）
- 如果在冷却期内调用，返回 `429 Too Many Requests`

**cURL 示例**

```bash
# 刷新所有项目
curl -X POST 'http://localhost:8080/api/refresh' \
  -H 'Authorization: Bearer your-api-key'

# 刷新单个项目
curl -X POST 'http://localhost:8080/api/refresh' \
  -H 'Authorization: Bearer your-api-key' \
  -H 'Content-Type: application/json' \
  -d '{"project_name": "OpenRouter Main"}'
```

---

## 订阅管理 API

### 4. 获取订阅状态

获取所有订阅的续费提醒状态。

**请求**

```
GET /api/subscriptions
```

**响应**

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
      "need_renewal": true,
      "alert_days_before": 7
    }
  ],
  "total_count": 1,
  "need_renewal_count": 1
}
```

---

### 5. 添加订阅

添加新的订阅项目。

**请求**

```
POST /api/subscription/add
```

**请求体**

```json
{
  "name": "Netflix Premium",
  "cycle_type": "monthly",
  "renewal_day": 15,
  "alert_days_before": 3,
  "amount": 99.0,
  "currency": "CNY"
}
```

**字段验证**

| 字段 | 必填 | 类型 | 限制 |
|------|------|------|------|
| name | ✅ | string | 1-200 字符 |
| cycle_type | ✅ | enum | weekly/monthly/yearly |
| renewal_day | ✅ | int | 1-31（月度），1-7（周度），1-365（年度） |
| alert_days_before | ✅ | int | 0-365 |
| amount | ✅ | float | >= 0 |
| currency | ❌ | string | 默认 CNY，3 字符 |

**响应**

```json
{
  "status": "success",
  "message": "订阅添加成功",
  "subscription": {
    "name": "Netflix Premium",
    "renewal_date": "2024-03-15"
  }
}
```

---

### 6. 更新订阅

更新现有订阅信息。

**请求**

```
POST /api/config/subscription
```

**请求体**

```json
{
  "old_name": "Netflix Premium",
  "name": "Netflix Premium Pro",
  "amount": 129.0,
  "alert_days_before": 5
}
```

**响应**

```json
{
  "status": "success",
  "message": "订阅更新成功"
}
```

---

### 7. 删除订阅

删除订阅项目。

**请求**

```
POST /api/subscription/delete
```

**请求体**

```json
{
  "name": "Netflix Premium"
}
```

**响应**

```json
{
  "status": "success",
  "message": "订阅删除成功"
}
```

---

### 8. 标记已续费

标记订阅已手动续费。

**请求**

```
POST /api/subscription/mark_renewed
```

**请求体**

```json
{
  "name": "Netflix Premium",
  "renewed_date": "2024-02-24"  // 可选：默认今天
}
```

**响应**

```json
{
  "status": "success",
  "message": "已标记续费",
  "next_renewal_date": "2024-03-24"
}
```

---

## 历史数据 API

**注意**：历史数据 API 需要启用数据库功能（`ENABLE_DATABASE=true`）

### 9. 查询余额历史

查询指定项目的余额历史记录。

**请求**

```
GET /api/history/balance
```

**查询参数**

| 参数 | 必填 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| project_id | ❌ | string | - | 项目ID（不传则查所有） |
| provider | ❌ | string | - | Provider类型 |
| days | ❌ | int | 7 | 查询天数（1-365） |
| limit | ❌ | int | 100 | 返回记录数（1-1000） |

**响应**

```json
{
  "status": "success",
  "count": 48,
  "data": [
    {
      "id": 1234,
      "project_id": "abc123",
      "project_name": "OpenRouter Main",
      "provider": "openrouter",
      "balance": 150.75,
      "threshold": 100.0,
      "currency": "USD",
      "balance_type": "credits",
      "need_alarm": false,
      "timestamp": "2024-02-24T10:00:00Z"
    }
  ]
}
```

**cURL 示例**

```bash
# 查询指定项目最近7天历史
curl 'http://localhost:8080/api/history/balance?project_id=abc123&days=7' \
  -H 'Authorization: Bearer your-api-key'

# 查询所有 OpenRouter 项目最近30天历史
curl 'http://localhost:8080/api/history/balance?provider=openrouter&days=30' \
  -H 'Authorization: Bearer your-api-key'
```

---

### 10. 获取余额趋势分析

获取指定项目的余额变化趋势和统计信息。

**请求**

```
GET /api/history/trend/<project_id>
```

**查询参数**

- `days`（可选）：分析天数，默认 30，范围 1-365

**响应**

```json
{
  "status": "success",
  "data": {
    "project_id": "abc123",
    "project_name": "OpenRouter Main",
    "days": 30,
    "data_points": 720,
    "current_balance": 150.75,
    "min_balance": 120.00,
    "max_balance": 200.50,
    "avg_balance": 165.30,
    "change": -15.25,
    "change_percent": -9.19,
    "first_timestamp": "2024-01-25T00:00:00Z",
    "last_timestamp": "2024-02-24T10:00:00Z",
    "history": [
      {
        "timestamp": "2024-02-24T10:00:00Z",
        "balance": 150.75,
        "need_alarm": false
      }
    ]
  }
}
```

**字段说明**

| 字段 | 说明 |
|------|------|
| data_points | 数据点数量 |
| current_balance | 当前余额 |
| min_balance | 最低余额 |
| max_balance | 最高余额 |
| avg_balance | 平均余额 |
| change | 余额变化量（负数=减少） |
| change_percent | 余额变化百分比 |

**cURL 示例**

```bash
curl 'http://localhost:8080/api/history/trend/abc123?days=30' \
  -H 'Authorization: Bearer your-api-key'
```

**Python 可视化示例**

```python
import requests
import matplotlib.pyplot as plt
from datetime import datetime

response = requests.get(
    'http://localhost:8080/api/history/trend/abc123?days=30',
    headers={'Authorization': 'Bearer your-api-key'}
)
data = response.json()['data']

# 提取数据
timestamps = [datetime.fromisoformat(h['timestamp'].replace('Z', '+00:00'))
              for h in data['history']]
balances = [h['balance'] for h in data['history']]

# 绘制趋势图
plt.figure(figsize=(12, 6))
plt.plot(timestamps, balances, marker='o', linewidth=2)
plt.axhline(y=data['avg_balance'], color='r', linestyle='--', label='平均值')
plt.title(f"{data['project_name']} - 余额趋势（{data['days']}天）")
plt.xlabel('时间')
plt.ylabel('余额')
plt.legend()
plt.grid(True)
plt.show()
```

---

### 11. 查询告警历史

查询告警记录。

**请求**

```
GET /api/history/alerts
```

**查询参数**

| 参数 | 必填 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| project_id | ❌ | string | - | 项目ID |
| alert_type | ❌ | string | - | 告警类型 |
| days | ❌ | int | 7 | 查询天数 |
| limit | ❌ | int | 50 | 返回记录数 |

**响应**

```json
{
  "status": "success",
  "count": 12,
  "data": [
    {
      "id": 789,
      "project_id": "abc123",
      "project_name": "OpenRouter Main",
      "alert_type": "low_balance",
      "status": "sent",
      "message": "积分不足: 45.2 < 50.0",
      "balance_value": 45.2,
      "threshold_value": 50.0,
      "timestamp": "2024-02-24T08:00:00Z"
    }
  ]
}
```

---

### 12. 获取告警统计

获取告警频率、分布等统计信息。

**请求**

```
GET /api/history/stats
```

**查询参数**

- `days`（可选）：统计天数，默认 30

**响应**

```json
{
  "status": "success",
  "data": {
    "days": 30,
    "total_alerts": 42,
    "by_type": {
      "low_balance": 35,
      "renewal_reminder": 7
    },
    "top_projects": [
      {"project": "OpenRouter Main", "count": 15},
      {"project": "Claude API", "count": 12}
    ]
  }
}
```

---

### 13. 获取所有项目摘要

获取所有项目的最新状态快照。

**请求**

```
GET /api/history/projects
```

**响应**

```json
{
  "status": "success",
  "count": 5,
  "data": [
    {
      "id": 1001,
      "project_id": "abc123",
      "project_name": "OpenRouter Main",
      "provider": "openrouter",
      "balance": 150.75,
      "threshold": 100.0,
      "need_alarm": false,
      "timestamp": "2024-02-24T10:00:00Z"
    }
  ]
}
```

---

## 配置 API

### 14. 获取项目配置

获取所有配置的项目列表（不含敏感信息）。

**请求**

```
GET /api/config/projects
```

**响应**

```json
{
  "status": "success",
  "projects": [
    {
      "name": "OpenRouter Main",
      "provider": "openrouter",
      "threshold": 100.0,
      "type": "credits",
      "enabled": true
    }
  ]
}
```

注意：**API Key 不会返回**

---

### 15. 更新项目阈值

动态修改项目的告警阈值。

**请求**

```
POST /api/config/threshold
```

**请求体**

```json
{
  "project_name": "OpenRouter Main",
  "new_threshold": 120.0
}
```

**响应**

```json
{
  "status": "success",
  "message": "阈值已更新: 100.0 -> 120.0",
  "data": {
    "project_name": "OpenRouter Main",
    "old_threshold": 100.0,
    "new_threshold": 120.0
  }
}
```

---

## 错误处理

### 标准错误响应

所有错误遵循统一格式：

```json
{
  "status": "error",
  "message": "错误描述",
  "errors": ["详细错误1", "详细错误2"]  // 可选：字段验证错误
}
```

### HTTP 状态码

| 状态码 | 说明 | 示例 |
|--------|------|------|
| 200 | 成功 | 正常响应 |
| 400 | 请求错误 | 参数验证失败 |
| 401 | 未授权 | API Key 无效 |
| 404 | 资源不存在 | 项目不存在 |
| 429 | 请求过多 | 超出速率限制 |
| 500 | 服务器错误 | 内部异常 |
| 503 | 服务不可用 | 数据库未初始化 |

### 常见错误示例

**验证错误（400）**

```json
{
  "status": "error",
  "errors": [
    "name: 字段不能为空",
    "threshold: 必须大于 0"
  ]
}
```

**认证错误（401）**

```json
{
  "status": "error",
  "message": "未授权访问"
}
```

**速率限制（429）**

```json
{
  "status": "error",
  "message": "刷新过于频繁，请30秒后重试"
}
```

---

## 速率限制

### 全局限制

- **默认**: 100 请求/分钟（每个 IP）
- **配置**: `RATE_LIMIT=100/minute`

### 端点限制

| 端点 | 限制 |
|------|------|
| `/api/refresh` | 2 请求/分钟 + 30秒冷却 |
| `/api/subscription/*` | 20 请求/分钟 |
| `/api/history/*` | 50 请求/分钟 |

### 超出限制响应

```
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1708765200

{
  "status": "error",
  "message": "Rate limit exceeded. Try again in 60 seconds."
}
```

---

## 示例代码

### Python SDK

```python
import requests
from typing import List, Dict, Any

class BalanceAlertClient:
    """Balance Alert API 客户端"""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        })

    def get_credits(self) -> List[Dict[str, Any]]:
        """获取所有项目余额"""
        response = self.session.get(f'{self.base_url}/api/credits')
        response.raise_for_status()
        return response.json()['projects']

    def refresh(self, project_name: str = None) -> Dict[str, Any]:
        """刷新余额"""
        data = {'project_name': project_name} if project_name else {}
        response = self.session.post(f'{self.base_url}/api/refresh', json=data)
        response.raise_for_status()
        return response.json()

    def get_trend(self, project_id: str, days: int = 30) -> Dict[str, Any]:
        """获取趋势分析"""
        response = self.session.get(
            f'{self.base_url}/api/history/trend/{project_id}',
            params={'days': days}
        )
        response.raise_for_status()
        return response.json()['data']

    def add_subscription(self, name: str, cycle_type: str, renewal_day: int,
                         alert_days_before: int, amount: float = 0,
                         currency: str = 'CNY') -> Dict[str, Any]:
        """添加订阅"""
        data = {
            'name': name,
            'cycle_type': cycle_type,
            'renewal_day': renewal_day,
            'alert_days_before': alert_days_before,
            'amount': amount,
            'currency': currency
        }
        response = self.session.post(f'{self.base_url}/api/subscription/add', json=data)
        response.raise_for_status()
        return response.json()

# 使用示例
client = BalanceAlertClient('http://localhost:8080', 'your-api-key')

# 获取余额
projects = client.get_credits()
for project in projects:
    print(f"{project['name']}: {project['balance']} {project['currency']}")

# 刷新指定项目
result = client.refresh('OpenRouter Main')

# 获取趋势
trend = client.get_trend('abc123', days=30)
print(f"当前余额: {trend['current_balance']}")
print(f"30天变化: {trend['change']} ({trend['change_percent']:.2f}%)")
```

### JavaScript/Node.js

```javascript
const axios = require('axios');

class BalanceAlertClient {
  constructor(baseUrl, apiKey) {
    this.client = axios.create({
      baseURL: baseUrl,
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
      }
    });
  }

  async getCredits() {
    const response = await this.client.get('/api/credits');
    return response.data.projects;
  }

  async refresh(projectName = null) {
    const data = projectName ? { project_name: projectName } : {};
    const response = await this.client.post('/api/refresh', data);
    return response.data;
  }

  async getTrend(projectId, days = 30) {
    const response = await this.client.get(`/api/history/trend/${projectId}`, {
      params: { days }
    });
    return response.data.data;
  }

  async addSubscription(subscription) {
    const response = await this.client.post('/api/subscription/add', subscription);
    return response.data;
  }
}

// 使用示例
const client = new BalanceAlertClient('http://localhost:8080', 'your-api-key');

(async () => {
  // 获取余额
  const projects = await client.getCredits();
  projects.forEach(p => {
    console.log(`${p.name}: ${p.balance} ${p.currency}`);
  });

  // 获取趋势
  const trend = await client.getTrend('abc123', 30);
  console.log(`当前余额: ${trend.current_balance}`);
  console.log(`30天变化: ${trend.change} (${trend.change_percent.toFixed(2)}%)`);
})();
```

### cURL 速查表

```bash
# 健康检查
curl http://localhost:8080/health

# 获取余额（带认证）
curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8080/api/credits

# 刷新余额
curl -X POST \
     -H "Authorization: Bearer YOUR_API_KEY" \
     http://localhost:8080/api/refresh

# 添加订阅
curl -X POST \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Netflix",
       "cycle_type": "monthly",
       "renewal_day": 15,
       "alert_days_before": 3,
       "amount": 99.0
     }' \
     http://localhost:8080/api/subscription/add

# 查询趋势
curl -H "Authorization: Bearer YOUR_API_KEY" \
     "http://localhost:8080/api/history/trend/abc123?days=30"

# 告警统计
curl -H "Authorization: Bearer YOUR_API_KEY" \
     "http://localhost:8080/api/history/stats?days=7"
```

---

## Swagger/OpenAPI 文档

访问交互式 API 文档（如果已启用）：

```
http://localhost:8080/apidocs
```

生成 OpenAPI Spec：

```
http://localhost:8080/apispec_1.json
```

---

**最后更新**: 2024-02-24
**文档版本**: 1.0.0
