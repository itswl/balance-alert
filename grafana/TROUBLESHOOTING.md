# Grafana Dashboard 故障排查指南

## 问题：Dashboard 显示 "No Data"

### 可能的原因和解决方案

#### 1. 时间范围问题 ⏰

**症状**：所有面板都显示 "No Data"

**原因**：时间范围选择不正确，可能选择了未来或过去没有数据的时间段

**解决方案**：
```
1. 点击右上角的时间选择器
2. 选择 "Last 6 hours" 或 "Last 24 hours"
3. 确保时间范围包含当前时间
4. 点击 "Apply" 应用时间范围
```

#### 2. Prometheus 未采集数据 📊

**症状**：Dashboard 无数据，Prometheus 也查不到数据

**检查方法**：
```bash
# 检查 Prometheus targets 状态
curl http://localhost:9090/api/v1/targets

# 应该看到：
# "health": "up"
```

**如果状态是 "down"**：

a. **网络问题** - web 服务未加入正确的 Docker 网络
```bash
# 检查 docker-compose.yml
# 确保 web 服务有以下配置：
networks:
  - monitoring
```

b. **端口问题** - Metrics 端口未暴露
```bash
# 检查 web 服务是否暴露 9100 端口
docker ps | grep credit-monitor
```

c. **服务未启动** - balance-alert 服务未运行
```bash
# 重启服务
docker compose --profile monitoring restart web
```

**解决方案**：
```bash
# 1. 停止所有服务
docker compose --profile monitoring down

# 2. 重新启动
docker compose --profile monitoring up -d

# 3. 等待 30 秒让服务完全启动
sleep 30

# 4. 验证 Prometheus target 状态
curl http://localhost:9090/api/v1/targets | grep health
```

#### 3. Grafana 数据源配置错误 🔌

**症状**：Prometheus 有数据，但 Grafana 显示 "No Data"

**检查数据源**：
```
1. 登录 Grafana (http://localhost:3000)
2. 进入 Configuration → Data Sources
3. 点击 "Prometheus"
4. 检查 URL 是否为: http://prometheus:9090
5. 点击 "Save & Test"
6. 应该看到 "Data source is working"
```

**如果测试失败**：

a. **URL 错误**
```
正确: http://prometheus:9090 (Docker 网络内部)
错误: http://localhost:9090 (除非使用 host 网络)
```

b. **网络隔离**
```bash
# 确保 Grafana 在 monitoring 网络中
docker inspect balance-alert-grafana | grep monitoring
```

c. **重新创建数据源**
```
1. 删除现有的 Prometheus 数据源
2. 点击 "Add data source"
3. 选择 "Prometheus"
4. URL: http://prometheus:9090
5. Access: Server (default)
6. Save & Test
```

#### 4. Dashboard 查询语句错误 📝

**症状**：部分面板有数据，部分面板 "No Data"

**检查方法**：
```
1. 编辑显示 "No Data" 的面板
2. 查看 Query 部分
3. 点击 "Run queries" 手动执行查询
4. 检查是否有错误信息
```

**常见问题**：

a. **标签筛选器为空** - `{project=~"$project"}` 变量为空
```
解决：在顶部变量筛选器中选择 "All"
```

b. **指标名称错误** - 查询不存在的指标
```bash
# 验证指标是否存在
curl http://localhost:9100/metrics | grep balance_alert
```

c. **数据源引用错误** - Dashboard 中的数据源 UID 不匹配
```
解决：重新导入 Dashboard
./grafana/import-dashboard.sh
```

#### 5. 数据刷新问题 🔄

**症状**：之前有数据，现在突然没有了

**可能原因**：

a. **余额刷新间隔未到**
```
默认 1 小时刷新一次
查看配置: grep BALANCE_REFRESH_INTERVAL .env
```

b. **服务异常停止**
```bash
# 检查容器状态
docker ps | grep credit-monitor

# 查看容器日志
docker logs credit-monitor --tail 50
```

c. **Metrics 端点异常**
```bash
# 测试 metrics 端点
curl http://localhost:9100/metrics

# 应该返回大量 Prometheus 格式的指标
```

**解决方案**：
```bash
# 手动触发刷新
curl -X POST http://localhost:8080/api/refresh

# 等待 30 秒
sleep 30

# 刷新 Grafana Dashboard
```

## 完整的诊断流程

### 步骤 1: 检查服务状态

```bash
# 检查所有容器
docker compose --profile monitoring ps

# 应该看到 3 个容器都是 Up 状态：
# - credit-monitor
# - balance-alert-prometheus
# - balance-alert-grafana
```

### 步骤 2: 检查 Metrics 端点

