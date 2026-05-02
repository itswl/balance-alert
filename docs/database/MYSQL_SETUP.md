# MySQL 数据库配置指南

本文档介绍如何将 Balance Alert 连接到 MySQL 数据库。

## 📋 前置要求

1. MySQL 数据库服务器（5.7+ 或 8.0+）
2. 数据库用户和密码
3. 数据库名称

## 🔧 配置步骤

### 1. 安装 MySQL 驱动

在项目目录下安装 `pymysql` 驱动：

```bash
# 安装 MySQL 驱动和依赖
pip install pymysql cryptography

# 或安装所有依赖
pip install -r requirements.txt
```

**注意**:
- `pymysql` 是纯 Python 实现，无需编译
- `cryptography` 用于支持 SSL 连接

### 2. 修改环境变量

编辑 `.env` 文件，修改 `DATABASE_URL` 配置：

```bash
# ========================================
# 数据持久化配置
# ========================================
# 启用数据库
ENABLE_DATABASE=true

# MySQL 连接字符串
DATABASE_URL=mysql+pymysql://username:password@host:port/database
```

#### 连接字符串格式说明

```
mysql+pymysql://[用户名]:[密码]@[主机]:[端口]/[数据库名]?[参数]
```

**重要**: 必须使用 `mysql+pymysql://` 前缀（不是 `mysql://`）

#### 示例配置

**本地 MySQL:**
```bash
DATABASE_URL=mysql+pymysql://root:mypassword@localhost:3306/balance_alert
```

**远程 MySQL:**
```bash
DATABASE_URL=mysql+pymysql://dbuser:secret123@db.example.com:3306/balance_alert
```

**带 SSL 连接:**
```bash
DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?ssl=true
```

**带字符集配置:**
```bash
DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?charset=utf8mb4
```

**完整配置示例:**
```bash
DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?charset=utf8mb4&ssl=true
```

### 3. 创建数据库

在 MySQL 中创建数据库（如果还没有）：

```sql
-- 登录 MySQL
mysql -u root -p

-- 创建数据库（使用 utf8mb4 字符集）
CREATE DATABASE balance_alert CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建用户（可选）
CREATE USER 'balance_user'@'%' IDENTIFIED BY 'your_password';

-- 授予权限
GRANT ALL PRIVILEGES ON balance_alert.* TO 'balance_user'@'%';
FLUSH PRIVILEGES;

-- 退出
EXIT;
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

或使用测试脚本：

```bash
python3 scripts/test_database.py
```

### 5. 启动服务

```bash
python3 main.py
```

## 🔐 常见配置参数

在 `DATABASE_URL` 后面可以添加以下参数（用 `?` 开始，`&` 分隔）：

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `charset` | 字符集 | `utf8mb4` (推荐) |
| `ssl` | 启用 SSL | `true`, `false` |
| `ssl_ca` | CA 证书路径 | `/path/to/ca.pem` |
| `ssl_cert` | 客户端证书路径 | `/path/to/client-cert.pem` |
| `ssl_key` | 客户端密钥路径 | `/path/to/client-key.pem` |
| `connect_timeout` | 连接超时（秒） | `10` |
| `read_timeout` | 读取超时（秒） | `30` |
| `write_timeout` | 写入超时（秒） | `30` |

**示例完整配置:**
```bash
DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?charset=utf8mb4&ssl=true&connect_timeout=10
```

## 📊 数据库表结构

系统会自动创建以下表：

- **balance_history**: 余额历史记录
- **alert_history**: 告警历史记录
- **subscription_history**: 订阅历史记录

## 🔄 从 SQLite 迁移到 MySQL

### 方法 1: 使用 SQLAlchemy 迁移脚本

创建迁移脚本：

```python
# migrate_to_mysql.py
import os
from sqlalchemy import create_engine, MetaData
from database.models import Base

# 源数据库 (SQLite)
sqlite_url = 'sqlite:///./data/balance_alert.db'
# 目标数据库 (MySQL)
mysql_url = 'mysql+pymysql://user:pass@localhost:3306/balance_alert'

sqlite_engine = create_engine(sqlite_url)
mysql_engine = create_engine(mysql_url)

# 创建 MySQL 表结构
Base.metadata.create_all(mysql_engine)

# 迁移数据
from sqlalchemy.orm import sessionmaker

SQLiteSession = sessionmaker(bind=sqlite_engine)
MySQLSession = sessionmaker(bind=mysql_engine)

from database.models import BalanceHistory, AlertHistory, SubscriptionHistory

sqlite_session = SQLiteSession()
mysql_session = MySQLSession()

# 迁移 balance_history
for record in sqlite_session.query(BalanceHistory).all():
    new_record = BalanceHistory(
        project_id=record.project_id,
        project_name=record.project_name,
        provider=record.provider,
        balance=record.balance,
        threshold=record.threshold,
        currency=record.currency,
        balance_type=record.balance_type,
        need_alarm=record.need_alarm,
        timestamp=record.timestamp
    )
    mysql_session.add(new_record)

