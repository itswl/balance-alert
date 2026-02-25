# MySQL 快速入门

## 🚀 三步配置 MySQL

### 方法一：使用配置脚本（推荐）

```bash
# 1. 安装依赖
pip install pymysql cryptography

# 2. 运行配置向导
./scripts/setup_mysql.sh

# 3. 启动服务
python3 web_server_modular.py
```

### 方法二：手动配置

```bash
# 1. 安装 MySQL 驱动
pip install pymysql cryptography

# 2. 编辑 .env 文件
nano .env

# 修改以下配置（注意前缀是 mysql+pymysql）:
ENABLE_DATABASE=true
DATABASE_URL=mysql+pymysql://username:password@host:port/database?charset=utf8mb4

# 3. 启动服务
python3 web_server_modular.py
```

## 📝 常见场景配置

### 本地 MySQL

```bash
# 1. 创建数据库
mysql -u root -p
```

```sql
CREATE DATABASE balance_alert CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'balance_user'@'%' IDENTIFIED BY 'yourpassword';
GRANT ALL PRIVILEGES ON balance_alert.* TO 'balance_user'@'%';
FLUSH PRIVILEGES;
EXIT;
```

```bash
# 2. 配置 .env
DATABASE_URL=mysql+pymysql://balance_user:yourpassword@localhost:3306/balance_alert?charset=utf8mb4
```

### Docker MySQL

```bash
# 1. 启动 MySQL 容器
docker run -d \
  --name mysql \
  -e MYSQL_ROOT_PASSWORD=rootpass \
  -e MYSQL_DATABASE=balance_alert \
  -e MYSQL_USER=balance_user \
  -e MYSQL_PASSWORD=userpass \
  -p 3306:3306 \
  mysql:8.0 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci

# 2. 配置 .env
DATABASE_URL=mysql+pymysql://balance_user:userpass@localhost:3306/balance_alert?charset=utf8mb4
```

### 云服务 MySQL

#### 阿里云 RDS

```bash
# 在阿里云 RDS 控制台创建 MySQL 实例后
DATABASE_URL=mysql+pymysql://username:password@rm-xxxxx.mysql.rds.aliyuncs.com:3306/balance_alert?charset=utf8mb4
```

#### 腾讯云 CDB

```bash
DATABASE_URL=mysql+pymysql://username:password@cdb-xxxxx.sql.tencentcdb.com:3306/balance_alert?charset=utf8mb4
```

#### AWS RDS

```bash
DATABASE_URL=mysql+pymysql://admin:password@mydb.123456789.us-east-1.rds.amazonaws.com:3306/balance_alert?charset=utf8mb4
```

## ✅ 测试连接

```bash
# 方法 1: 使用测试脚本
python3 scripts/test_database.py

# 方法 2: 使用 Python 直接测试
python3 << 'EOF'
from database.engine import get_engine, init_database
engine = get_engine()
if engine:
    print('✅ 连接成功')
    print(f'数据库: {engine.url}')
    init_database()
else:
    print('❌ 连接失败')
EOF

# 方法 3: MySQL 命令行
mysql -h localhost -u balance_user -p balance_alert
```

预期输出：
```
============================================================
数据库连接测试
============================================================

📋 配置信息:
  ENABLE_DATABASE: True
  DATABASE_URL: mysql+pymysql://...

🔌 测试数据库连接...
✅ 数据库连接成功!
  MySQL 版本: MySQL 8.0.x

🏗️  初始化数据库表...
✅ 数据库表初始化成功!

📊 数据库表:
  - balance_history
  - alert_history
  - subscription_history

🎉 数据库测试完成!
```

## 🔧 故障排除

### 驱动未安装

```bash
❌ ModuleNotFoundError: No module named 'pymysql'

# 解决:
pip install pymysql cryptography
```

### 连接被拒绝

```bash
❌ Can't connect to MySQL server

# 检查 MySQL 是否运行:
# Linux:
sudo systemctl status mysql

# macOS:
brew services list | grep mysql

# Docker:
docker ps | grep mysql
```

### 认证失败

```bash
❌ Access denied for user

# 解决:
# 1. 检查用户名密码
# 2. 确认用户权限
mysql -u root -p
```

```sql
-- 查看用户权限
SHOW GRANTS FOR 'balance_user'@'%';

-- 授予权限
GRANT ALL PRIVILEGES ON balance_alert.* TO 'balance_user'@'%';
FLUSH PRIVILEGES;
```

### 数据库不存在

```bash
❌ Unknown database 'balance_alert'

# 解决:
mysql -u root -p
```

```sql
CREATE DATABASE balance_alert
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### 字符集问题

```bash
# 确保使用 utf8mb4
DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?charset=utf8mb4

# 检查数据库字符集
mysql -u user -p -e "SHOW VARIABLES LIKE 'character_set%';"
```

## 📊 性能优化

### 创建索引

```sql
-- 连接到数据库
mysql -u balance_user -p balance_alert

-- 创建索引
CREATE INDEX idx_balance_project_time ON balance_history(project_id, timestamp DESC);
CREATE INDEX idx_balance_timestamp ON balance_history(timestamp);
CREATE INDEX idx_alert_project_time ON alert_history(project_id, timestamp DESC);
```

### 调整连接池

```bash
# 在 DATABASE_URL 中添加参数
DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?charset=utf8mb4&pool_size=10&max_overflow=20
```

## 🔄 从 SQLite 迁移

如果你之前使用 SQLite，可以这样迁移：

```bash
# 1. 配置 MySQL
./scripts/setup_mysql.sh

# 2. 启动服务（会自动创建表）
python3 web_server_modular.py

# 3. (可选) 导入历史数据
# 如果需要保留历史数据，需要手动迁移或使用迁移脚本
```

## 📚 更多信息

- 详细文档: [MYSQL_SETUP.md](./MYSQL_SETUP.md)
- PostgreSQL: [POSTGRESQL_SETUP.md](./POSTGRESQL_SETUP.md)
- 数据库文档: [../database/README.md](../database/README.md)
- 项目主页: [../README.md](../README.md)

## 💡 常见问题

**Q: MySQL 和 PostgreSQL 哪个更好？**
A: 都很好！MySQL 生态更丰富，PostgreSQL 功能更强大。本项目两者都支持。

**Q: 为什么连接字符串前缀是 `mysql+pymysql` 而不是 `mysql`？**
A: `mysql+pymysql://` 指定使用 PyMySQL 驱动。这是 SQLAlchemy 的标准格式。

**Q: 必须使用 utf8mb4 吗？**
A: 强烈推荐！utf8mb4 支持完整的 Unicode（包括 Emoji），而 MySQL 的 utf8 只支持部分。

**Q: 可以使用 MySQL 5.7 吗？**
A: 可以，但推荐 MySQL 8.0+，性能和功能更好。

---

**快速链接**:
- 🛠️ 配置脚本: `./scripts/setup_mysql.sh`
- 🧪 测试脚本: `./scripts/test_database.py`
- 📖 完整文档: `docs/MYSQL_SETUP.md`
