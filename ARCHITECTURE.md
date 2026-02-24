# 系统架构文档

## 目录

- [总体架构](#总体架构)
- [核心模块](#核心模块)
- [数据流](#数据流)
- [部署架构](#部署架构)
- [技术栈](#技术栈)
- [设计决策](#设计决策)

## 总体架构

Balance Alert 是一个云原生的多项目余额/积分监控系统，采用微服务友好的架构设计。

```
┌─────────────────────────────────────────────────────────┐
│                      用户界面                            │
│  Web Dashboard │ API 客户端 │ 告警通知（飞书/钉钉/邮件）│
└────────────────┬────────────────────────────────────────┘
                 │
┌────────────────┴────────────────────────────────────┬───┐
│               Web Server (Flask)                    │   │
│  ┌──────────────┬──────────────┬─────────────────┐ │   │
│  │  REST API    │  WebSocket   │  Status Page    │ │   │
│  ├──────────────┼──────────────┼─────────────────┤ │ P │
│  │ /api/credits │ /api/refresh │ /api/history/*  │ │ r │
│  │ /api/config  │ /health      │ /metrics        │ │ o │
│  └──────────────┴──────────────┴─────────────────┘ │ m │
└────────────────┬────────────────────────────────────┤ e │
                 │                                    │ t │
┌────────────────┴────────────────────────────────────┤ h │
│            Core Monitoring Engine                   │ e │
│  ┌──────────────────────┬──────────────────────┐   │ u │
│  │  CreditMonitor       │  SubscriptionChecker │   │ s │
│  │  - 多Provider支持    │  - 续费提醒          │   │   │
│  │  - 并发检查(20线程)  │  - 周期计算          │   │   │
│  │  - 智能缓存          │  - 灵活周期          │   │   │
│  │  - 告警逻辑          │                      │   │   │
│  └────────┬─────────────┴─────┬────────────────┘   │ E │
│           │                   │                    │ x │
│  ┌────────┴───────┬───────────┴────────┐           │ p │
│  │  Provider      │  Webhook Adapter   │           │ o │
│  │  Adapters      │  - Feishu/钉钉     │           │ r │
│  │  - OpenRouter  │  - 通用Webhook     │           │ t │
│  │  - Anthropic   │  - 重试机制        │           │ e │
│  │  - OpenAI      │                    │           │ r │
│  │  - Azure       │                    │           │   │
│  └────────────────┴────────────────────┘           │   │
└────────────────┬────────────────────────────────────┴───┘
                 │
┌────────────────┴────────────────────────────────────────┐
│                 Data Layer                              │
│  ┌───────────────┬────────────────┬──────────────────┐  │
│  │ State Manager │ SQLite/PG DB   │ Config Loader    │  │
│  │ - 内存缓存    │ - 历史数据     │ - 热重载         │  │
│  │ - 实时状态    │ - 趋势分析     │ - 环境变量       │  │
│  └───────────────┴────────────────┴──────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 核心模块

### 1. Monitor 模块 (`monitor.py`)

**职责**：多项目余额/积分监控的核心引擎

**关键特性**：
- 并发检查：ThreadPoolExecutor 支持最多 50 个并发检查
- 缓存机制：Provider 实例缓存（10分钟）+ 响应结果缓存（5分钟）
- 智能刷新：检测余额变化率，动态调整刷新间隔
- Prometheus 指标：记录执行时间、API 调用延迟

**工作流程**：
```
1. 加载配置（config.json + 环境变量）
2. 过滤启用的项目
3. 并发执行 check_project()
   ├─ 获取 Provider 实例（带缓存）
   ├─ 检查响应缓存（TTL=300s）
   ├─ 调用 Provider API
   ├─ 保存到数据库（可选）
   └─ 判断是否需要告警
4. 汇总结果并记录指标
```

### 2. Provider 适配器 (`providers/`)

**设计模式**：策略模式 + 工厂模式

**支持的 Provider**：
- `OpenRouterProvider` - OpenRouter API
- `AnthropicProvider` - Claude API
- `OpenAIProvider` - OpenAI API
- `AzureProvider` - Azure OpenAI
- `DeepSeekProvider` - DeepSeek API
- `GroqProvider` - Groq API

**统一接口**：
```python
class BaseProvider:
    def get_credits(self) -> Dict[str, Any]:
        """
        返回格式：
        {
            'success': bool,
            'credits': float,
            'currency': str,
            'error': str  # 仅失败时
        }
        """
```

**重试机制**：
- 使用 `tenacity` 库实现指数退避
- 默认重试 3 次，最大等待 10 秒
- 处理网络超时、API 限流

### 3. Web Server (`web_server.py`)

**框架**：Flask + Waitress (生产) / Flask Dev Server (开发)

**API 分组**：

#### 核心 API
- `GET /` - 仪表盘页面
- `GET /health` - 健康检查（支持 Kubernetes）
- `GET /api/credits` - 获取所有项目余额
- `POST /api/refresh` - 手动刷新（有冷却时间）

#### 订阅管理 API
- `GET /api/subscriptions` - 获取订阅状态
- `POST /api/subscription/add` - 添加订阅
- `POST /api/config/subscription` - 更新订阅
- `DELETE /api/subscription/delete` - 删除订阅

#### 历史数据 API（需启用数据库）
- `GET /api/history/balance` - 余额历史查询
- `GET /api/history/trend/<id>` - 趋势分析
- `GET /api/history/alerts` - 告警历史
- `GET /api/history/stats` - 统计报表

#### 配置 API
- `GET /api/config/projects` - 获取项目配置
- `POST /api/config/threshold` - 更新阈值

**认证机制**：
- API Key 认证（可选）：`Authorization: Bearer <key>`
- JWT 认证（可选）：Flask-JWT-Extended
- Rate Limiting：Flask-Limiter（默认 100 req/min）

**性能优化**：
- ETag 支持（304 Not Modified）
- 响应压缩（gzip）
- 后台线程刷新（避免阻塞请求）

### 4. 数据持久化 (`database/`)

**ORM**：SQLAlchemy 2.0

**数据模型**：
```
BalanceHistory (balance_history)
├─ id (PK)
├─ project_id (INDEX)
├─ project_name
├─ provider (INDEX)
├─ balance, threshold, currency
└─ timestamp (INDEX)
    复合索引：(project_id, timestamp), (provider, timestamp)

AlertHistory (alert_history)
├─ id (PK)
├─ project_id (INDEX)
├─ alert_type (INDEX)
├─ message, status
└─ timestamp
    复合索引：(project_id, alert_type, timestamp)

SubscriptionHistory (subscription_history)
├─ id (PK)
├─ subscription_id (INDEX)
├─ days_until_renewal
└─ timestamp
    复合索引：(subscription_id, timestamp)
```

**Repository 模式**：
- `BalanceRepository` - 余额数据访问
- `AlertRepository` - 告警数据访问
- `SubscriptionRepository` - 订阅数据访问

**数据库迁移**：
- Alembic 管理版本
- 初始 Schema：`alembic/versions/001_initial_schema.py`

### 5. 配置管理 (`config_loader.py`)

**三种配置模式**：

1. **纯环境变量模式** (`USE_ENV_CONFIG=true`)
   - 所有配置从环境变量读取
   - 适合容器化部署、敏感信息保护

2. **混合模式** (默认)
   - 从 `config.json` 加载结构
   - 敏感字段（API Key、密码）用环境变量替换
   - 兼顾可读性和安全性

3. **纯文件模式**
   - 所有配置从 `config.json` 读取
   - 适合开发环境

**热重载机制**：
- 使用 `watchdog` 监听文件变化
- 1 秒防抖，避免多次触发
- 异步通知 Web Server 更新缓存

**环境变量命名规范**：
```bash
# 项目配置
PROJECT_1_NAME=OpenRouter-Main
PROJECT_1_PROVIDER=openrouter
PROJECT_1_API_KEY=sk-xxx
PROJECT_1_THRESHOLD=100.0

# 邮箱配置
EMAIL_1_NAME=飞书邮箱
EMAIL_1_HOST=imap.feishu.cn
EMAIL_1_USERNAME=user@example.com
```

### 6. 状态管理 (`state_manager.py`)

**职责**：内存中的实时状态缓存

**存储数据**：
- `_balance_state`: 最新余额状态（每个项目）
- `_subscription_state`: 订阅续费状态
- `_last_update`: 最后更新时间
- `_cache_ttl`: 缓存有效期

**线程安全**：
- 使用 `threading.RLock` 保护状态
- 支持多线程并发访问

**持久化**：
- 可选保存到 JSON 文件（`BALANCE_CACHE_FILE`）
- 重启后恢复状态

### 7. Webhook 适配器 (`webhook_adapter.py`)

**支持的平台**：
- 飞书（Feishu）
- 钉钉（DingTalk）
- 自定义 Webhook

**消息模板**：
- 余额告警：红色卡片，含当前值/阈值
- 续费提醒：黄色卡片，含剩余天数
- 富文本支持（Markdown）

**重试机制**：
- Tenacity 指数退避
- 3 次重试，最大 10 秒等待

### 8. Prometheus 监控 (`prometheus_exporter.py`)

**指标类别**：

**业务指标**：
- `balance_alert_project_balance` - 项目余额（Gauge）
- `balance_alert_active_projects` - 活跃项目数（Gauge）
- `balance_alert_alerts_total` - 告警总数（Counter）

**性能指标**：
- `balance_alert_monitor_execution_time` - 监控执行时间（Histogram）
- `balance_alert_provider_api_latency` - API 延迟（Histogram）
- `balance_alert_http_request_duration` - HTTP 请求时长（Histogram）

**缓存指标**：
- `balance_alert_cache_hits` - 缓存命中（Counter）
- `balance_alert_cache_misses` - 缓存未命中（Counter）

**API 指标**：
- `balance_alert_provider_api_calls` - API 调用次数（Counter by provider, status）

**暴露端点**：
- 默认端口：`9100`
- 路径：`/metrics`（Prometheus 格式）

## 数据流

### 余额检查流程

```
1. 定时器触发 (Cron/后台线程)
   │
   ├──> 2. CreditMonitor.run()
   │     │
   │     ├──> 3. 加载配置 (config_loader)
   │     │     ├─ 读取 config.json
   │     │     └─ 替换环境变量
   │     │
   │     ├──> 4. 并发检查项目 (ThreadPoolExecutor)
   │     │     │
   │     │     ├──> 5. check_project(project)
   │     │     │     ├─ 缓存检查 (TTL=300s)
   │     │     │     │  └─ 命中 → 直接返回
   │     │     │     │
   │     │     │     ├─ Provider.get_credits()
   │     │     │     │  ├─ HTTP 请求 API
   │     │     │     │  ├─ 重试机制（最多3次）
   │     │     │     │  └─ 记录 Prometheus 指标
   │     │     │     │
   │     │     │     ├─ 保存到数据库（可选）
   │     │     │     │  └─ BalanceRepository.save()
   │     │     │     │
   │     │     │     └─ 判断告警
   │     │     │        ├─ balance < threshold?
   │     │     │        └─ Yes → send_alarm()
   │     │     │              ├─ WebhookAdapter.send()
   │     │     │              └─ AlertRepository.save()
   │     │     │
   │     │     └──> 6. 汇总结果
   │     │
   │     └──> 7. 更新 StateManager 缓存
   │           └─ 写入内存 + 可选持久化
   │
   └──> 8. Web API 返回最新状态
         └─ GET /api/credits → 从 StateManager 读取
```

### 配置热重载流程

```
1. 用户编辑 config.json
   │
   ├──> 2. Watchdog 检测文件变化
   │     │
   │     └──> 3. 触发 reload 事件 (1秒防抖)
   │           │
   │           ├──> 4. config_loader 重新加载
   │           │     ├─ 解析 JSON
   │           │     ├─ 替换环境变量
   │           │     └─ 验证配置
   │           │
   │           └──> 5. 通知 Web Server
   │                 └─ 后台线程刷新缓存
   │                   ├─ CreditMonitor.run()
   │                   └─ 更新 StateManager
```

## 部署架构

###Kubernetes 部署

```yaml
┌─────────────────────────────────────────────────┐
│              Ingress (可选)                     │
│  ┌──────────────────────────────────────────┐   │
│  │  nginx-ingress / Traefik                 │   │
│  │  balance-alert.example.com               │   │
│  └──────────────┬───────────────────────────┘   │
└─────────────────┼───────────────────────────────┘
                  │
┌─────────────────┴────────────────────────────────┐
│           Service (ClusterIP)                    │
│  ┌────────────────┬──────────────────────────┐   │
│  │  web:8080      │  metrics:9100            │   │
│  └────────┬───────┴──────────┬───────────────┘   │
└───────────┼──────────────────┼───────────────────┘
            │                  │
┌───────────┴──────────────────┴───────────────────┐
│        Deployment (2 replicas)                   │
│  ┌────────────────────────────────────────────┐  │
│  │  Pod 1                    Pod 2            │  │
│  │  ┌──────────┐             ┌──────────┐     │  │
│  │  │Container │             │Container │     │  │
│  │  │  - Web   │             │  - Web   │     │  │
│  │  │  - Cron  │             │  - Cron  │     │  │
│  │  └──────────┘             └──────────┘     │  │
│  │                                            │  │
│  │  Resources:                                │  │
│  │  - CPU: 250m / Limit 500m                 │  │
│  │  - Mem: 256Mi / Limit 512Mi               │  │
│  └────────────────────────────────────────────┘  │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────┴───────────────────────────────┐
│         ConfigMap & Secret                       │
│  ┌────────────────────────────────────────────┐  │
│  │  ConfigMap: config.json 结构               │  │
│  │  Secret: API Keys, Webhook URL            │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│         PersistentVolumeClaim (可选)            │
│  ┌────────────────────────────────────────────┐  │
│  │  SQLite DB: /app/data/balance_alert.db    │  │
│  │  Size: 1Gi                                │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

**健康检查配置**：
```yaml
readinessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 5

livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 30

startupProbe:
  httpGet:
    path: /health
    port: 8080
  periodSeconds: 5
  failureThreshold: 12
```

**PodDisruptionBudget**：
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: balance-alert-pdb
spec:
  minAvailable: 1  # 保证至少1个Pod可用
```

### Docker Compose 部署

```yaml
version: '3.8'

services:
  balance-alert:
    image: balance-alert:latest
    ports:
      - "8080:8080"    # Web UI
      - "9100:9100"    # Prometheus Metrics
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/balance
      - WEBHOOK_URL=${WEBHOOK_URL}
    volumes:
      - ./config.json:/app/config.json:ro
      - ./data:/app/data
    restart: unless-stopped

  postgres:  # 可选：使用 PostgreSQL 代替 SQLite
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: balance
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - postgres-data:/var/lib/postgresql/data

  prometheus:  # 可选：监控
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

volumes:
  postgres-data:
```

## 技术栈

### 后端框架
- **Python 3.11+**
- **Flask 3.0** - Web 框架
- **Waitress** - WSGI 生产服务器
- **SQLAlchemy 2.0** - ORM
- **Alembic** - 数据库迁移

### 异步与并发
- **threading** - 后台刷新线程
- **concurrent.futures** - 并发检查线程池
- **watchdog** - 文件监听

### 数据验证
- **Pydantic 2.0** - 数据模型验证
- **python-dotenv** - 环境变量加载

### 监控与日志
- **Prometheus Client** - 指标收集
- **python-json-logger** - 结构化日志
- **logging** - 标准日志

### HTTP 客户端
- **requests** - HTTP 请求（带重试）
- **tenacity** - 重试机制

### 安全
- **Flask-JWT-Extended** - JWT 认证
- **Flask-Limiter** - 速率限制
- **Flask-CORS** - 跨域支持

### API 文档
- **Flasgger** - Swagger/OpenAPI 自动生成

### 测试
- **pytest** - 测试框架
- **unittest.mock** - Mock 测试

## 设计决策

### 1. 为什么选择 SQLite 作为默认数据库？

**优势**：
- 零配置：无需独立数据库服务
- 高性能：本地文件访问，查询延迟 < 1ms
- 可移植：单个 DB 文件，易于备份和迁移
- 无依赖：标准库自带，减少部署复杂度

**适用场景**：
- 单实例部署（< 10万条历史记录）
- 读多写少（每小时写入 < 100 条）

**何时升级到 PostgreSQL**：
- 需要多实例负载均衡
- 历史数据 > 1GB
- 复杂的 JOIN 查询

### 2. 为什么使用线程池而非异步 I/O？ **当前选择**：`ThreadPoolExecutor` + 同步请求

**理由**：
- Provider API 响应时间通常 < 500ms
- 并发数有限（默认 20），线程开销可接受
- 代码简单，易于调试和维护
- 避免 async/await 的传染性（整个调用链需要异步化）

**未来优化方向**：
- 如果 Provider 数量 > 100，可考虑 asyncio + aiohttp
- 如果 API 延迟 > 2s，异步带来的收益更明显

### 3. 为什么分离 Web 端口和 Metrics 端口？

**安全考虑**：
- Metrics 端点暴露内部指标，不应公开访问
- 可在防火墙/Ingress 层隔离 9100 端口
- 避免 Metrics 流量影响 Web 服务性能

**K8s 最佳实践**：
- Prometheus ServiceMonitor 只抓取 metrics 端口
- Web 端口通过 Ingress 暴露
- 两者生命周期独立

### 4. 为什么同时支持环境变量和配置文件？

**灵活性**：
- 环境变量：容器化部署、CI/CD、敏感信息
- 配置文件：开发环境、复杂结构、版本控制

**安全性**：
- 敏感信息（API Key）必须用环境变量
- 结构配置（项目列表）可用文件，便于管理

**最佳实践**：
- 生产环境：`USE_ENV_CONFIG=true`（全环境变量）
- 开发环境：混合模式（文件结构 + 环境变量敏感字段）

### 5. 为什么使用 Pydantic 而不是手动验证？

**类型安全**：
- 自动类型转换（str → int, bool）
- 运行时类型检查

**错误提示**：
- 内置验证错误信息
- 标准化错误格式（便于前端解析）

**代码简洁**：
- 单个请求验证减少 26-53% 代码
- 避免重复的 if/else 判断

### 6. 为什么不使用消息队列（如 Redis Queue）？

**当前规模不需要**：
- 项目数量通常 < 100
- 检查频率：每小时一次
- 并发度：20 足够

**引入 MQ 的复杂度**：
- 增加依赖（Redis/RabbitMQ）
- 需要处理队列失败、重试、死信
- 部署和运维成本增加

**何时引入**：
- 项目数 > 1000
- 需要分布式调度（多个 Worker）
- 需要精确的任务优先级控制

### 7. 为什么使用 Cron + Supercronic 而不是 APScheduler？

**Cron 优势**：
- 标准化：所有运维都熟悉 Cron 语法
- 隔离性：每次执行是独立进程
- 可靠性：不会因主进程异常而停止调度
- 可观测：日志独立，易于排查

**APScheduler 的问题**：
- 在主进程中运行，OOM 或崩溃会停止调度
- 内存泄漏风险（长期运行）
- 调试困难（与 Web 请求混在一起）

### 8. 为什么不使用 Celery？

**Celery 过重**：
- 需要 Broker（Redis/RabbitMQ）
- 需要独立 Worker 进程
- 配置复杂（Beat Scheduler）

**当前场景简单**：
- 只有 2 个定时任务
- 任务执行时间 < 30s
- 不需要分布式任务调度

**Cron + 独立脚本更合适**：
- 部署简单（单个容器）
- 日志清晰（stdout）
- 资源占用小

## 性能指标

### 典型负载（20个项目）

| 指标 | 值 |
|------|------|
| 监控执行时间 | < 2s（并发检查） |
| 内存占用 | 80-120 MB（含 Flask + 缓存） |
| CPU 使用率 | < 5%（空闲时） / 20%（检查时） |
| API 响应延迟 | P50=15ms, P95=50ms, P99=200ms |
| 数据库查询延迟 | < 5ms（SQLite 本地） |

### 扩展性

| 场景 | 推荐配置 |
|------|----------|
| < 50 个项目 | 单实例，SQLite，2 副本（HA） |
| 50-200 个项目 | 单实例，PostgreSQL，3 副本 |
| > 200 个项目 | 多实例 + 负载均衡，PostgreSQL |

### 缓存命中率

- Provider 实例缓存：> 95%（10分钟 TTL）
- 响应结果缓存：> 80%（5分钟 TTL）
- StateManager 缓存：100%（内存常驻）

## 安全性

### 认证与授权

1. **API Key 认证**（默认）
   - 环境变量：`API_KEY`
   - 请求头：`Authorization: Bearer <key>`
   - 可选启用

2. **JWT 认证**（高级）
   - 环境变量：`ENABLE_JWT=true`
   - Token 过期时间：1 小时
   - 刷新Token支持

### 速率限制

- 默认：100 req/min （可配置）
- IP 级别限制
- 可针对端点单独配置

### 数据安全

1. **敏感信息保护**
   - API Key 必须用环境变量
   - 不记录敏感字段到日志
   - 数据库连接字符串加密

2. **输入验证**
   - Pydantic 模型验证
   - SQL 注入防护（SQLAlchemy ORM）
   - XSS 防护（Flask 自动转义）

3. **HTTPS 加密**
   - 生产环境强制 HTTPS
   - 使用 Ingress TLS 终止

## 可观测性

### 日志

**日志级别**：
- INFO：正常操作（余额检查、告警发送）
- WARNING：异常但可恢复（API 重试、配置缺失）
- ERROR：失败操作（API 调用失败、数据库错误）

**日志格式**：
- 开发：文本格式（可读性）
- 生产：JSON 格式（结构化查询）

**日志聚合**：
- 标准输出（stdout/stderr）
- 容器日志驱动收集
- ELK/Loki/Splunk 分析

### Metrics

**Prometheus 指标**：
- 业务指标：`balance_alert_project_balance`
- 性能指标：`balance_alert_monitor_execution_time`
- API 指标：`balance_alert_provider_api_calls_total`

**Grafana 仪表盘**：
- 余额趋势图
- API 调用成功率
- 告警频率统计

### Tracing（未来）

- OpenTelemetry 集成
- 分布式追踪（API 调用链路）
- 性能瓶颈分析

## 故障恢复

### 自动恢复机制

1. **Provider API 失败**
   - 3次指数退避重试
   - 失败后记录ERROR日志
   - 不影响其他项目检查

2. **数据库不可用**
   - 优雅降级：跳过历史记录保存
   - 主功能（余额检查）继续工作
   - 日志记录错误

3. **配置文件损坏**
   - 加载失败时使用缓存配置
   - 告警通知运维人员
   - /health 端点返回 503

4. **Web 服务崩溃**
   - K8s livenessProbe 自动重启
   - 后台任务由 Cron 独立调度
   - 零数据丢失（数据库持久化）

### 灾难恢复

1. **数据备份**
   - SQLite 文件：每天自动备份
   - 配置文件：纳入版本控制

2. **恢复流程**
   - 恢复配置文件 → 验证语法
   - 恢复数据库文件 → 检查完整性
   - 重启服务 → 健康检查

## 未来优化方向

### 短期（1-3个月）

- [ ] Swagger UI 完整集成
- [ ] 更多 Provider 支持（Google Vertex AI, Mistral）
- [ ] 数据清理策略（自动删除旧数据）
- [ ] 异常检测（余额异常波动告警）

### 中期（3-6个月）

- [ ] Web Server 模块化重构（Blueprint 拆分）
- [ ] Grafana 官方仪表盘模板
- [ ] 多语言支持（i18n）
- [ ] 移动端通知（iOS/Android Push）

### 长期（6-12个月）

- [ ] 异步 I/O 重构（asyncio + aiohttp）
- [ ] 分布式部署支持（多实例负载均衡）
- [ ] 机器学习预测（余额耗尽预估）
- [ ] SaaS 化（多租户支持）

---

**文档维护**：本文档应随架构演进及时更新
**最后更新**：2024-02-24
**维护者**：项目团队