mysql_session.commit()
print('✅ 迁移完成')
```

### 方法 2: 导出 SQL 并手动导入

```bash
# 1. 从 SQLite 导出数据
sqlite3 data/balance_alert.db .dump > backup.sql

# 2. 编辑 SQL 文件，调整语法差异
# 3. 导入到 MySQL
mysql -u user -p balance_alert < backup.sql
```

### 方法 3: 重新开始（推荐）

如果历史数据不重要，直接切换到 MySQL，系统会自动创建新表。

## 🐛 常见问题

### 1. 连接被拒绝

**错误**: `Can't connect to MySQL server`

**解决**:
- 检查 MySQL 服务是否启动
  ```bash
  # Linux
  sudo systemctl status mysql
  # macOS
  brew services list | grep mysql
  ```
- 检查防火墙设置
- 确认 MySQL 配置允许远程连接（`bind-address` 设置）

### 2. 密码认证失败

**错误**: `Access denied for user`

**解决**:
- 检查用户名和密码是否正确
- 确认用户有访问权限
  ```sql
  SHOW GRANTS FOR 'balance_user'@'%';
  ```
- MySQL 8.0 可能需要修改认证插件：
  ```sql
  ALTER USER 'balance_user'@'%' IDENTIFIED WITH mysql_native_password BY 'your_password';
  ```

### 3. 字符集问题

**错误**: 中文显示乱码

**解决**:
```bash
# 确保使用 utf8mb4
DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?charset=utf8mb4

# 检查数据库字符集
SHOW VARIABLES LIKE 'character_set%';

# 修改数据库字符集
ALTER DATABASE balance_alert CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. 驱动未安装

**错误**: `ModuleNotFoundError: No module named 'pymysql'`

**解决**:
```bash
pip install pymysql cryptography
```

### 5. SSL 连接错误

**错误**: `SSL connection error`

**解决**:
```bash
# 禁用 SSL（仅开发环境）
DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?ssl=false

# 或配置 SSL 证书
DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?ssl_ca=/path/to/ca.pem
```

### 6. 权限不足

**错误**: `Access denied; you need (at least one of) the CREATE privilege(s)`

**解决**:
```sql
-- 授予所有权限
GRANT ALL PRIVILEGES ON balance_alert.* TO 'balance_user'@'%';
FLUSH PRIVILEGES;
```

## 🔍 连接验证

查看当前数据库连接：

```bash
# 检查环境变量
python3 -c "from database.engine import DATABASE_URL; print(f'当前配置: {DATABASE_URL}')"

# MySQL 命令行连接测试
mysql -h host -u user -p -D balance_alert

# 查看表结构
mysql -u user -p balance_alert -e "SHOW TABLES;"

# 查看数据
mysql -u user -p balance_alert -e "SELECT * FROM balance_history LIMIT 5;"
```

## 📈 性能优化建议

### 1. 创建索引

虽然系统会自动创建索引，但可以手动优化：

```sql
-- 在 balance_history 表上创建索引
CREATE INDEX idx_balance_project_time ON balance_history(project_id, timestamp DESC);
CREATE INDEX idx_balance_timestamp ON balance_history(timestamp);
CREATE INDEX idx_balance_provider ON balance_history(provider);

-- 在 alert_history 表上创建索引
CREATE INDEX idx_alert_project_time ON alert_history(project_id, timestamp DESC);
CREATE INDEX idx_alert_type ON alert_history(alert_type);
```

### 2. 调整 MySQL 配置

编辑 `my.cnf` 或 `my.ini`：

```ini
[mysqld]
# 字符集
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

# 连接池
max_connections = 200

# InnoDB 缓冲池（根据内存调整）
innodb_buffer_pool_size = 1G

# 查询缓存
query_cache_size = 64M
query_cache_type = 1

