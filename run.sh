#!/bin/bash

# 余额监控 Docker 管理脚本

case "$1" in
  build)
    echo "构建 Docker 镜像..."
    docker build -t credit-monitor:latest .
    ;;
  
  start)
    echo "启动容器（Web 服务器 + 定时任务）..."
    docker compose up -d
    echo "容器已启动！"
    echo ""
    echo "🌐 Web 界面: http://localhost:8080"
    echo "⏰ 定时任务: 每天 9:00 和 15:00 运行"
    echo ""
    echo "查看容器日志: docker logs -f credit-monitor"
    echo "查看定时任务日志: docker exec credit-monitor cat /app/logs/cron.log"
    ;;
  
  start-web)
    echo "启动 Web 服务器和定时任务..."
    docker compose -f docker compose.web.yml up -d
    echo "容器已启动！"
    echo "🌐 Web 界面: http://localhost:8080"
    echo "📊 实时查看余额: http://localhost:8080"
    echo ""
    echo "查看 Web 日志: docker logs -f credit-monitor-web"
    echo "查看 Cron 日志: docker logs -f credit-monitor-cron"
    ;;
  
  stop)
    echo "停止容器..."
    docker compose down
    docker compose -f docker compose.web.yml down 2>/dev/null
    ;;
  
  web)
    echo "本地运行 Web 服务器（不用 Docker）..."
    echo "🌐 访问地址: http://localhost:8080"
    python3 web_server.py
    ;;
  
  restart)
    echo "重启容器..."
    docker compose restart
    ;;
  
  logs)
    echo "查看容器日志..."
    docker logs -f credit-monitor
    ;;
  
  cron-logs)
    echo "查看定时任务日志..."
    docker exec credit-monitor tail -f /app/logs/cron.log 2>/dev/null || echo "日志文件尚未生成"
    ;;
  
  run-now)
    echo "立即执行一次检查..."
    docker exec credit-monitor python /app/monitor.py
    ;;
  
  shell)
    echo "进入容器 shell..."
    docker exec -it credit-monitor /bin/bash
    ;;
  
  clean)
    echo "清理容器和镜像..."
    docker compose down
    docker rmi credit-monitor:latest
    ;;
  
  *)
    echo "余额监控 Docker 管理脚本"
    echo ""
    echo "用法: $0 {build|start|web|stop|restart|logs|cron-logs|run-now|shell|clean}"
    echo ""
    echo "命令说明:"
    echo "  build      - 构建 Docker 镜像"
    echo "  start      - 启动容器（Web 服务器 + 定时任务）"
    echo "  web        - 本地运行 Web 服务器（不用 Docker）"
    echo "  stop       - 停止容器"
    echo "  restart    - 重启容器"
    echo "  logs       - 查看容器日志"
    echo "  cron-logs  - 查看定时任务执行日志"
    echo "  run-now    - 立即执行一次余额检查"
    echo "  shell      - 进入容器 shell"
    echo "  clean      - 清理容器和镜像"
    echo ""
    echo "示例:"
    echo "  $0 build && $0 start  # 构建并启动服务"
    echo "  $0 web                # 本地运行 Web 服务器"
    echo ""
    exit 1
    ;;
esac
