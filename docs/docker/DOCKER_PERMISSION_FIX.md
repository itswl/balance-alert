# Docker 权限问题修复指南

## 🐛 问题：Permission denied: 'config.json'

### 错误信息

```
[Errno 13] Permission denied: 'config.json'
```

### 问题原因

1. **容器使用非 root 用户运行**
   - Docker 容器内使用 `appuser`（非 root）运行
   - 提高安全性，符合最佳实践

2. **config.json 文件不存在或无写入权限**
   - 应用需要写入配置文件（订阅管理、阈值设置等）
   - 文件不存在或权限不正确

3. **数据持久化目录权限问题**
   - SQLite 数据库文件需要写入权限
   - logs 目录需要写入权限

---

## ✅ 解决方案

### 已实施的修复

#### 1. Dockerfile 更新

```dockerfile
# 创建必要目录和文件
RUN groupadd -r appuser && \
    useradd -r -g appuser -d /app -s /sbin/nologin appuser && \
    mkdir -p /app/logs /app/data && \
    touch /app/config.json && \
    chmod +x /app/start.sh /app/docker-entrypoint.sh && \
    chown -R appuser:appuser /app
```

**改进**:
- ✅ 创建 `/app/data` 目录（SQLite 数据库）
- ✅ 创建空的 `config.json` 文件
- ✅ 确保 appuser 拥有所有文件权限

#### 2. 入口脚本 (docker-entrypoint.sh)

新增启动入口脚本，在应用启动前：
- ✅ 创建必要目录
- ✅ 初始化默认配置文件
- ✅ 设置正确的文件权限
- ✅ 显示配置信息

#### 3. .dockerignore 更新

```
data/
config.json
*.db
*.db-journal
```

**原因**:
- 避免复制本地文件到容器（权限冲突）
- 容器内动态创建这些文件

---

## 🚀 使用方法

### 重新构建镜像

```bash
# 无缓存重建（重要！）
docker build --no-cache -t balance-alert:latest .

# 或使用构建脚本
./build-docker.sh --no-cache
```

### 运行容器

#### 方法 1: 使用默认配置

```bash
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -p 9100:9100 \
  balance-alert:latest
```

**说明**:
- 容器会自动创建默认 config.json
- 配置通过 Web 界面管理
- 或通过环境变量配置

#### 方法 2: 挂载配置文件

```bash
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -p 9100:9100 \
  -v "$(pwd)/config.json:/app/config.json" \
  balance-alert:latest
```

**注意**: 确保本地 config.json 权限正确:
```bash
chmod 644 config.json
```

#### 方法 3: 使用环境变量（推荐）

```bash
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -p 9100:9100 \
  -v "$(pwd)/.env:/app/.env:ro" \
  balance-alert:latest
```

**优点**:
- 不需要配置文件
- 环境变量只读挂载（更安全）
- 配置通过 .env 管理

#### 方法 4: 持久化数据（生产推荐）

```bash
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -p 9100:9100 \
  -v balance-alert-data:/app/data \
  -v "$(pwd)/.env:/app/.env:ro" \
  balance-alert:latest
```

**说明**:
- 使用 Docker volume 持久化数据库
- 容器重启/删除后数据保留

---

## 🔍 验证权限

### 检查容器内权限

```bash
# 进入容器
docker exec -it balance-alert sh

# 检查文件权限
ls -la /app/config.json
ls -la /app/data
ls -la /app/logs

# 检查当前用户
whoami  # 应该显示 appuser

# 测试写入权限
echo "test" >> /app/config.json
cat /app/config.json
```

### 检查日志

```bash
# 查看启动日志
docker logs balance-alert

# 应该看到:
# 📁 创建必要目录...
# 📝 创建默认配置文件...
# ✅ 默认配置文件已创建
# 🔐 设置文件权限...
# ✅ 初始化完成，启动服务...
```

---

## 🛠️ 故障排查

### 问题 1: 仍然提示 Permission denied

**检查**:
```bash
docker exec -it balance-alert ls -la /app/
```

**解决**:
```bash
# 1. 停止容器
docker stop balance-alert
docker rm balance-alert

# 2. 删除旧镜像
docker rmi balance-alert:latest

# 3. 清理缓存
docker builder prune -f

# 4. 重新构建（无缓存）
docker build --no-cache -t balance-alert:latest .

# 5. 重新运行
docker run -d --name balance-alert -p 8080:8080 balance-alert:latest
```