# 慢查询日志
slow_query_log = 1
long_query_time = 2
```

### 3. 连接池配置

在代码中已经配置了连接池（`database/engine.py`），可以通过环境变量调整：

```bash
# 在 DATABASE_URL 中添加参数
DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?charset=utf8mb4&pool_size=10&max_overflow=20
```

### 4. 启用查询日志（调试用）

在 `database/engine.py` 中设置 `echo=True`

## 🔒 安全建议

1. **使用强密码**
   ```sql
   -- 创建复杂密码
   CREATE USER 'balance_user'@'%' IDENTIFIED BY 'C0mpl3x!P@ssw0rd';
   ```

2. **限制访问 IP**
   ```sql
   -- 只允许特定 IP
   CREATE USER 'balance_user'@'192.168.1.100' IDENTIFIED BY 'password';
   GRANT ALL PRIVILEGES ON balance_alert.* TO 'balance_user'@'192.168.1.100';
   ```

3. **使用 SSL 连接**（生产环境）
   ```bash
   DATABASE_URL=mysql+pymysql://user:pass@host:3306/dbname?ssl=true&ssl_ca=/path/to/ca.pem
   ```

4. **最小权限原则**
   ```sql
   -- 只授予必要的权限
   GRANT SELECT, INSERT, UPDATE, DELETE ON balance_alert.* TO 'balance_user'@'%';
   ```

5. **定期备份数据库**
   ```bash
   # 备份数据库
   mysqldump -u user -p balance_alert > backup_$(date +%Y%m%d).sql

   # 备份带压缩
   mysqldump -u user -p balance_alert | gzip > backup_$(date +%Y%m%d).sql.gz
   ```

6. **不要在 URL 中明文存储密码**
   ```bash
   # 使用环境变量
   DB_USER=myuser
   DB_PASS=mypassword
   DB_HOST=localhost
   DB_PORT=3306
   DB_NAME=balance_alert

   # 在应用中组合
   DATABASE_URL=mysql+pymysql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}
   ```

## 📱 云服务提供商配置

### AWS RDS MySQL

```bash
DATABASE_URL=mysql+pymysql://admin:password@mydb.123456789.us-east-1.rds.amazonaws.com:3306/balance_alert?charset=utf8mb4
```

### Google Cloud SQL

```bash
# 使用 Unix Socket
DATABASE_URL=mysql+pymysql://user:pass@/balance_alert?unix_socket=/cloudsql/project:region:instance&charset=utf8mb4

# 使用公共 IP
DATABASE_URL=mysql+pymysql://user:pass@1.2.3.4:3306/balance_alert?charset=utf8mb4
```

### Azure Database for MySQL

```bash
DATABASE_URL=mysql+pymysql://username%40servername:password@servername.mysql.database.azure.com:3306/balance_alert?ssl=true&charset=utf8mb4
```

### 腾讯云 CDB

```bash
DATABASE_URL=mysql+pymysql://user:pass@cdb-xxxxx.sql.tencentcdb.com:3306/balance_alert?charset=utf8mb4
```

### 阿里云 RDS

```bash
DATABASE_URL=mysql+pymysql://user:pass@rm-xxxxx.mysql.rds.aliyuncs.com:3306/balance_alert?charset=utf8mb4
```

### PlanetScale (Serverless MySQL)

```bash
DATABASE_URL=mysql+pymysql://user:pass@aws.connect.psdb.cloud/balance_alert?ssl=true&charset=utf8mb4
```

## 🐳 Docker 部署 MySQL

### 快速启动 MySQL 容器

```bash
docker run -d \
  --name mysql \
  -e MYSQL_ROOT_PASSWORD=rootpassword \
  -e MYSQL_DATABASE=balance_alert \
  -e MYSQL_USER=balance_user \
  -e MYSQL_PASSWORD=userpassword \
  -p 3306:3306 \
  -v mysql_data:/var/lib/mysql \
  mysql:8.0 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci
```

### 连接到容器中的 MySQL

```bash
# 配置 .env
DATABASE_URL=mysql+pymysql://balance_user:userpassword@localhost:3306/balance_alert?charset=utf8mb4
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: rootpassword
      MYSQL_DATABASE: balance_alert
      MYSQL_USER: balance_user
      MYSQL_PASSWORD: userpassword
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    command: --character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci

  app:
    build: .
    environment:
      DATABASE_URL: mysql+pymysql://balance_user:userpassword@mysql:3306/balance_alert?charset=utf8mb4
    depends_on:
      - mysql

volumes:
  mysql_data:
```

## 🔄 MySQL vs PostgreSQL vs SQLite

| 特性 | SQLite | MySQL | PostgreSQL |
|------|--------|-------|------------|
| **安装复杂度** | ⭐⭐⭐⭐⭐ 无需安装 | ⭐⭐⭐ 中等 | ⭐⭐⭐ 中等 |
| **性能** | ⭐⭐⭐ 小规模 | ⭐⭐⭐⭐ 中大规模 | ⭐⭐⭐⭐⭐ 大规模 |
| **并发支持** | ⭐⭐ 单写入 | ⭐⭐⭐⭐ 高并发 | ⭐⭐⭐⭐⭐ 非常高 |
| **高可用** | ❌ 不支持 | ⭐⭐⭐⭐ 支持 | ⭐⭐⭐⭐⭐ 优秀 |
| **生态系统** | ⭐⭐⭐ 基础 | ⭐⭐⭐⭐⭐ 丰富 | ⭐⭐⭐⭐ 丰富 |
| **云服务** | ❌ 无 | ⭐⭐⭐⭐⭐ 广泛 | ⭐⭐⭐⭐ 广泛 |
| **适用场景** | 单机、开发 | Web 应用 | 复杂查询、分析 |

**推荐选择**：
- 🔹 **开发/测试**: SQLite（默认）
- 🔹 **中小型生产**: MySQL
- 🔹 **大型生产/复杂查询**: PostgreSQL

---

**最后更新**: 2026-02-24
**维护者**: Balance Alert Team
