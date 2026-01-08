FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim

# 安装 cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目文件
COPY . .

# 设置时区为上海
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 创建日志目录
RUN mkdir -p /app/logs

# 复制 crontab 文件并设置定时任务
COPY crontab /etc/cron.d/credit-monitor
RUN chmod 0644 /etc/cron.d/credit-monitor && \
    crontab /etc/cron.d/credit-monitor

# 创建启动脚本
RUN echo '#!/bin/bash\n\
echo "Starting credit monitor services..."\n\
echo ""\n\
echo "🌐 Starting Web Server on port 8080..."\n\
python /app/web_server.py &\n\
WEB_PID=$!\n\
echo "Web Server started with PID: $WEB_PID"\n\
echo ""\n\
echo "⏰ Starting Cron Service..."\n\
service cron start\n\
echo "Cron service started"\n\
echo ""\n\
echo "🚀 Running initial balance check..."\n\
python /app/monitor.py\n\
echo ""\n\
echo "✅ All services started successfully!"\n\
echo ""\n\
echo "📊 Access Web UI: http://localhost:8080"\n\
echo "📋 Cron logs: /app/logs/cron.log"\n\
echo ""\n\
# 保持容器运行\n\
tail -f /dev/null' > /app/start.sh && \
    chmod +x /app/start.sh

# 默认命令：启动 cron 并保持容器运行
CMD ["/app/start.sh"]
