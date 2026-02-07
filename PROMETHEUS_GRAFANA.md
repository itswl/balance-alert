# Prometheus + Grafana 监控部署指南

## 📊 功能说明

本系统已集成 Prometheus Exporter，可以将余额/订阅监控数据推送到 Prometheus，并通过 Grafana 进行可视化展示。

### 暴露的指标

#### 余额/积分指标
- `balance_alert_balance` - 当前余额/积分
- `balance_alert_threshold` - 告警阈值
- `balance_alert_ratio` - 余额比例（余额/阈值）
- `balance_alert_status` - 余额状态（1=正常, 0=告警）

#### 订阅续费指标
- `balance_alert_subscription_days` - 距离续费天数
- `balance_alert_subscription_amount` - 续费金额
- `balance_alert_subscription_status` - 订阅状态（1=正常, 0=需续费, -1=已续费）

#### 系统指标
- `balance_alert_last_check_timestamp` - 最后检查时间戳
- `balance_alert_check_success` - 检查成功状态
- `balance_alert_email_scan_total` - 扫描邮件总数
- `balance_alert_email_alerts` - 告警邮件数

## 🚀 快速启动

### 方式一：Docker Compose 一键启动（推荐）

```bash
# 启动所有服务（Web + Prometheus + Grafana）
docker-compose -f docker-compose.monitoring.yml up -d

# 查看日志
docker-compose -f docker-compose.monitoring.yml logs -f

# 停止服务
docker-compose -f docker-compose.monitoring.yml down
```

启动后访问：
- **Grafana**: http://localhost:3000 （默认账号：admin/admin123）
- **Prometheus**: http://localhost:9090
- **监控服务**: http://localhost:8080
- **Metrics端点**: http://localhost:8080/metrics

### 方式二：独立部署

#### 1. 启动监控服务

```bash
# 本地运行
python web_server.py

# 或使用 Docker
docker-compose up -d
```

#### 2. 启动 Prometheus

```bash
# 使用 Docker
docker run -d \
  --name prometheus \
  -p 9090:9090 \
  -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus:latest
```

#### 3. 启动 Grafana

```bash
# 使用 Docker
docker run -d \
  --name grafana \
  -p 3000:3000 \
  -v grafana-data:/var/lib/grafana \
  grafana/grafana:latest
```

## 📝 配置说明

### Prometheus 配置

编辑 `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'balance-alert'
    static_configs:
      - targets: ['localhost:8080']  # 修改为你的服务地址
```

### Grafana 配置

1. **添加数据源**
   - 登录 Grafana (http://localhost:3000)
   - 进入 Configuration > Data Sources
   - 添加 Prometheus 数据源
   - URL: `http://prometheus:9090` (Docker) 或 `http://localhost:9090` (本地)

2. **导入 Dashboard**
   - 进入 Dashboards > Import
   - 上传 `grafana/dashboards/balance-alert-dashboard.json`
   - 选择 Prometheus 数据源
   - 点击 Import

## 📈 Grafana Dashboard 说明

预配置的 Dashboard 包含以下面板：

1. **余额/积分总览** - 显示所有项目的当前余额
2. **余额比例** - 仪表盘显示余额/阈值比例
3. **余额趋势** - 时间序列图表显示余额变化
4. **订阅续费倒计时** - 显示各订阅距离续费的天数
5. **订阅状态** - 表格显示订阅详细状态

## 🔍 查询示例

### Prometheus 查询

在 Prometheus UI (http://localhost:9090/graph) 中尝试以下查询：

```promql
# 查看所有项目余额
balance_alert_balance

# 查看余额不足的项目
balance_alert_status == 0

# 查看余额比例小于0.5的项目
balance_alert_ratio < 0.5

# 查看7天内需要续费的订阅
balance_alert_subscription_days <= 7

# 查看邮箱告警邮件增长率
rate(balance_alert_email_alerts[5m])
```

### Grafana 面板查询

在 Grafana 面板中使用的查询示例：

```promql
# 余额趋势（按项目分组）
balance_alert_balance{project="OpenRouter"}

# 订阅续费倒计时（按名称分组）
balance_alert_subscription_days{name=~".*"}

# 告警项目数量
sum(balance_alert_status == 0)

# 平均余额比例
avg(balance_alert_ratio)
```

## ⚠️ 告警规则

可以在 Prometheus 中配置告警规则，例如：

创建 `alert_rules.yml`:

```yaml
groups:
  - name: balance_alerts
    interval: 60s
    rules:
      - alert: BalanceLow
        expr: balance_alert_ratio < 0.2
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "余额不足告警"
          description: "{{ $labels.project }} 余额比例低于20%"

      - alert: SubscriptionExpiring
        expr: balance_alert_subscription_days <= 3
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "订阅即将到期"
          description: "{{ $labels.name }} 将在 {{ $value }} 天后到期"
```

然后在 `prometheus.yml` 中引用：

```yaml
rule_files:
  - "alert_rules.yml"
```

## 🔧 故障排查

### Metrics 端点无法访问

```bash
# 检查服务是否运行
curl http://localhost:8080/metrics

# 检查 prometheus-client 是否安装
pip list | grep prometheus-client
```

### Prometheus 无法抓取数据

1. 检查 Prometheus targets: http://localhost:9090/targets
2. 确认服务地址配置正确
3. 检查网络连接（Docker 网络或防火墙）

### Grafana 无法显示数据

1. 验证数据源连接：Configuration > Data Sources > Test
2. 检查 Prometheus 是否有数据：http://localhost:9090/graph
3. 确认查询语句正确

## 📊 性能优化

1. **调整采集间隔**
   - 编辑 `prometheus.yml` 中的 `scrape_interval`
   - 推荐 60s-300s

2. **数据保留时间**
   - 默认保留 30 天
   - 修改 Prometheus 启动参数：`--storage.tsdb.retention.time=30d`

3. **Grafana 刷新频率**
   - Dashboard 右上角设置自动刷新间隔
   - 推荐 1m-5m

## 🔗 相关链接

- [Prometheus 文档](https://prometheus.io/docs/)
- [Grafana 文档](https://grafana.com/docs/)
- [PromQL 查询语法](https://prometheus.io/docs/prometheus/latest/querying/basics/)