### 问题 2: 挂载的配置文件无法写入

**原因**: 宿主机文件权限问题

**解决**:
```bash
# 方法 1: 修改宿主机文件权限
chmod 666 config.json

# 方法 2: 使用环境变量代替配置文件
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -e ENABLE_DATABASE=true \
  -e DATABASE_URL=sqlite:///./data/balance_alert.db \
  balance-alert:latest
```

### 问题 3: 数据库文件权限错误

**检查**:
```bash
docker exec -it balance-alert ls -la /app/data/
```

**解决**:
```bash
# 使用 Docker volume（推荐）
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -v balance-alert-data:/app/data \
  balance-alert:latest

# 或者挂载时设置权限
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -v "$(pwd)/data:/app/data:rw" \
  --user $(id -u):$(id -g) \
  balance-alert:latest
```

### 问题 4: SELinux 权限问题（RHEL/CentOS）

**检查**:
```bash
getenforce  # 如果是 Enforcing
```

**解决**:
```bash
# 临时禁用（测试用）
sudo setenforce 0

# 或添加 :Z 标志
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -v "$(pwd)/data:/app/data:Z" \
  balance-alert:latest
```

---

## 📊 Kubernetes 部署

### 使用 ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: balance-alert-config
data:
  config.json: |
    {
      "settings": {
        "balance_refresh_interval_seconds": 3600
      },
      "projects": []
    }
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: balance-alert
spec:
  template:
    spec:
      containers:
      - name: balance-alert
        image: balance-alert:latest
        volumeMounts:
        - name: config
          mountPath: /app/config.json
          subPath: config.json
        - name: data
          mountPath: /app/data
      volumes:
      - name: config
        configMap:
          name: balance-alert-config
      - name: data
        persistentVolumeClaim:
          claimName: balance-alert-data
```

### 使用 Secret（推荐）

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: balance-alert
        envFrom:
        - secretRef:
            name: balance-alert-secret
        volumeMounts:
        - name: data
          mountPath: /app/data
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: balance-alert-data
```

---

## 💡 最佳实践

### 1. 使用环境变量（推荐）

```bash
# 创建 .env 文件
cat > .env << EOF
ENABLE_DATABASE=true
DATABASE_URL=sqlite:///./data/balance_alert.db
WEBHOOK_URL=https://...
OPENROUTER_API_KEY=sk-...
EOF

# 运行容器
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -v "$(pwd)/.env:/app/.env:ro" \
  -v balance-alert-data:/app/data \
  balance-alert:latest
```

**优点**:
- ✅ 配置与代码分离
- ✅ 易于管理和版本控制
- ✅ 符合 12-Factor App
- ✅ 不需要配置文件权限

### 2. 使用 Docker Volume（持久化）

```bash
# 创建 volume
docker volume create balance-alert-data

# 使用 volume
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -v balance-alert-data:/app/data \
  balance-alert:latest

# 备份 volume
docker run --rm \
  -v balance-alert-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/backup.tar.gz /data
```

### 3. 非 root 用户运行（安全）

```bash
# 已在 Dockerfile 中实现
USER appuser

# 验证
docker exec balance-alert whoami  # 应该是 appuser
```

### 4. 只读挂载敏感配置

```bash
docker run -d \
  --name balance-alert \
  -v "$(pwd)/.env:/app/.env:ro" \  # 只读
  balance-alert:latest
```

---

## 🔄 迁移指南

### 从旧版本迁移

如果你之前使用的是有权限问题的版本：

```bash
# 1. 备份数据
docker cp balance-alert:/app/config.json ./config.json.backup
docker cp balance-alert:/app/data ./data.backup

# 2. 停止并删除旧容器
docker stop balance-alert
docker rm balance-alert

# 3. 删除旧镜像
docker rmi balance-alert:latest

# 4. 重新构建
docker build --no-cache -t balance-alert:latest .

# 5. 使用 volume 运行新容器
docker volume create balance-alert-data
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -v balance-alert-data:/app/data \
  balance-alert:latest

# 6. 恢复数据（如需要）
docker cp ./data.backup/. balance-alert:/app/data/
docker restart balance-alert
```

---

**最后更新**: 2026-02-25
**维护者**: Balance Alert Team
