
# Kubernetes 部署指南

## 文件说明

| 文件 | 说明 | 必需 |
|------|------|------|
| `namespace.yaml` | 创建 balance-alert 命名空间 | ✅ |
| `configmap.yaml` | ConfigMap 配置模板 | ✅ |
| `deployment.yaml` | 部署 balance-alert 应用 | ✅ |
| `service.yaml` | 服务暴露（ClusterIP + NodePort） | ✅ |
| `ingress.yaml` | Ingress 配置 | ❌ 可选 |
| `prometheus-config.yaml` | Prometheus 抓取配置参考 | ❌ 可选 |
| `servicemonitor.yaml` | ServiceMonitor（需 prometheus-operator） | ❌ 可选 |
| `kustomization.yaml` | Kustomize 配置 | ❌ 可选 |

> **注意**: 
> - Prometheus 和 Grafana 是可选的，如需监控可单独部署
> - `prometheus-config.yaml` 和 `servicemonitor.yaml` 仅作为配置参考

## 快速部署

### 方式一：从文件创建 ConfigMap（推荐）

```bash
# 1. 创建命名空间
kubectl apply -f k8s/namespace.yaml

# 2. 从本地 config.json 创建 ConfigMap
kubectl create configmap balance-alert-config \
  --from-file=config.json=config.json \
  -n balance-alert

# 3. 部署应用
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# 可选：启用 Ingress
# kubectl apply -f k8s/ingress.yaml
```

### 方式二：使用 Kustomize

```bash
# 编辑 kustomization.yaml，取消注释 configMapGenerator 部分
# 然后部署
kubectl apply -k k8s/
```

### 方式三：直接应用所有 YAML

```bash
# 注意：此方式使用 configmap.yaml 中的默认空配置
# 部署后需要手动更新 ConfigMap
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

## 配置管理

### 方式1: 从文件创建（推荐）

```bash
# 使用本地 config.json 创建/更新 ConfigMap
kubectl create configmap balance-alert-config \
  --from-file=config.json=config.json \
  -n balance-alert \
  --dry-run=client -o yaml | kubectl apply -f -

# 重启 Pod 使配置生效
kubectl rollout restart deployment/balance-alert -n balance-alert
```

### 方式2: 编辑 ConfigMap

```bash
# 在线编辑
kubectl edit configmap balance-alert-config -n balance-alert

# 重启 Pod
kubectl rollout restart deployment/balance-alert -n balance-alert
```

### 方式3: 使用 Secret（敏感信息）

```bash
# 将敏感配置（api_key, webhook url）放入 Secret
kubectl create secret generic balance-alert-secret \
  --from-literal=webhook-url="https://..." \
  -n balance-alert
```

## 访问服务

### NodePort 方式

```bash
# 获取 Node IP
kubectl get nodes -o wide

# 访问地址
http://<NodeIP>:30080
```

### Ingress 方式

1. 修改 `ingress.yaml` 中的 host
2. 应用配置：

```bash
kubectl apply -f k8s/ingress.yaml
```

3. 配置 DNS 或本地 hosts
4. 访问：`http://balance-alert.example.com`

### Port-forward（本地测试）

```bash
# Web 界面
kubectl port-forward svc/balance-alert 8080:8080 -n balance-alert

# Metrics（如使用外部 Prometheus）
kubectl port-forward svc/balance-alert 9100:9100 -n balance-alert
```

## Prometheus 集成（可选）

### 方式一：使用提供的配置参考

参考 `prometheus-config.yaml` 中的配置，复制到你的 Prometheus 配置中。

### 方式二：ServiceMonitor（需 prometheus-operator）

```bash
# 应用 ServiceMonitor
kubectl apply -f k8s/servicemonitor.yaml

# 确保 Service 有正确的标签选择器
# 默认已配置，无需修改
```

### 方式三：手动配置 Prometheus

在你的 Prometheus 配置中添加：

```yaml
scrape_configs:
  - job_name: 'balance-alert'
    static_configs:
      - targets: ['balance-alert.balance-alert.svc.cluster.local:9100']
```

### 启用 Service 监控注解（可选）

如需使用 Prometheus 的 Kubernetes SD 自动发现，取消 `service.yaml` 中的注释：

```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "9100"
    prometheus.io/path: "/metrics"
```

## 常用命令

```bash
# 查看资源
kubectl get all -n balance-alert

# 查看 Pod 日志
kubectl logs -f deployment/balance-alert -n balance-alert

# 进入容器
kubectl exec -it deployment/balance-alert -n balance-alert -- /bin/bash

# 查看配置
kubectl get configmap balance-alert-config -n balance-alert -o yaml

# 扩缩容
kubectl scale deployment/balance-alert --replicas=2 -n balance-alert

# 删除所有资源
kubectl delete -f k8s/namespace.yaml
```

## 生产环境建议

1. **镜像管理**
   - 推送到私有镜像仓库
   - 使用具体版本号替代 `latest`

2. **配置安全**
   - API Key 和 Webhook URL 使用 Secret
   - 配置 RBAC 权限

3. **高可用**
   - 设置 `replicas: 2` 或更多
   - 配置 PodDisruptionBudget

4. **资源限制**
   - 根据实际负载调整 resources
   - 配置 HPA 自动扩缩容

5. **持久化**
   - 如需保留日志，使用 PVC 替代 emptyDir
