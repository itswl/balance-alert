# Docker 镜像构建指南

## 🐛 常见问题：镜像是旧界面

### 问题原因

1. **Docker 缓存**：Docker 使用了缓存的中间层，没有复制最新的文件
2. **没有重新构建**：只是重启了容器，而不是重新构建镜像
3. **镜像标签混淆**：使用了旧的镜像标签

### 快速解决

使用 `--no-cache` 重新构建：

```bash
# 方法 1: 使用构建脚本（推荐）
./build-docker.sh --no-cache

# 方法 2: 直接使用 Docker 命令
docker build --no-cache -t balance-alert:latest .

# 方法 3: 快速重建并测试
./rebuild-and-test.sh
```

---

## 📋 完整构建流程

### 1. 清理旧镜像和容器

```bash
# 停止运行的容器
docker stop balance-alert

# 删除容器
docker rm balance-alert

# 删除旧镜像
docker rmi balance-alert:latest

# 清理悬空镜像
docker image prune -f
```

### 2. 构建新镜像

#### 方法 A：使用构建脚本（推荐）

```bash
# 带缓存构建（快速）
./build-docker.sh

# 无缓存构建（确保最新）
./build-docker.sh --no-cache
```

#### 方法 B：手动构建

```bash
# 基础构建
docker build -t balance-alert:latest .

# 无缓存构建（重要！）
docker build --no-cache -t balance-alert:latest .

# 多标签构建
docker build \
  --no-cache \
  -t balance-alert:latest \
  -t balance-alert:$(git rev-parse --short HEAD) \
  -t balance-alert:v1.0.0 \
  .
```

### 3. 验证镜像

```bash
# 查看镜像
docker images balance-alert

# 检查镜像创建时间（应该是刚刚创建）
docker inspect balance-alert:latest | grep Created

# 验证文件内容
docker run --rm balance-alert:latest ls -la /app/templates/
docker run --rm balance-alert:latest ls -la /app/static/
```

### 4. 运行容器

```bash
# 基础运行
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -p 9100:9100 \
  balance-alert:latest

# 带配置文件运行
docker run -d \
  --name balance-alert \
  -p 8080:8080 \
  -p 9100:9100 \
  -v "$(pwd)/.env:/app/.env:ro" \
  -v "$(pwd)/data:/app/data" \
  balance-alert:latest
```

### 5. 验证界面

```bash
# 检查健康状态
curl http://localhost:8080/health

# 访问 Web 界面
open http://localhost:8080

# 或使用 curl 检查 HTML
curl http://localhost:8080 | grep "余额监控中心"
```

---

## 🔍 故障排查

### 问题 1: 界面还是旧的

**原因**: Docker 使用了缓存

**解决**:
```bash
# 1. 完全清理
docker stop balance-alert
docker rm balance-alert
docker rmi balance-alert:latest

# 2. 无缓存重建
docker build --no-cache -t balance-alert:latest .

# 3. 重新运行
docker run -d --name balance-alert -p 8080:8080 balance-alert:latest
```

### 问题 2: 构建时提示文件不存在

**原因**: .dockerignore 排除了某些文件

**解决**:
```bash
# 检查 .dockerignore
cat .dockerignore

# 确保不要忽略 templates/ 和 static/
# 如果被忽略，从 .dockerignore 中删除
```

### 问题 3: 容器启动但界面访问不了

**原因**: 端口映射或服务未启动

**解决**:
```bash
# 检查容器状态
docker ps -a

# 查看日志
docker logs balance-alert

# 检查端口
docker port balance-alert

# 进入容器检查
docker exec -it balance-alert sh
ls -la /app/templates/
ls -la /app/static/
```

### 问题 4: 文件权限问题

**原因**: Docker 构建时的用户权限

**解决**:
```bash
# 在 Dockerfile 中确保正确的权限
# 已经有这行：
# chown -R appuser:appuser /app

# 重新构建
docker build --no-cache -t balance-alert:latest .
```

---

## 📊 镜像层分析

### 查看镜像层

```bash
# 查看镜像历史
docker history balance-alert:latest

# 查看详细信息
docker inspect balance-alert:latest
```

### 验证关键文件层

```bash
# 检查 templates 目录
docker run --rm balance-alert:latest find /app/templates -type f

# 检查 static 目录
docker run --rm balance-alert:latest find /app/static -type f

# 检查特定文件内容
docker run --rm balance-alert:latest cat /app/templates/index.html | head -20
```

---

