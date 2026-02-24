# PostgreSQL 数据库配置指南

本文档介绍如何将 Balance Alert 连接到外部 PostgreSQL 数据库。

## 📋 前置要求

1. PostgreSQL 数据库服务器（本地或远程）
2. 数据库用户和密码
3. 数据库名称

## 🔧 配置步骤

### 1. 安装 PostgreSQL 驱动

在项目目录下安装 `psycopg2` 驱动：

```bash
# 方式 1: 使用二进制版本（推荐，无需编译）
pip install psycopg2-binary

# 方式 2: 使用源码编译版本（生产环境推荐）
pip install psycopg2
```

**注意**: `psycopg2-binary` 适合开发和测试，`psycopg2` 适合生产环境但需要编译工具。

### 2. 修改环境变量

编辑 `.env` 文件，修改 `DATABASE_URL` 配置：

```bash
# ========================================
# 数据持久化配置
# ========================================
# 启用数据库
ENABLE_DATABASE=true

# PostgreSQL 连接字符串
DATABASE_URL=postgresql://username:password@host:port/database
```

#### 连接字符串格式说明

```
postgresql://[用户名]:[密码]@[主机]:[端口]/[数据库名]?[参数]
```

#### 示例配置

**本地 PostgreSQL:**
```bash
DATABASE_URL=postgresql://postgres:mypassword@localhost:5432/balance_alert
```

**远程 PostgreSQL:**
```bash
DATABASE_URL=postgresql://dbuser:secret123@db.example.com:5432/balance_alert
```

**带 SSL 连接:**
```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require
```

**连接池配置:**
```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname?pool_size=10&max_overflow=20
```

### 3. 创建数据库

在 PostgreSQL 中创建数据库（如果还没有）：

```sql
-- 登录 PostgreSQL
psql -U postgres

-- 创建数据库
CREATE DATABASE balance_alert;

-- 创建用户（可选）
CREATE USER balance_user WITH PASSWORD 'your_password';

-- 授予权限
GRANT ALL PRIVILEGES ON DATABASE balance_alert TO balance_user;

-- 退出
\q
```

### 4. 测试连接

运行以下命令测试数据库连接：

```bash
python3 -c "
from database.engine import get_engine, init_database
engine = get_engine()
if engine:
    print('✅ 数据库连接成功')
    print(f'数据库: {engine.url}')
    # 初始化数据库表
    if init_database():
        print('✅ 数据库表创建成功')
else:
    print('❌ 数据库连接失败')
"
```

### 5. 启动服务

```bash
python3 web_server_modular.py
```

## 🔐 常见配置参数

在 `DATABASE_URL` 后面可以添加以下参数（用 `?` 开始，`&` 分隔）：

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `sslmode` | SSL 模式 | `disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full` |
| `connect_timeout` | 连接超时（秒） | `10` |
| `application_name` | 应用名称 | `balance-alert` |
| `pool_size` | 连接池大小 | `10` |
| `max_overflow` | 最大溢出连接 | `20` |

**示例完整配置:**
```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require&connect_timeout=10&application_name=balance-alert
```

## 📊 数据库表结构

系统会自动创建以下表：

- **balance_history**: 余额历史记录
- **alert_history**: 告警历史记录
- **subscription_history**: 订阅历史记录

## 🔄 从 SQLite 迁移到 PostgreSQL

### 方法 1: 手动迁移（推荐小数据量）

1. 导出 SQLite 数据：
```bash
sqlite3 data/balance_alert.db .dump > backup.sql
```

2. 修改 SQL 语法（SQLite → PostgreSQL）
3. 导入到 PostgreSQL

### 方法 2: 使用工具迁移

使用 `pgloader` 工具：

```bash
# 安装 pgloader (macOS)
brew install pgloader

# 执行迁移
pgloader data/balance_alert.db postgresql://user:pass@host:5432/balance_alert
```

### 方法 3: 重新开始（推荐）

如果历史数据不重要，直接切换到 PostgreSQL，系统会自动创建新表。

## 🐛 常见问题

### 1. 连接被拒绝

**错误**: `could not connect to server: Connection refused`

**解决**:
- 检查 PostgreSQL 服务是否启动
- 检查防火墙设置
- 确认 `postgresql.conf` 中的 `listen_addresses` 配置

### 2. 密码认证失败

**错误**: `password authentication failed`

**解决**:
- 检查用户名和密码是否正确
- 确认 `pg_hba.conf` 允许该用户连接
- 尝试明确指定认证方法：`?auth=md5`

### 3. SSL 错误

**错误**: `SSL connection has been closed unexpectedly`

**解决**:
- 添加 `sslmode=disable` 参数（仅开发环境）
- 或配置正确的 SSL 证书

### 4. 驱动未安装

**错误**: `ModuleNotFoundError: No module named 'psycopg2'`

**解决**:
```bash
pip install psycopg2-binary
```

### 5. 权限不足

**错误**: `permission denied for schema public`

**解决**:
```sql
-- 授予 public schema 的所有权限
GRANT ALL ON SCHEMA public TO balance_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO balance_user;
```

## 🔍 连接验证

查看当前数据库连接：

```bash
# 检查环境变量
python3 -c "from database.engine import DATABASE_URL; print(f'当前配置: {DATABASE_URL}')"

# 查看表结构
psql -U your_user -d balance_alert -c "\dt"

# 查看数据
psql -U your_user -d balance_alert -c "SELECT * FROM balance_history LIMIT 5;"
```

## 📈 性能优化建议

1. **创建索引**（系统会自动创建，但可以手动优化）：
```sql
-- 在 balance_history 表上创建索引
CREATE INDEX idx_balance_project_time ON balance_history(project_id, timestamp DESC);
CREATE INDEX idx_balance_timestamp ON balance_history(timestamp);

-- 在 alert_history 表上创建索引
CREATE INDEX idx_alert_project_time ON alert_history(project_id, timestamp DESC);
```

2. **调整连接池**：
```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname?pool_size=20&max_overflow=10
```

3. **启用查询日志**（调试用）：
在 `database/engine.py` 中设置 `echo=True`

## 🔒 安全建议

1. **不要在 URL 中明文存储密码**，使用环境变量：
```bash
DB_USER=myuser
DB_PASS=mypassword
DB_HOST=localhost
DB_PORT=5432
DB_NAME=balance_alert

# 在代码中组合
DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}
```

2. **使用 SSL 连接**（生产环境）
3. **限制数据库用户权限**（最小权限原则）
4. **定期备份数据库**

## 📱 云服务提供商配置

### AWS RDS PostgreSQL

```bash
DATABASE_URL=postgresql://username:password@mydb.123456789.us-east-1.rds.amazonaws.com:5432/balance_alert?sslmode=require
```

### Google Cloud SQL

```bash
DATABASE_URL=postgresql://username:password@/balance_alert?host=/cloudsql/project:region:instance
```

### Azure Database for PostgreSQL

```bash
DATABASE_URL=postgresql://username%40servername:password@servername.postgres.database.azure.com:5432/balance_alert?sslmode=require
```

### Supabase

```bash
DATABASE_URL=postgresql://postgres:password@db.xxxxx.supabase.co:5432/postgres
```

### Railway / Render

这些平台通常会自动提供 `DATABASE_URL` 环境变量，直接使用即可。

---

**最后更新**: 2026-02-24
**维护者**: Balance Alert Team
