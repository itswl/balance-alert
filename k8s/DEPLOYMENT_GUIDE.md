# Kubernetes 部署完整指南

本文档介绍如何在 Kubernetes 集群中部署 Balance Alert，包括 SQLite 数据持久化和环境变量配置。

## 📋 目录

- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [部署步骤](#部署步骤)
- [数据持久化](#数据持久化)
- [环境变量](#环境变量)
- [常见问题](#常见问题)

## 🚀 快速开始

### 前置要求

- Kubernetes 集群（v1.19+）
- kubectl 命令行工具
- 已构建的 Docker 镜像

### 一键部署

```bash
# 1. 创建命名空间
kubectl apply -f k8s/namespace.yaml

# 2. 从 .env 创建 Secret
./k8s/create-secret-from-env.sh

# 3. 部署所有资源
kubectl apply -f k8s/
```

## 📝 配置说明

### 文件结构

```
k8s/
├── namespace.yaml              # 命名空间
├── configmap.yaml              # ConfigMap（配置文件，可选）
├── secret.yaml                 # Secret 模板（不要提交敏感信息！）
├── pvc.yaml                    # PersistentVolumeClaim（数据持久化）
├── deployment.yaml             # Deployment（主应用）
├── service.yaml                # Service（服务暴露）
├── ingress.yaml                # Ingress（外部访问）
├── create-secret-from-env.sh   # 从 .env 创建 Secret 的脚本
└── DEPLOYMENT_GUIDE.md         # 本文档
```

### 配置方式

Balance Alert 支持两种配置方式：

1. **环境变量**（推荐）：通过 Secret 注入
2. **配置文件**：通过 ConfigMap 挂载 config.json

推荐使用环境变量方式，更符合 12-Factor App 原则。

## 🔧 部署步骤

### 步骤 1: 创建命名空间

```bash
kubectl apply -f k8s/namespace.yaml
```

### 步骤 2: 创建 Secret

#### 方法 A: 从 .env 文件自动创建（推荐）

```bash
# 1. 确保 .env 文件存在并配置正确
cp .env.example .env
nano .env  # 编辑配置

# 2. 运行脚本创建 Secret
./k8s/create-secret-from-env.sh
```

#### 方法 B: 手动创建

```bash
kubectl create secret generic balance-alert-secret \
  --from-literal=WEBHOOK_URL='https://...' \
  --from-literal=DATABASE_URL='sqlite:///./data/balance_alert.db' \
  --from-literal=OPENROUTER_MAIN_API_KEY='your-key' \
  -n balance-alert
```

### 步骤 3: 创建持久化存储

```bash
# 应用 PVC 配置
kubectl apply -f k8s/pvc.yaml

# 检查 PVC 状态
kubectl get pvc -n balance-alert
```

**注意**：检查你的 Kubernetes 集群是否有默认的 StorageClass：
```bash
kubectl get storageclass
```

### 步骤 4: 部署应用

```bash
# 部署所有资源
kubectl apply -f k8s/

# 检查部署状态
kubectl get pods -n balance-alert
kubectl get svc -n balance-alert
```

### 步骤 5: 验证部署

```bash
# 查看 Pod 日志
kubectl logs -f deployment/balance-alert -n balance-alert

# 测试存活/就绪检查
kubectl exec -it deployment/balance-alert -n balance-alert -- curl localhost:8080/live
kubectl exec -it deployment/balance-alert -n balance-alert -- curl localhost:8080/ready

# 端口转发到本地测试
kubectl port-forward svc/balance-alert -n balance-alert 8080:8080
# 然后访问 http://localhost:8080
```

## 💾 数据持久化

### SQLite 持久化配置

deployment.yaml 中的关键配置：

```yaml
volumeMounts:
  # SQLite 数据库目录挂载
  - name: data
    mountPath: /app/data

volumes:
  # SQLite 数据库持久化存储
  - name: data
    persistentVolumeClaim:
      claimName: balance-alert-data
```

### 数据备份

```bash
# 进入 Pod
kubectl exec -it deployment/balance-alert -n balance-alert -- sh

# 备份数据库
cd /app/data
sqlite3 balance_alert.db .dump > backup.sql

# 或复制整个数据库文件
kubectl cp balance-alert/<pod-name>:/app/data/balance_alert.db ./backup.db -n balance-alert
```

### 迁移到 PostgreSQL

如需更好的高可用性，可以迁移到 PostgreSQL：

```bash
# 1. 部署 PostgreSQL
helm install postgres bitnami/postgresql \
  --set auth.database=balance_alert \
  -n balance-alert

# 2. 更新 Secret
kubectl patch secret balance-alert-secret -n balance-alert \
  --type merge \
  -p '{"stringData":{"DATABASE_URL":"postgresql://postgres:password@postgres-postgresql:5432/balance_alert"}}'

# 3. 重启应用
kubectl rollout restart deployment/balance-alert -n balance-alert
```

## 🔐 环境变量管理

### 查看当前配置

```bash
# 查看 Secret 里的所有 key
kubectl get secret balance-alert-secret -n balance-alert \
  -o jsonpath='{.data}' | jq 'keys'

# 查看解码后的值（小心敏感信息！）
kubectl get secret balance-alert-secret -n balance-alert \
  -o jsonpath='{.data.DATABASE_URL}' | base64 -d
```

### 更新环境变量

```bash
# 方法 1: 重新从 .env 创建（推荐）
./k8s/create-secret-from-env.sh

# 方法 2: 单独更新某个值
kubectl patch secret balance-alert-secret -n balance-alert \
  --type merge \
  -p '{"stringData":{"WEBHOOK_URL":"https://new-webhook-url"}}'

# 重启 Pod 使新配置生效
kubectl rollout restart deployment/balance-alert -n balance-alert
```

## 📊 监控和调试

### 查看日志

```bash
# 实时查看日志
kubectl logs -f deployment/balance-alert -n balance-alert

# 查看最近 100 行
kubectl logs deployment/balance-alert -n balance-alert --tail=100

# 查看之前崩溃的 Pod 日志
kubectl logs deployment/balance-alert -n balance-alert --previous
```

### 进入容器调试

```bash
# 进入容器
kubectl exec -it deployment/balance-alert -n balance-alert -- sh

# 检查环境变量
env | grep DATABASE

# 检查数据目录
ls -la /app/data/

# 测试数据库连接
python3 scripts/test_database.py
```

### 检查资源使用

```bash
# 查看 Pod 资源使用
kubectl top pod -n balance-alert

# 查看 PVC 使用情况
kubectl get pvc -n balance-alert
```

## 🔄 更新和回滚

### 更新应用

```bash
# 1. 构建新镜像
docker build -t balance-alert:v2.0.0 .

# 2. 更新 Deployment
kubectl set image deployment/balance-alert \
  balance-alert=balance-alert:v2.0.0 \
  -n balance-alert

# 3. 查看滚动更新状态
kubectl rollout status deployment/balance-alert -n balance-alert
```

### 回滚操作

```bash
# 查看历史版本
kubectl rollout history deployment/balance-alert -n balance-alert

# 回滚到上一版本
kubectl rollout undo deployment/balance-alert -n balance-alert
```

## 🐛 常见问题

### 1. Pod 无法启动

```bash
# 查看 Pod 状态
kubectl describe pod <pod-name> -n balance-alert

# 查看事件
kubectl get events -n balance-alert --sort-by='.lastTimestamp'

# 常见原因：
# - 镜像拉取失败
# - Secret 不存在
# - PVC 未绑定
```

### 2. PVC 一直 Pending

```bash
# 检查存储类
kubectl get storageclass

# 如果没有默认存储类，需要在 pvc.yaml 中指定
storageClassName: <your-storage-class>

# 或创建本地存储（测试用）
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolume
metadata:
  name: balance-alert-pv
spec:
  capacity:
    storage: 5Gi
  accessModes:
    - ReadWriteOnce
  hostPath:
    path: /data/balance-alert
EOF
```

### 3. 数据丢失

SQLite + PVC 配置下，数据应该是持久化的。如果数据丢失：

```bash
# 检查 PVC 是否正确绑定
kubectl get pvc balance-alert-data -n balance-alert

# 检查挂载点
kubectl exec deployment/balance-alert -n balance-alert -- df -h

# 检查数据文件
kubectl exec deployment/balance-alert -n balance-alert -- ls -la /app/data/
```

### 4. Secret 未生效

```bash
# 检查 Secret 是否存在
kubectl get secret balance-alert-secret -n balance-alert

# 检查 Pod 环境变量
kubectl exec deployment/balance-alert -n balance-alert -- env

# 重启 Pod
kubectl rollout restart deployment/balance-alert -n balance-alert
```

## 🔒 安全建议

1. **不要提交 Secret 到 Git**
   ```bash
   # 添加到 .gitignore
   echo "k8s/secret.yaml" >> .gitignore
   ```

2. **使用 Sealed Secrets**（推荐）
   ```bash
   # 安装 Sealed Secrets Controller
   kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml

   # 加密 Secret
   kubeseal -f k8s/secret.yaml -w k8s/sealed-secret.yaml
   ```

3. **定期轮换密钥**
   ```bash
   # 更新 .env 后重新创建 Secret
   ./k8s/create-secret-from-env.sh
   ```

4. **限制 RBAC 权限**
   ```yaml
   apiVersion: v1
   kind: ServiceAccount
   metadata:
     name: balance-alert
     namespace: balance-alert
   ```

## 📚 相关文档

- [PostgreSQL 配置指南](../docs/POSTGRESQL_SETUP.md)
- [数据库文档](../database/README.md)
- [项目主文档](../README.md)

---

**维护者**: Balance Alert Team
**最后更新**: 2026-02-24
