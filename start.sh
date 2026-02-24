#!/bin/bash
echo "Starting credit monitor services..."
echo ""

# 信号处理：优雅关闭
cleanup() {
    echo "Received shutdown signal, stopping services..."
    if [ -n "$WEB_PID" ]; then
        kill -TERM "$WEB_PID" 2>/dev/null
        wait "$WEB_PID" 2>/dev/null
    fi
    if [ -n "$CRON_PID" ]; then
        kill -TERM "$CRON_PID" 2>/dev/null
        wait "$CRON_PID" 2>/dev/null
    fi
    echo "All services stopped."
    exit 0
}

trap cleanup SIGTERM SIGINT SIGQUIT

echo "🌐 Starting Web Server on port 8080..."
python /app/web_server_modular.py &
WEB_PID=$!
echo "Web Server started with PID: $WEB_PID"
echo ""
echo "⏰ Starting Cron Service (supercronic)..."
supercronic /app/crontab &
CRON_PID=$!
echo "Cron service started with PID: $CRON_PID"
echo ""
echo "🚀 Running initial balance check..."
python /app/monitor.py
echo ""
echo "✅ All services started successfully!"
echo ""
echo "📊 Access Web UI: http://localhost:8080"
echo ""
# 等待 Web 进程，正确转发信号
wait $WEB_PID
