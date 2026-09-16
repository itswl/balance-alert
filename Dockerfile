# syntax=docker/dockerfile:1
# 多架构通用：不锁定 --platform，由 docker build / buildx 的目标平台决定；
# 基础镜像与 pip 源用 build-arg 覆盖，例如国内环境：
#   docker build \
#     --build-arg BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim \
#     --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple -t balance-alert .
# 一次构建多架构：
#   docker buildx build --platform linux/amd64,linux/arm64 -t <registry>/balance-alert --push .
ARG BASE_IMAGE=python:3.11-slim

# ---------- Stage 1: 依赖装进独立 venv，运行镜像整目录拷走，不依赖 site-packages 路径 ----------
FROM ${BASE_IMAGE} AS builder
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install -r requirements.txt

# ---------- Stage 2: 运行镜像 ----------
FROM ${BASE_IMAGE}
ENV TZ=Asia/Shanghai \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

# 不装任何系统包：官方 python:*-slim 自带 tzdata，TZ 环境变量直接生效（定时任务时刻按它算）；
# 健康检查用 Python 自带的 urllib。换成不带 tzdata 的基础镜像时需自行补上。
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv

# 分层复制项目文件，优化缓存
COPY *.py ./
COPY core ./core
COPY services ./services
COPY providers ./providers
COPY database ./database
COPY web ./web
COPY scripts ./scripts
COPY templates ./templates
COPY static ./static
COPY docker-entrypoint.sh ./

# 非 root 运行
RUN groupadd -r appuser && \
    useradd -r -g appuser -d /app -s /sbin/nologin appuser && \
    mkdir -p /app/logs /app/data && \
    chmod +x /app/docker-entrypoint.sh && \
    chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('WEB_PORT', '8080') + '/live', timeout=5)" || exit 1

EXPOSE 8080 9100
CMD ["/app/docker-entrypoint.sh"]
