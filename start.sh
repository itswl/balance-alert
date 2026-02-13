#!/bin/bash
echo "Starting credit monitor services..."
echo ""
echo "🌐 Starting Web Server on port 8080..."
python /app/web_server.py &
WEB_PID=$!
echo "Web Server started with PID: $WEB_PID"
echo ""
echo "⏰ Starting Cron Service..."
service cron start
echo "Cron service started"
echo ""
echo "🚀 Running initial balance check..."
python /app/monitor.py
echo ""
echo "✅ All services started successfully!"
echo ""
echo "📊 Access Web UI: http://localhost:8080"
echo "📋 Cron logs: /app/logs/cron.log"
echo ""
# 保持容器运行
tail -f /dev/null
