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

# 安装运行时依赖：curl（用于健康检查）。定时任务由 main.py 进程内调度，不再需要 cron。
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

# 从 builder 复制已安装的 Python 包到系统 site-packages
# 这样所有用户都可以访问
COPY --from=builder /root/.local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /root/.local/bin /usr/local/bin

# 复制项目文件（分层复制，优化缓存）
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

# 创建非 root 用户和必要的目录/文件
RUN groupadd -r appuser && \
    useradd -r -g appuser -d /app -s /sbin/nologin appuser && \
    mkdir -p /app/logs /app/data && \
    touch /app/config.json && \
    chmod +x /app/docker-entrypoint.sh && \
    chown -R appuser:appuser /app

# 以非 root 用户运行
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/live || exit 1

# 暴露端口（文档用途）
EXPOSE 8080 9100

CMD ["/app/docker-entrypoint.sh"]
