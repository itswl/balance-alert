#!/bin/bash
# 容器入口：准备目录与默认配置，然后把进程交给 main.py
# main.py 一个进程里跑 Web 服务、Prometheus 指标和进程内定时任务（看板刷新、定时告警、邮箱扫描）
set -e

mkdir -p /app/logs /app/data

# config.json 是可选的：项目可以由 {PROVIDER}_API_KEY 自动发现，也可以在页面上维护。
# docker-compose 把它作为文件挂载，宿主机上没有时 Docker 会建成目录，这里清掉以免误判。
if [ -d /app/config.json ]; then
    rmdir /app/config.json 2>/dev/null || true
fi

echo "Balance Alert 启动，Web: http://localhost:${WEB_PORT:-8080}"
# exec 让 Python 直接成为容器主进程，SIGTERM 原样送达，优雅关闭由 main.py 处理
exec python /app/main.py