## 🚀 最佳实践

### 1. 使用多阶段构建（已实现）

```dockerfile
# Dockerfile 中已经使用两阶段构建
FROM python:3.11-slim AS builder  # 构建阶段
FROM python:3.11-slim              # 运行阶段
```

### 2. 合理使用缓存

```bash
# 开发时使用缓存（快速）
docker build -t balance-alert:latest .

# 发布前无缓存（确保最新）
docker build --no-cache -t balance-alert:latest .
```

### 3. 版本管理

```bash
# 使用 Git commit 作为标签
GIT_COMMIT=$(git rev-parse --short HEAD)
docker build -t balance-alert:${GIT_COMMIT} .

# 使用语义化版本
docker build -t balance-alert:v1.0.0 .

# 同时打多个标签
docker build \
  -t balance-alert:latest \
  -t balance-alert:v1.0.0 \
  -t balance-alert:${GIT_COMMIT} \
  .
```

### 4. 镜像大小优化

```bash
# 查看镜像大小
docker images balance-alert

# 清理构建缓存
docker builder prune -a

# 查看镜像层大小
docker history balance-alert:latest --no-trunc
```

---

## 🔄 CI/CD 集成

### GitHub Actions 示例

```yaml
name: Build Docker Image

on:
  push:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build Docker image
        run: |
          docker build \
            --no-cache \
            -t balance-alert:${{ github.sha }} \
            -t balance-alert:latest \
            .

      - name: Test image
        run: |
          docker run -d --name test -p 8080:8080 balance-alert:latest
          sleep 10
          curl -f http://localhost:8080/health
          docker stop test
```

### GitLab CI 示例

```yaml
build:
  stage: build
  script:
    - docker build --no-cache -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker tag $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA $CI_REGISTRY_IMAGE:latest
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
    - docker push $CI_REGISTRY_IMAGE:latest
```

---

## 📝 构建脚本说明

### build-docker.sh

全功能构建脚本：

```bash
# 带缓存构建
./build-docker.sh

# 无缓存构建
./build-docker.sh --no-cache

# 自定义镜像名和标签
IMAGE_NAME=my-app IMAGE_TAG=v2.0 ./build-docker.sh
```

**功能**:
- ✅ 自动清理悬空镜像
- ✅ 添加构建元数据（版本、commit、时间）
- ✅ 多标签支持
- ✅ 彩色输出
- ✅ 显示后续操作提示

### rebuild-and-test.sh

快速重建和测试：

```bash
./rebuild-and-test.sh
```

**功能**:
- ✅ 停止旧容器
- ✅ 无缓存重建
- ✅ 自动启动测试容器
- ✅ 健康检查
- ✅ 显示日志

---

## 💡 常用命令速查

### 构建相关

```bash
# 基础构建
docker build -t balance-alert:latest .

# 无缓存构建（重要！）
docker build --no-cache -t balance-alert:latest .

# 查看构建过程
docker build --progress=plain --no-cache -t balance-alert:latest .

# 指定 Dockerfile
docker build -f Dockerfile.prod -t balance-alert:latest .
```

### 运行相关

```bash
# 后台运行
docker run -d --name balance-alert -p 8080:8080 balance-alert:latest

# 交互式运行（调试用）
docker run -it --rm balance-alert:latest sh

# 挂载配置
docker run -d -p 8080:8080 -v $(pwd)/.env:/app/.env:ro balance-alert:latest

# 查看日志
docker logs -f balance-alert

# 进入容器
docker exec -it balance-alert sh
```

### 清理相关

```bash
# 停止容器
docker stop balance-alert

# 删除容器
docker rm balance-alert

# 删除镜像
docker rmi balance-alert:latest

# 清理所有
docker system prune -a
```

---

## 🎯 确保获得最新界面的完整步骤

```bash
# 1. 完全清理
docker stop balance-alert 2>/dev/null || true
docker rm balance-alert 2>/dev/null || true
docker rmi balance-alert:latest 2>/dev/null || true

# 2. 无缓存重建
docker build --no-cache -t balance-alert:latest .

# 3. 验证镜像时间
docker images balance-alert:latest

# 4. 验证文件
docker run --rm balance-alert:latest cat /app/templates/index.html | grep "余额监控中心"

# 5. 运行容器
docker run -d --name balance-alert -p 8080:8080 balance-alert:latest

# 6. 访问界面
open http://localhost:8080
```

---

**最后更新**: 2026-02-25
**维护者**: Balance Alert Team
