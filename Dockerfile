FROM --platform=linux/amd64 swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim

# 设置时区 + 安装 supercronic（无需 root 运行 cron）
ENV TZ=Asia/Shanghai
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
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目文件
COPY . .

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# 创建日志目录 + 赋予启动脚本执行权限
RUN mkdir -p /app/logs && \
    chmod +x /app/start.sh && \
    chown -R appuser:appuser /app

# 以非 root 用户运行
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD curl -f http://localhost:8080/health || exit 1

CMD ["/app/start.sh"]
