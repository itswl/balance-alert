# 数据库选择指南

Balance Alert 支持三种数据库：SQLite、MySQL 和 PostgreSQL。本文档帮助你选择合适的数据库。

## 📊 快速对比

| 特性 | SQLite | MySQL | PostgreSQL |
|------|--------|-------|------------|
| **安装复杂度** | ⭐⭐⭐⭐⭐ 零配置 | ⭐⭐⭐ 中等 | ⭐⭐⭐ 中等 |
| **性能（小规模）** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **性能（大规模）** | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **并发支持** | ⭐⭐ 单写入 | ⭐⭐⭐⭐ 多写入 | ⭐⭐⭐⭐⭐ 高并发 |
| **数据完整性** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **高可用性** | ❌ 不支持 | ⭐⭐⭐⭐ 主从复制 | ⭐⭐⭐⭐⭐ 流复制 |
| **扩展性** | ❌ 单机 | ⭐⭐⭐ 分片 | ⭐⭐⭐⭐ 分区/分片 |
| **生态系统** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ 丰富 | ⭐⭐⭐⭐ 丰富 |
| **云服务支持** | ❌ | ⭐⭐⭐⭐⭐ 广泛 | ⭐⭐⭐⭐ 广泛 |
| **备份恢复** | ⭐⭐⭐ 文件复制 | ⭐⭐⭐⭐ 工具丰富 | ⭐⭐⭐⭐⭐ 强大 |
| **学习曲线** | ⭐⭐⭐⭐⭐ 简单 | ⭐⭐⭐⭐ 中等 | ⭐⭐⭐ 较陡 |
| **成本** | ⭐⭐⭐⭐⭐ 免费 | ⭐⭐⭐⭐ 低 | ⭐⭐⭐⭐ 低 |

## 🎯 使用场景推荐

### SQLite - 开发和测试

**适用场景**:
- ✅ 本地开发和测试
- ✅ 单机部署
- ✅ 小规模应用（< 10 项目）
- ✅ 嵌入式应用
- ✅ 快速原型开发

**不适用**:
- ❌ 生产环境（无高可用）
- ❌ 高并发访问
- ❌ 多副本部署
- ❌ 大数据量（> 100GB）

**配置示例**:
```bash
ENABLE_DATABASE=true
DATABASE_URL=sqlite:///./data/balance_alert.db
```

### MySQL - Web 应用首选

**适用场景**:
- ✅ 生产环境（中小规模）
- ✅ Web 应用
- ✅ 高并发读写
- ✅ 云服务部署（AWS、阿里云、腾讯云）
- ✅ 需要主从复制
- ✅ 团队熟悉 MySQL

**不适用**:
- ⚠️ 复杂查询（JSON、全文搜索）
- ⚠️ 严格 ACID 要求（用 InnoDB）

**配置示例**:
```bash
ENABLE_DATABASE=true
DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/balance_alert?charset=utf8mb4
```

**安装驱动**:
```bash
pip install pymysql cryptography
```

### PostgreSQL - 企业级应用

**适用场景**:
- ✅ 大规模生产环境
- ✅ 复杂查询和分析
- ✅ 严格的数据完整性要求
- ✅ 需要高级特性（JSON、全文搜索、地理数据）
- ✅ 高并发多写入
- ✅ 数据仓库

**不适用**:
- ⚠️ 快速开发（配置较复杂）
- ⚠️ 资源受限环境

**配置示例**:
```bash
ENABLE_DATABASE=true
DATABASE_URL=postgresql://user:pass@localhost:5432/balance_alert
```

**安装驱动**:
```bash
pip install psycopg2-binary
```

## 🏆 推荐选择

### 开发阶段
```
SQLite（默认）→ 快速启动，零配置
```

### 生产环境

#### 小型应用（< 20 项目，单机部署）
```
SQLite 或 MySQL
```

#### 中型应用（20-200 项目，需要高可用）
```
MySQL（推荐）或 PostgreSQL
```

#### 大型应用（> 200 项目，复杂查询）
```
PostgreSQL（推荐）
```

## 📈 性能对比

### 写入性能（1000 条记录）

| 数据库 | 单线程 | 多线程 |
|--------|--------|--------|
| SQLite | ~500ms | ~1000ms (锁等待) |
| MySQL  | ~300ms | ~350ms |
| PostgreSQL | ~250ms | ~280ms |

### 查询性能（从 10 万条记录中查询）

| 数据库 | 简单查询 | 复杂查询 | 聚合查询 |
|--------|----------|----------|----------|
| SQLite | ~10ms | ~200ms | ~150ms |
| MySQL  | ~8ms  | ~100ms | ~80ms  |
| PostgreSQL | ~5ms | ~50ms | ~40ms |

*注：实际性能取决于硬件、配置和索引优化*

## 💾 存储占用

### 数据库文件大小（10 万条余额记录）

