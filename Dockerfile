# ========================================
# Stage 1: Builder - 构建依赖
# ========================================
FROM --platform=linux/amd64 swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim AS builder

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖到用户目录（不需要 root 权限）
RUN pip install --user --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# ========================================
# Stage 2: Runtime - 最终镜像
# ========================================
FROM --platform=linux/amd64 swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim

# 设置时区
ENV TZ=Asia/Shanghai

# 安装运行时依赖：curl（用于健康检查）+ supercronic（定时任务）
ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 \
    SUPERCRONIC_MIRROR=https://ghp.ci/https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=71b0d58cc53f6bd72cf2f293e09e294b79c666d8 \
    SUPERCRONIC=supercronic-linux-amd64

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    (curl -fsSLO --retry 3 --connect-timeout 30 -o "$SUPERCRONIC" "$SUPERCRONIC_URL" || \
     curl -fsSLO --retry 3 --connect-timeout 30 -o "$SUPERCRONIC" "$SUPERCRONIC_MIRROR") && \
    echo "$SUPERCRONIC_SHA1SUM  $SUPERCRONIC" | sha1sum -c - && \
    chmod +x "$SUPERCRONIC" && \
    mv "$SUPERCRONIC" /usr/local/bin/supercronic && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

# 从 builder 复制已安装的 Python 包
COPY --from=builder /root/.local /root/.local

# 确保 pip 安装的脚本在 PATH 中
ENV PATH=/root/.local/bin:$PATH

# 复制项目文件（分层复制，优化缓存）
COPY *.py ./
COPY providers ./providers
COPY models ./models
COPY templates ./templates
COPY static ./static
COPY start.sh crontab ./

# 创建非 root 用户
RUN groupadd -r appuser && \
    useradd -r -g appuser -d /app -s /sbin/nologin appuser && \
    mkdir -p /app/logs && \
    chmod +x /app/start.sh && \
    chown -R appuser:appuser /app

# 以非 root 用户运行
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 暴露端口（文档用途）
EXPOSE 8080 9100

CMD ["/app/start.sh"]
