# PostgreSQL 快速入门

## 🚀 三步配置 PostgreSQL

### 方法一：使用配置脚本（推荐）

```bash
# 1. 安装依赖
pip install psycopg2-binary

# 2. 运行配置向导
./scripts/setup_postgresql.sh

# 3. 启动服务
python3 web_server_modular.py
```

### 方法二：手动配置

```bash
# 1. 安装 PostgreSQL 驱动
pip install psycopg2-binary

# 2. 编辑 .env 文件
nano .env

# 修改以下配置:
ENABLE_DATABASE=true
DATABASE_URL=postgresql://username:password@host:port/database

# 3. 启动服务
python3 web_server_modular.py
```

## 📝 常见场景配置

### 本地 PostgreSQL

```bash
# 1. 创建数据库
createdb balance_alert

# 2. 配置 .env
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/balance_alert
```

### Docker PostgreSQL

```bash
# 1. 启动 PostgreSQL 容器
docker run -d \
  --name postgres \
  -e POSTGRES_DB=balance_alert \
  -e POSTGRES_USER=balance_user \
  -e POSTGRES_PASSWORD=yourpassword \
  -p 5432:5432 \
  postgres:15

# 2. 配置 .env
DATABASE_URL=postgresql://balance_user:yourpassword@localhost:5432/balance_alert
```

### Supabase (免费云数据库)

```bash
# 1. 在 Supabase 创建项目
# 2. 获取连接字符串 (Settings -> Database -> Connection string -> URI)
# 3. 配置 .env
DATABASE_URL=postgresql://postgres.xxx:password@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
```

### Railway (免费云数据库)

```bash
# 1. 在 Railway 创建 PostgreSQL 服务
# 2. 复制 DATABASE_URL
# 3. 粘贴到 .env
DATABASE_URL=postgresql://postgres:password@containers-us-west-xxx.railway.app:6789/railway
```

## ✅ 测试连接

```bash
# 测试数据库连接和初始化
python3 scripts/test_database.py
```

预期输出：
```
============================================================
数据库连接测试
============================================================

📋 配置信息:
  ENABLE_DATABASE: True
  DATABASE_URL: postgresql://...

🔌 测试数据库连接...
✅ 数据库连接成功!
  PostgreSQL 版本: PostgreSQL 15.x

🏗️  初始化数据库表...
✅ 数据库表初始化成功!

📊 数据库表:
  - balance_history
  - alert_history
  - subscription_history

🎉 数据库测试完成!
```

## 🔧 故障排除

### 连接失败

```bash
# 检查 PostgreSQL 是否运行
pg_isready

# 检查配置
python3 -c "from database.engine import DATABASE_URL; print(DATABASE_URL)"

# 测试连接
psql -h localhost -U your_user -d balance_alert
```

### 驱动未安装

```bash
❌ ModuleNotFoundError: No module named 'psycopg2'

# 解决方案:
pip install psycopg2-binary
```

### 权限问题

```sql
-- 授予必要权限
GRANT ALL PRIVILEGES ON DATABASE balance_alert TO your_user;
GRANT ALL ON SCHEMA public TO your_user;
```

## 📚 更多信息

- 详细文档: [POSTGRESQL_SETUP.md](./POSTGRESQL_SETUP.md)
- 数据库文档: [DATABASE.md](../database/README.md)
- 项目文档: [README.md](../README.md)