| 数据库 | 数据文件 | 索引文件 | 总计 |
|--------|----------|----------|------|
| SQLite | ~25MB | ~5MB | ~30MB |
| MySQL  | ~20MB | ~8MB | ~28MB |
| PostgreSQL | ~18MB | ~10MB | ~28MB |

## 🔄 迁移路径

### SQLite → MySQL
```bash
# 1. 配置 MySQL
./scripts/setup_mysql.sh

# 2. 导出 SQLite 数据（可选）
sqlite3 data/balance_alert.db .dump > backup.sql

# 3. 启动应用（自动创建表）
python3 web_server_modular.py
```

### SQLite → PostgreSQL
```bash
# 1. 配置 PostgreSQL
./scripts/setup_postgresql.sh

# 2. 启动应用
python3 web_server_modular.py
```

### MySQL → PostgreSQL
```bash
# 使用 pgloader 工具
pgloader mysql://user:pass@localhost/balance_alert \
          postgresql://user:pass@localhost/balance_alert
```

## 🔒 安全性对比

| 特性 | SQLite | MySQL | PostgreSQL |
|------|--------|-------|------------|
| **用户管理** | ❌ 文件权限 | ✅ 完整 | ✅ 完整 |
| **权限控制** | ❌ | ✅ 细粒度 | ✅ 非常细 |
| **SSL 连接** | ❌ | ✅ 支持 | ✅ 支持 |
| **加密** | ❌ | ✅ 支持 | ✅ 支持 |
| **审计日志** | ❌ | ✅ 支持 | ✅ 完整 |

## 💰 成本对比

### 云服务月费（按流量和存储计算）

| 服务 | 小规模 | 中规模 | 大规模 |
|------|--------|--------|--------|
| **SQLite** | $0 (本地) | $0 (本地) | ❌ 不适用 |
| **MySQL (AWS RDS)** | ~$15 | ~$50 | ~$200 |
| **PostgreSQL (AWS RDS)** | ~$15 | ~$60 | ~$300 |
| **MySQL (阿里云)** | ~¥50 | ~¥200 | ~¥800 |
| **PostgreSQL (阿里云)** | ~¥60 | ~¥250 | ~¥1000 |

*价格仅供参考，实际费用请查询云服务商*

## 📚 学习资源

### SQLite
- 官方文档: https://www.sqlite.org/docs.html
- 快速入门: 无需学习，开箱即用

### MySQL
- 官方文档: https://dev.mysql.com/doc/
- 配置指南: [docs/MYSQL_SETUP.md](./MYSQL_SETUP.md)
- 快速入门: [docs/QUICK_START_MYSQL.md](./QUICK_START_MYSQL.md)

### PostgreSQL
- 官方文档: https://www.postgresql.org/docs/
- 配置指南: [docs/POSTGRESQL_SETUP.md](./POSTGRESQL_SETUP.md)
- 快速入门: [docs/QUICK_START_POSTGRESQL.md](./QUICK_START_POSTGRESQL.md)

## 🎓 最佳实践

### 开发环境
```bash
# 使用 SQLite，简单快速
DATABASE_URL=sqlite:///./data/balance_alert.db
```

### 测试环境
```bash
# 使用与生产相同的数据库类型
# 如果生产用 MySQL，测试也用 MySQL
DATABASE_URL=mysql+pymysql://test:test@localhost:3306/balance_alert_test
```

### 生产环境
```bash
# 根据规模选择：
# - 小规模（< 20 项目）: SQLite 或 MySQL
# - 中规模（20-200 项目）: MySQL
# - 大规模（> 200 项目）: PostgreSQL

# MySQL 示例
DATABASE_URL=mysql+pymysql://user:pass@db.example.com:3306/balance_alert?charset=utf8mb4&ssl=true

# PostgreSQL 示例
DATABASE_URL=postgresql://user:pass@db.example.com:5432/balance_alert?sslmode=require
```

## 🚀 快速决策流程图

```
开始
  │
  ├─ 只是开发测试？
  │   └─ 是 → SQLite ✅
  │
  ├─ 需要高可用？
  │   └─ 否 → SQLite 或 MySQL
  │   └─ 是 ↓
  │
  ├─ 项目数量 < 50？
  │   └─ 是 → MySQL ✅
  │   └─ 否 ↓
  │
  ├─ 需要复杂查询？
  │   └─ 是 → PostgreSQL ✅
  │   └─ 否 → MySQL ✅
  │
  └─ 团队更熟悉哪个？
      └─ 熟悉的数据库 ✅
```

---

**总结**:
- 🚀 **快速开始**: SQLite
- 🌐 **Web 应用**: MySQL
- 🏢 **企业级**: PostgreSQL

**建议**: 从 SQLite 开始开发，根据需求逐步迁移到 MySQL 或 PostgreSQL。

---

**最后更新**: 2026-02-24
**维护者**: Balance Alert Team
