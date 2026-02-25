#!/bin/bash
# 快速重建并测试 Docker 镜像

set -e

IMAGE_NAME="balance-alert"
CONTAINER_NAME="balance-alert-test"

echo "🔄 停止并删除旧容器..."
docker stop ${CONTAINER_NAME} 2>/dev/null || true
docker rm ${CONTAINER_NAME} 2>/dev/null || true

echo ""
echo "🔨 重新构建镜像（无缓存）..."
docker build --no-cache -t ${IMAGE_NAME}:latest . || {
    echo "❌ 构建失败"
    exit 1
}

echo ""
echo "✅ 构建完成"
echo ""
echo "📦 镜像信息:"
docker images ${IMAGE_NAME}:latest

echo ""
echo "🚀 启动测试容器..."
docker run -d \
    --name ${CONTAINER_NAME} \
    -p 8080:8080 \
    -p 9100:9100 \
    -v "$(pwd)/.env:/app/.env:ro" \
    ${IMAGE_NAME}:latest

echo ""
echo "⏳ 等待服务启动..."
sleep 5

echo ""
echo "📋 查看日志:"
docker logs ${CONTAINER_NAME}

echo ""
echo "🔍 健康检查:"
curl -s http://localhost:8080/health | python3 -m json.tool || echo "服务未就绪"

echo ""
echo "✅ 测试完成"
echo ""
echo "📝 后续操作:"
echo "  查看日志: docker logs -f ${CONTAINER_NAME}"
echo "  访问界面: http://localhost:8080"
echo "  停止容器: docker stop ${CONTAINER_NAME}"
echo "  删除容器: docker rm ${CONTAINER_NAME}"