```bash
# 测试 metrics 暴露
curl http://localhost:9100/metrics | head -20

# 应该看到类似：
# balance_alert_balance{project="...",provider="..."} 12345.0
```

### 步骤 3: 检查 Prometheus 采集

```bash
# 检查 targets
curl http://localhost:9090/api/v1/targets | python3 -m json.tool

# 查找 balance-alert job，确认：
# "health": "up"
# "lastError": ""

# 查询数据
curl "http://localhost:9090/api/v1/query?query=balance_alert_balance" | python3 -m json.tool

# 应该看到 result 数组中有数据
```

### 步骤 4: 检查 Grafana 数据源

```bash
# 测试数据源 API
curl -u "$GRAFANA_ADMIN_USER:$GRAFANA_ADMIN_PASSWORD" http://localhost:3000/api/datasources | python3 -m json.tool

# 应该看到 Prometheus 数据源：
# "name": "Prometheus"
# "url": "http://prometheus:9090"
# "isDefault": true
```

### 步骤 5: 检查 Dashboard

```
1. 访问 http://localhost:3000
2. 使用 .env 中的 GRAFANA_ADMIN_USER / GRAFANA_ADMIN_PASSWORD 登录
3. 进入 Dashboards → Browse
4. 找到 "余额监控 Dashboard"
5. 打开 Dashboard
6. 检查右上角时间范围
7. 点击任意面板的标题 → Edit
8. 查看 Query 部分
9. 点击 "Run queries"
```

## 自动化测试脚本

我们提供了自动化测试脚本来快速诊断问题：

```bash
# 测试 Metrics 和指标
./grafana/test-dashboard.sh

# 应该输出：
# ✅ Metrics 端点可访问
# ✅ balance_alert_balance
# ✅ balance_alert_threshold
# ...
# ✅ 测试通过！
```

## 重新开始 (Reset Everything)

如果所有方法都不奏效，可以完全重置：

```bash
# 1. 停止并删除所有容器和卷
docker compose --profile monitoring down -v

# 2. 删除 Grafana 数据
rm -rf grafana/grafana-data

# 3. 重新启动
docker compose --profile monitoring up -d

# 4. 等待服务启动
sleep 30

# 5. 手动触发一次余额刷新
curl -X POST http://localhost:8080/api/refresh

# 6. 测试指标
./grafana/test-dashboard.sh

# 7. 访问 Grafana
open http://localhost:3000

# 8. 如果 Dashboard 未自动加载，手动导入
./grafana/import-dashboard.sh
```

## 常见错误信息

### "invalid service state: Failed"

**完整错误**：
```
Datasource provisioning error: datasource.yaml config is invalid.
Only one datasource per organization can be marked as default
```

**原因**：有多个数据源配置文件，都设置了 `isDefault: true`

**解决**：
```bash
# 检查数据源目录
ls grafana/datasources/

# 应该只有一个文件：datasources.yml
# 删除其他重复的文件
rm grafana/datasources/prometheus.yml
```

### Prometheus 抓取 metrics 返回 EOF

**原因**：Prometheus target 指向了不存在的旧服务名，或应用服务未加入 monitoring 网络

**解决**：
```yaml
# docker-compose.yml
services:
  web:
    networks:
      - monitoring  # 添加这行
```

### "Data source is not working"

**原因**：Grafana 无法连接到 Prometheus

**解决**：
```
1. 检查 Prometheus URL: http://prometheus:9090
2. 检查 Access 模式: Server (default)
3. 确保 Grafana 和 Prometheus 在同一网络
```

## 联系支持

如果问题仍然无法解决，请提供以下信息：

```bash
# 收集诊断信息
echo "=== Container Status ===" > grafana-debug.log
docker compose --profile monitoring ps >> grafana-debug.log

echo "\n=== Prometheus Targets ===" >> grafana-debug.log
curl -s http://localhost:9090/api/v1/targets >> grafana-debug.log

echo "\n=== Metrics Sample ===" >> grafana-debug.log
curl -s http://localhost:9100/metrics | head -50 >> grafana-debug.log

echo "\n=== Grafana Logs ===" >> grafana-debug.log
docker logs balance-alert-grafana --tail 100 >> grafana-debug.log

echo "\n=== Prometheus Logs ===" >> grafana-debug.log
docker logs balance-alert-prometheus --tail 100 >> grafana-debug.log

echo "\n=== Web Logs ===" >> grafana-debug.log
docker logs credit-monitor --tail 100 >> grafana-debug.log

# 查看诊断文件
cat grafana-debug.log
```

---

**最后更新**: 2024-02-24
**版本**: 1.0
