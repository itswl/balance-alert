# 系统架构文档

## 总体架构

Balance Alert 是一个云原生的多平台余额/积分监控系统。

```
┌─────────────────────────────────────────┐
│       用户界面 (Web / API / 告警)        │
└────────────────┬────────────────────────┘
                 │
┌────────────────┴────────────────────────┐
│         Web Server (Flask)              │
│  REST API + WebSocket + Metrics         │
└────────────────┬────────────────────────┘
                 │
┌────────────────┴────────────────────────┐
│      Core Monitoring Engine             │
│  ├─ CreditMonitor (并发检查)            │
│  ├─ Provider Adapters (多平台)          │
│  ├─ Webhook Adapter (告警通知)          │
│  └─ SubscriptionChecker (续费提醒)      │
└────────────────┬────────────────────────┘
                 │
┌────────────────┴────────────────────────┐
│           Data Layer                    │
│  ├─ State Manager (内存缓存)            │
│  ├─ SQLite/PostgreSQL (历史数据)        │
│  └─ Config Loader (配置热重载)          │
└─────────────────────────────────────────┘
```

## 核心模块

### 1. Monitor 模块 (`monitor.py`)

**职责**：多项目余额/积分监控引擎

**关键特性**：
- 并发检查：ThreadPoolExecutor（最多 50 并发）
- 智能缓存：Provider 实例缓存（10分钟）+ 响应缓存（5分钟）
- Prometheus 指标记录

**工作流程**：
```
1. 加载配置 (config.json + 环境变量)
2. 过滤启用的项目
3. 并发执行检查
   ├─ 检查缓存
   ├─ 调用 Provider API
   ├─ 保存到数据库
   └─ 判断是否需要告警
4. 汇总结果并记录指标
```

### 2. Provider 适配器 (`providers/`)

**设计模式**：策略模式 + 工厂模式

**支持的 Provider**：
- OpenRouter, Anthropic, OpenAI, Azure
- 火山云 (Volc), 阿里云 (Aliyun)
- DeepSeek, Groq, TikHub, WxRank, UniAPI

**统一接口**：
```python
class BaseProvider:
    def get_credits(self) -> Dict[str, Any]:
        """
        返回: {
            'success': bool,
            'credits': float,
            'currency': str,
            'error': str  # 仅失败时
        }
        """
```

### 3. Web Server (`web_server.py`)

**框架**：Flask + Waitress

**核心 API**：
- `GET /` - 仪表盘页面
- `GET /health` - 健康检查
- `GET /api/credits` - 获取余额
- `POST /api/refresh` - 手动刷新

**订阅管理 API**：
- `GET /api/subscriptions` - 获取订阅状态
- `POST /api/subscription/add` - 添加订阅
- `DELETE /api/subscription/delete` - 删除订阅

**历史数据 API**（需启用数据库）：
- `GET /api/history/balance` - 余额历史
- `GET /api/history/trend/<id>` - 趋势分析
- `GET /api/history/alerts` - 告警历史

### 4. 数据持久化 (`database/`)

**ORM**：SQLAlchemy 2.0

**数据模型**：
```
BalanceHistory        # 余额历史
├─ project_id, balance, threshold
└─ timestamp (索引)

AlertHistory          # 告警历史
├─ project_id, alert_type, message
└─ timestamp

SubscriptionHistory   # 订阅历史
├─ subscription_id, days_until_renewal
└─ timestamp
```

### 5. 配置管理 (`config_loader.py`)

**三种配置模式**：
1. **纯环境变量模式** (`USE_ENV_CONFIG=true`)
2. **混合模式**（默认）- config.json + 环境变量
3. **纯文件模式** - 仅 config.json

**热重载机制**：
- watchdog 监听文件变化
- 1秒防抖
- 异步通知 Web Server 更新缓存

### 6. Webhook 适配器 (`webhook_adapter.py`)

**支持的平台**：
- 飞书（Feishu）
- 钉钉（DingTalk）
- 企业微信（WeCom）
- 自定义 Webhook

### 7. Prometheus 监控 (`prometheus_exporter.py`)

**业务指标**：
- `balance_alert_project_balance` - 项目余额
- `balance_alert_active_projects` - 活跃项目数
- `balance_alert_alerts_total` - 告警总数

**性能指标**：
- `balance_alert_monitor_execution_time` - 监控执行时间
- `balance_alert_provider_api_latency` - API 延迟
- `balance_alert_cache_hits/misses` - 缓存命中率

**暴露端点**：`:9100/metrics`

## 部署架构

### Docker Compose 部署

```yaml
services:
  balance-alert:
    image: balance-alert:latest
    ports:
      - "8080:8080"   # Web UI
      - "9100:9100"   # Metrics
    environment:
      - DATABASE_URL=sqlite:///data/balance.db
      - WEBHOOK_URL=${WEBHOOK_URL}
    volumes:
      - ./config.json:/app/config.json:ro
      - ./data:/app/data
    restart: unless-stopped
```

### Kubernetes 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: balance-alert
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: app
        image: balance-alert:latest
        ports:
        - containerPort: 8080
        - containerPort: 9100
        resources:
          requests:
            cpu: 250m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          periodSeconds: 30
```

## 技术栈

- **Python 3.11+**
- **Flask 3.0** - Web 框架
- **SQLAlchemy 2.0** - ORM
- **Prometheus Client** - 指标收集
- **requests** + **tenacity** - HTTP 客户端 + 重试
- **Pydantic 2.0** - 数据验证

## 设计决策

### 为什么选择 SQLite？

- 零配置，无需独立数据库服务
- 本地文件访问，查询延迟 < 1ms
- 适合单实例部署（< 10万条记录）

**何时升级到 PostgreSQL**：
- 多实例负载均衡
- 历史数据 > 1GB
- 需要复杂 JOIN 查询

### 为什么使用线程池而非异步 I/O？

- Provider API 响应通常 < 500ms
- 并发数有限（默认 20），线程开销可接受
- 代码简单，易于调试

### 为什么分离 Web 端口和 Metrics 端口？

- Metrics 不应公开访问（安全考虑）
- 避免 Metrics 流量影响 Web 性能
- K8s 最佳实践（ServiceMonitor 单独抓取）

## 性能指标

### 典型负载（20个项目）

| 指标 | 值 |
|------|------|
| 监控执行时间 | < 2s |
| 内存占用 | 80-120 MB |
| CPU 使用率 | < 5%（空闲） / 20%（检查时） |
| API 响应延迟 | P50=15ms, P95=50ms |

### 缓存命中率

- Provider 实例缓存：> 95%
- 响应结果缓存：> 80%
- StateManager 缓存：100%（内存常驻）

## 安全性

### 认证与授权
- API Key 认证（环境变量 `API_KEY`）
- JWT 认证（可选，`ENABLE_JWT=true`）

### 速率限制
- 默认：100 req/min（每个 IP）
- `/api/refresh`: 2 req/min + 30秒冷却

### 数据安全
- API Key 必须用环境变量
- 敏感字段不记录到日志
- HTTPS 加密（生产环境）

---

**最后更新**: 2024-02-24
