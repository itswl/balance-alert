#!/bin/bash
# 测试定时任务是否能正常执行

echo "======================================"
echo "测试 cron 定时任务"
echo "======================================"

# 模拟 cron 环境
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export SHELL=/bin/bash

echo ""
echo "1. 测试 Python 路径"
echo "---"
which python3
python3 --version

echo ""
echo "2. 测试监控脚本"
echo "---"
cd /Users/imwl/check_credits
python3 monitor.py --dry-run | head -20

echo ""
echo "======================================"
echo "✅ 测试完成"
echo "======================================"
