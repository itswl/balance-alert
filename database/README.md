# 数据持久化模块

提供 SQLite / PostgreSQL / MySQL 持久化，用于历史记录与数据库动态配置。
`ENABLE_DATABASE=true` 时应用启动会自动创建缺失的表（`init_database()`），无需手动迁移。

## 结构

```text
database/
├── engine.py      # 引擎/会话工厂单例，init_database() 建表
├── models.py      # ORM 模型
└── repository.py  # 数据访问层（含可选的敏感字段加解密）
```

## 表

| 表 | 模型 | 用途 | 写入方 |
| --- | --- | --- | --- |
| `balance_history` | `BalanceHistory` | 每次余额检查结果 | `services/monitor.py` |
| `alert_history` | `AlertHistory` | 已发送的告警（含冷却去重依据） | monitor / subscription_checker |
| `email_alert_history` | `EmailAlertHistory` | 扫描到的告警邮件（去重依据） | `services/email_scanner.py` |
| `project_config` | `ProjectConfig` | 动态项目配置 | Web API |
| `subscription_config` | `SubscriptionConfig` | 动态订阅配置 | Web API |
| `email_config` | `EmailConfig` | 动态邮箱配置 | Web API |

## Repository

- `ConfigRepository`：动态配置的读写（`get_all_projects/subscriptions/emails`、`upsert_*`、`delete_*`）。
  设置 `CONFIG_ENCRYPTION_KEY` 后，`api_key` / 邮箱 `password` 自动加密存储（`enc:v1:` 前缀）。
- `BalanceRepository`：余额历史写入与查询（`get_balance_history`、`get_balance_trend`、`get_all_projects_summary`）。
- `AlertRepository`：告警历史写入、冷却判断（`has_recent_alert`）与统计。
- `EmailRepository`：邮件告警记录与去重（`has_recent_email_alert`）。

默认所有数据库异常被记录日志并返回兜底值；排障时设 `STRICT_DATABASE_ERRORS=true` 让异常向上抛出。
数据库连接与开关在模块导入时定型（`DATABASE_URL` / `ENABLE_DATABASE`），修改后需重启进程。
