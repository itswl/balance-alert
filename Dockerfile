FROM --platform=linux/amd64 swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim

# 设置时区 + 安装 cron（合并 RUN 减少镜像层数）
ENV TZ=Asia/Shanghai
RUN apt-get update && \
    apt-get install -y --no-install-recommends cron curl && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目文件
COPY . .

# 设置 cron 定时任务 + 创建日志目录 + 赋予启动脚本执行权限
RUN mkdir -p /app/logs && \
    cp /app/crontab /etc/cron.d/credit-monitor && \
    chmod 0644 /etc/cron.d/credit-monitor && \
    crontab /etc/cron.d/credit-monitor && \
    chmod +x /app/start.sh

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD curl -f http://localhost:8080/health || exit 1

CMD ["/app/start.sh"]
