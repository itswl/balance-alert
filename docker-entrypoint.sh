#!/bin/bash
# 容器入口：准备目录与默认配置，然后把进程交给 main.py
# main.py 一个进程里跑 Web 服务、Prometheus 指标和进程内定时任务（看板刷新、定时告警、邮箱扫描）
set -e

mkdir -p /app/logs /app/data

# config.json 只放业务清单；不存在或为空时给一份空清单，密钥、开关等一律走环境变量
if [ ! -s /app/config.json ]; then
    cat > /app/config.json << 'JSON'
{
  "email": [],
  "subscriptions": [],
  "projects": []
}
JSON
    echo "已创建默认 config.json"
fi

echo "Balance Alert 启动，Web: http://localhost:${WEB_PORT:-8080}"
# exec 让 Python 直接成为容器主进程，SIGTERM 原样送达，优雅关闭由 main.py 处理
exec python /app/main.py
