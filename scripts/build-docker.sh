#!/bin/bash
# Docker 镜像构建脚本
# 使用 --no-cache 确保获取最新代码

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 默认配置
IMAGE_NAME="${IMAGE_NAME:-balance-alert}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
VERSION=$(git describe --tags --abbrev=0 2>/dev/null || echo "dev")

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Docker 镜像构建${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "镜像名称: ${IMAGE_NAME}"
echo "镜像标签: ${IMAGE_TAG}"
echo "版本: ${VERSION}"
echo "Git Commit: ${GIT_COMMIT}"
echo "构建时间: ${BUILD_DATE}"
echo ""

# 检查是否使用缓存
USE_CACHE=true
if [ "$1" == "--no-cache" ] || [ "$1" == "-n" ]; then
    USE_CACHE=false
    echo -e "${YELLOW}⚠️  将清除所有缓存重新构建${NC}"
    echo ""
fi

# 清理旧的悬空镜像
echo -e "${YELLOW}🧹 清理悬空镜像...${NC}"
docker image prune -f || true

# 构建镜像
echo -e "${GREEN}🔨 开始构建镜像...${NC}"
echo ""

if [ "$USE_CACHE" = false ]; then
    # 无缓存构建
    docker build \
        --no-cache \
        --build-arg BUILD_DATE="${BUILD_DATE}" \
        --build-arg GIT_COMMIT="${GIT_COMMIT}" \
        --build-arg VERSION="${VERSION}" \
        -t "${IMAGE_NAME}:${IMAGE_TAG}" \
        -t "${IMAGE_NAME}:${GIT_COMMIT}" \
        .
else
    # 使用缓存构建
    docker build \
        --build-arg BUILD_DATE="${BUILD_DATE}" \
        --build-arg GIT_COMMIT="${GIT_COMMIT}" \
        --build-arg VERSION="${VERSION}" \
        -t "${IMAGE_NAME}:${IMAGE_TAG}" \
        -t "${IMAGE_NAME}:${GIT_COMMIT}" \
        .
fi

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ 镜像构建成功！${NC}"
    echo ""
    echo "镜像信息:"
    docker images "${IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    echo ""
    echo -e "${GREEN}======================================${NC}"
    echo -e "${GREEN}下一步操作:${NC}"
    echo -e "${GREEN}======================================${NC}"
    echo ""
    echo "1. 运行镜像:"
    echo "   docker run -d -p 8080:8080 -p 9100:9100 --name balance-alert ${IMAGE_NAME}:${IMAGE_TAG}"
    echo ""
    echo "2. 查看日志:"
    echo "   docker logs -f balance-alert"
    echo ""
    echo "3. 推送到仓库:"
    echo "   docker tag ${IMAGE_NAME}:${IMAGE_TAG} your-registry/${IMAGE_NAME}:${IMAGE_TAG}"
    echo "   docker push your-registry/${IMAGE_NAME}:${IMAGE_TAG}"
    echo ""
    echo "4. 验证新界面:"
    echo "   访问 http://localhost:8080"
    echo ""
else
    echo ""
    echo -e "${RED}❌ 镜像构建失败${NC}"
    exit 1
fi
