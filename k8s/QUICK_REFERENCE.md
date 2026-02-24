# Kubernetes 快速参考

## 🚀 快速命令

### 部署

```bash
# 完整部署流程
kubectl apply -f k8s/namespace.yaml
./k8s/create-secret-from-env.sh
kubectl apply -f k8s/

# 或使用 kustomize
kubectl apply -k k8s/
```

### 查看状态

```bash
# 查看所有资源
kubectl get all -n balance-alert

# 查看 Pod
kubectl get pods -n balance-alert -w

# 查看日志
kubectl logs -f deployment/balance-alert -n balance-alert

# 查看 PVC
kubectl get pvc -n balance-alert
```

### 进入容器

```bash
# 交互式 Shell
kubectl exec -it deployment/balance-alert -n balance-alert -- sh

# 执行单条命令
kubectl exec deployment/balance-alert -n balance-alert -- env | grep DATABASE
```

### 端口转发

```bash
# Web 界面
kubectl port-forward svc/balance-alert -n balance-alert 8080:8080

# Prometheus metrics
kubectl port-forward svc/balance-alert -n balance-alert 9100:9100
```

### 更新配置

```bash
# 更新 Secret
./k8s/create-secret-from-env.sh
kubectl rollout restart deployment/balance-alert -n balance-alert

# 查看滚动更新状态
kubectl rollout status deployment/balance-alert -n balance-alert
```

### 数据备份

```bash
# 备份数据库
POD=$(kubectl get pod -n balance-alert -l app=balance-alert -o jsonpath='{.items[0].metadata.name}')
kubectl cp balance-alert/$POD:/app/data/balance_alert.db ./backup-$(date +%Y%m%d).db
```

### 清理

```bash
# 删除所有资源
kubectl delete namespace balance-alert

# 或删除特定资源
kubectl delete -f k8s/
```

## 📊 关键配置点

### SQLite 数据持久化

```yaml
# pvc.yaml - 持久化存储声明
storage: 5Gi

# deployment.yaml - 卷挂载
volumeMounts:
  - name: data
    mountPath: /app/data

volumes:
  - name: data
    persistentVolumeClaim:
      claimName: balance-alert-data
```

### 环境变量配置

```yaml
# deployment.yaml - 从 Secret 加载
envFrom:
  - secretRef:
      name: balance-alert-secret
```

### 单副本模式（SQLite）

```yaml
# deployment.yaml
spec:
  replicas: 1
  strategy:
    type: Recreate  # 重要！避免并发访问数据库
```

## 🔧 故障排查

```bash
# Pod 无法启动
kubectl describe pod <pod-name> -n balance-alert
kubectl get events -n balance-alert --sort-by='.lastTimestamp'

# PVC 未绑定
kubectl describe pvc balance-alert-data -n balance-alert
kubectl get pv

# Secret 问题
kubectl get secret balance-alert-secret -n balance-alert
kubectl describe secret balance-alert-secret -n balance-alert

# 数据库连接测试
kubectl exec deployment/balance-alert -n balance-alert -- \
  python3 -c "from database.engine import get_engine; print(get_engine())"
```

## 📝 文件清单

- ✅ `namespace.yaml` - 命名空间
- ✅ `secret.yaml` - Secret 模板（使用脚本创建，不要提交）
- ✅ `pvc.yaml` - 持久化存储（5Gi SQLite）
- ✅ `deployment.yaml` - 应用部署（单副本 + 环境变量）
- ✅ `service.yaml` - 服务暴露
- ⚙️ `configmap.yaml` - 配置文件（可选）
- ⚙️ `ingress.yaml` - 外部访问（可选）
- ⚙️ `pdb.yaml` - 高可用配置（可选）
- 🛠️ `create-secret-from-env.sh` - Secret 创建脚本

---

**详细文档**: [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)
