# 数据持久化模块

本模块提供 SQLite/PostgreSQL/MySQL 数据持久化功能，用于存储余额历史、告警记录和订阅历史。

## 功能特性

- **余额历史记录**：自动保存每次余额检查结果
- **告警历史记录**：记录所有发送的告警
- **订阅历史记录**：跟踪订阅续费提醒
- **趋势分析**：提供余额变化趋势分析
- **统计报表**：告警统计、项目摘要等

## 快速开始

### 1. 配置数据库

在 `.env` 文件中配置：

```bash
# 启用数据库持久化
ENABLE_DATABASE=true

# SQLite（默认，无需额外配置）
DATABASE_URL=sqlite:///./data/balance_alert.db

# PostgreSQL
# DATABASE_URL=postgresql://username:password@localhost:5432/balance_alert

# MySQL
# DATABASE_URL=mysql://username:password@localhost:3306/balance_alert
```

### 2. 初始化数据库

数据库会在 Web 服务器启动时自动初始化，或手动运行：

```python
from database import init_database

if init_database():
    print("✅ 数据库初始化成功")
```

### 3. 使用示例

#### 保存余额记录

```python
from database.repository import BalanceRepository

BalanceRepository.save_balance_record(
    project_id="project-123",
    project_name="OpenRouter API",
    provider="openrouter",
    balance=150.5,
    threshold=100.0,
    currency="USD",
    balance_type="credits",
    need_alarm=False
)
```

#### 查询余额历史

```python
# 查询最近7天的历史
history = BalanceRepository.get_balance_history(
    project_id="project-123",
    days=7,
    limit=100
)

for record in history:
    print(f"{record['timestamp']}: {record['balance']} {record['currency']}")
```

#### 获取趋势分析

```python
trend = BalanceRepository.get_balance_trend("project-123", days=30)

print(f"当前余额: {trend['current_balance']}")
print(f"最低余额: {trend['min_balance']}")
print(f"最高余额: {trend['max_balance']}")
print(f"平均余额: {trend['avg_balance']}")
print(f"变化: {trend['change']} ({trend['change_percent']:.2f}%)")
```

## API 端点

Web 服务器提供了以下历史数据查询接口：

### 查询余额历史

```bash
GET /api/history/balance?project_id=xxx&days=7&limit=100
```

**查询参数：**
- `project_id`（可选）：项目ID
- `provider`（可选）：Provider类型
- `days`（可选）：查询天数，默认7
- `limit`（可选）：返回记录数，默认100

### 获取余额趋势

```bash
GET /api/history/trend/<project_id>?days=30
```

**路径参数：**
- `project_id`：项目唯一标识

**查询参数：**
- `days`（可选）：分析天数，默认30

**返回示例：**

```json
{
  "status": "success",
  "data": {
    "project_id": "abc123",
    "project_name": "OpenRouter API",
    "days": 30,
    "data_points": 720,
    "current_balance": 150.0,
    "min_balance": 120.0,
    "max_balance": 200.0,
    "avg_balance": 165.5,
    "change": -15.0,
    "change_percent": -9.09,
    "first_timestamp": "2024-01-25T00:00:00",
    "last_timestamp": "2024-02-24T00:00:00",
    "history": [
      {
        "timestamp": "2024-02-24T00:00:00",
        "balance": 150.0,
        "need_alarm": false
      }
    ]
  }
}
```

### 查询告警历史

```bash
GET /api/history/alerts?project_id=xxx&days=7&limit=50
```

**查询参数：**
- `project_id`（可选）：项目ID
- `alert_type`（可选）：告警类型
- `days`（可选）：查询天数，默认7
- `limit`（可选）：返回记录数，默认50

### 获取告警统计

```bash
GET /api/history/stats?days=30
```

**查询参数：**
- `days`（可选）：统计天数，默认30

**返回示例：**

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
      {"project": "Project A", "count": 15},
      {"project": "Project B", "count": 12}
    ]
  }
}
```

### 获取项目摘要

```bash
GET /api/history/projects
```

返回所有项目的最新状态。

## 数据模型

### BalanceHistory（余额历史）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| project_id | String(200) | 项目唯一标识 |
| project_name | String(200) | 项目名称 |
| provider | String(50) | Provider类型 |
| balance | Float | 余额或积分数量 |
| threshold | Float | 告警阈值 |
| currency | String(10) | 货币单位 |
| balance_type | String(20) | 类型：balance/credits |
| need_alarm | Boolean | 是否需要告警 |
| timestamp | DateTime | 记录时间 |

**索引：**
- `idx_project_time` (project_id, timestamp)
- `idx_provider_time` (provider, timestamp)

### AlertHistory（告警历史）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| project_id | String(200) | 项目唯一标识 |
| project_name | String(200) | 项目名称 |
| alert_type | String(50) | 告警类型 |
| status | String(20) | 发送状态 |
| message | Text | 告警消息 |
| balance_value | Float | 触发告警时的余额 |
| threshold_value | Float | 阈值 |
| timestamp | DateTime | 告警时间 |

**索引：**
- `idx_project_type_time` (project_id, alert_type, timestamp)

### SubscriptionHistory（订阅历史）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| subscription_id | String(200) | 订阅唯一标识 |
| subscription_name | String(200) | 订阅名称 |
| cycle_type | String(20) | 周期类型 |
| days_until_renewal | Integer | 距离续费天数 |
| amount | Float | 订阅金额 |
| currency | String(10) | 货币 |
| need_renewal | Boolean | 是否需要续费 |
| timestamp | DateTime | 记录时间 |

**索引：**
- `idx_subscription_time` (subscription_id, timestamp)

## 数据库迁移

使用 Alembic 管理数据库版本：

```bash
# 查看当前版本
alembic current

# 升级到最新版本
alembic upgrade head

# 创建新迁移
alembic revision --autogenerate -m "描述"

# 回滚到上一版本
alembic downgrade -1
```

## 禁用数据库

如果不需要数据持久化功能，可以在 `.env` 中设置：

```bash
ENABLE_DATABASE=false
```

此时监控功能仍正常工作，只是不保存历史数据。

## 性能优化

1. **索引优化**：已为常用查询字段添加索引
2. **连接池**：SQLAlchemy 自动管理连接池
3. **批量插入**：Repository 支持批量操作
4. **数据清理**：建议定期清理旧数据（可配置保留期限）

## 故障排查

### 数据库文件权限问题

```bash
# 确保 data 目录存在且可写
mkdir -p ./data
chmod 755 ./data
```

### 查看数据库日志

```python
from database.engine import get_engine

# 启用 SQL 日志
engine = get_engine()
engine.echo = True
```

### 重建数据库

```bash
# 删除现有数据库（⚠️ 数据会丢失）
rm ./data/balance_alert.db

# 重新初始化
python -c "from database import init_database; init_database()"
```
