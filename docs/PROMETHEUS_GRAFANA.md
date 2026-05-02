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
```bash
# 启动所有服务（包括监控栈）
docker compose --profile monitoring up -d

# 查看日志
docker compose --profile monitoring logs -f

# 停止服务
docker compose --profile monitoring down
```
- **Grafana**: http://localhost:3000 （默认账号：admin/admin123）
- **Prometheus**: http://localhost:9090
- **监控服务**: http://localhost:8080
- **Metrics端点**: http://localhost:9100/metrics

### 方式二：独立部署

#### 1. 启动监控服务

```bash
# 本地运行
python main.py

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

### 使用内置 Prometheus

#### Prometheus 配置

编辑 `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'balance-alert'
    static_configs:
      - targets: ['localhost:8080']  # 修改为你的服务地址
```

#### Grafana 配置

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

### 使用外部 Prometheus

如果您已有 Prometheus 环境，只需配置 Prometheus 采集本服务的 metrics 端点。

#### 1. 启动余额监控服务

**方式 A: Docker 启动（只启动 Web 服务）**

```bash
# 使用原有的 docker-compose.yml
docker-compose up -d
```

**方式 B: 本地启动**

```bash
python3 main.py
```

Metrics 端点: `http://localhost:9100/metrics`

#### 2. 配置外部 Prometheus

在您的 Prometheus 配置文件中添加采集任务：

```yaml
scrape_configs:
  # ... 您现有的其他 job ...

  # 余额监控服务
  - job_name: 'balance-alert'
    scrape_interval: 60s  # 采集间隔
    static_configs:
      - targets: ['<YOUR_HOST>:9100']  # 替换为实际地址，使用 9100 端口
        labels:
          service: 'balance-alert'
          environment: 'production'  # 可自定义
```

#### 3. 不同场景的 targets 配置

**场景 1: Prometheus 和 Web 服务在同一台机器**
```yaml
- targets: ['localhost:9100']
```

**场景 2: Web 服务在其他服务器**
```yaml
- targets: ['192.168.1.100:9100']  # 替换为实际 IP
```

**场景 3: Web 服务在 Docker 容器中（Prometheus 在宿主机）**
```yaml
# Docker Desktop (Mac/Windows)
- targets: ['host.docker.internal:9100']

# Linux Docker
- targets: ['172.17.0.1:9100']  # Docker 默认网关
```

**场景 4: Kubernetes 环境**
```yaml
- job_name: 'balance-alert'
  kubernetes_sd_configs:
    - role: pod
  relabel_configs:
    - source_labels: [__meta_kubernetes_pod_label_app]
      regex: balance-alert
      action: keep
```

**场景 5: 使用服务发现（Consul）**
```yaml
- job_name: 'balance-alert'
  consul_sd_configs:
    - server: 'consul.example.com:8500'
      services: ['balance-alert']
```

#### 4. 验证 Prometheus 采集

**检查 Metrics 端点**
```bash
curl http://localhost:9100/metrics | grep balance_alert
```

**检查 Prometheus Targets**

访问 Prometheus UI: `http://<PROMETHEUS_HOST>:9090`

1. 进入 Status → Targets
2. 找到 `balance-alert` job
3. 状态应为 **UP**（绿色）

**执行测试查询**

在 Prometheus Graph 页面执行：
```promql
balance_alert_balance
```

应该返回所有项目的余额数据。

#### 5. 配置外部 Grafana

**添加 Prometheus 数据源**

- **Name**: `Prometheus` 或自定义
- **Type**: `Prometheus`
- **URL**: 
  - 同一网络: `http://prometheus:9090`
  - 其他服务器: `http://<PROMETHEUS_HOST>:9090`
  - Docker: `http://host.docker.internal:9090`

**导入 Dashboard**

方式 1: 手动导入
```bash
# 1. 下载 balance-alert-dashboard.json
# 2. Grafana → Dashboards → Import → Upload JSON file
# 3. 选择对应的 Prometheus 数据源
# 4. 点击 Import
```

方式 2: 使用 API 导入
```bash
# 修改导入脚本配置
export GRAFANA_URL="http://your-grafana:3000"
export GRAFANA_USER="admin"
export GRAFANA_PASS="your-password"

# 编辑 import_dashboard.sh 修改第一行配置
# 然后运行
./import_dashboard.sh
```

方式 3: 手动 API 调用
```bash
# 获取数据源 UID
DATASOURCE_UID=$(curl -s -u admin:password \
  http://your-grafana:3000/api/datasources/name/Prometheus | jq -r '.uid')

# 替换 Dashboard 中的数据源 UID
sed "s/\"uid\": \"prometheus\"/\"uid\": \"$DATASOURCE_UID\"/g" \
  grafana/dashboards/balance-alert-dashboard.json > /tmp/dashboard.json

# 导入 Dashboard
cat /tmp/dashboard.json | jq '{dashboard: ., overwrite: true}' | \
  curl -X POST \
  -H "Content-Type: application/json" \
  -u admin:password \
  -d @- \
  http://your-grafana:3000/api/dashboards/db
```

#### 6. 网络连通性检查

如果 Prometheus 无法采集数据：

```bash
# 从 Prometheus 容器内测试
docker exec -it <prometheus-container> wget -O- http://web:9100/metrics

# 从 Prometheus 宿主机测试
curl http://localhost:9100/metrics

# 测试端口连通性
telnet <web-host> 9100
```

#### 7. 安全配置（可选）

**使用 Nginx 反向代理**

```nginx
# /etc/nginx/sites-available/balance-alert-metrics
location /metrics {
    proxy_pass http://localhost:9100/metrics;
    
    # 添加基础认证
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    # 只允许 Prometheus 服务器访问
    allow 192.168.1.100;  # Prometheus IP
    deny all;
}
```

**使用 Prometheus 基础认证**

```yaml
scrape_configs:
  - job_name: 'balance-alert'
    basic_auth:
      username: 'prometheus'
      password: 'your-password'
    static_configs:
      - targets: ['localhost:9100']
```

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
curl http://localhost:9100/metrics

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

### 1. 余额采集频率

**默认配置**: 每 **3600 秒**（60 分钟）自动更新一次

在 `config.json` 中配置：
```json
{
  "settings": {
    "balance_refresh_interval_seconds": 3600
  }
}
```

**配置说明**：
- 单位：秒
- 最小值：60 秒（1 分钟）
- 默认值：3600 秒（60 分钟）
- 修改配置后需重启服务生效

**常用配置**：
- 5 分钟：`"balance_refresh_interval_seconds": 300`
- 10 分钟：`"balance_refresh_interval_seconds": 600`
- 1 小时：`"balance_refresh_interval_seconds": 3600`

### 2. Prometheus 采集间隔

- 编辑 `prometheus.yml` 中的 `scrape_interval`
- 推荐 60s-300s

### 3. 数据保留时间

- 默认保留 30 天
- 修改 Prometheus 启动参数：`--storage.tsdb.retention.time=30d`

### 4. Grafana 刷新频率

- Dashboard 右上角设置自动刷新间隔
- 推荐 1m-5m

## 🔗 相关链接

- [Prometheus 文档](https://prometheus.io/docs/)
- [Grafana 文档](https://grafana.com/docs/)
- [PromQL 查询语法](https://prometheus.io/docs/prometheus/latest/querying/basics/)
