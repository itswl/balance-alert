#!/usr/bin/env python3
"""
余额监控 Web 服务器 - 模块化版本

使用新的模块化架构启动 Web 服务
"""
import os
import signal
import sys
import threading
from web import create_app
from core.state_manager import StateManager
from services.monitor import CreditMonitor
from core.logger import get_logger
from core.config_loader import get_default_config_path, get_enable_web_alarm, get_refresh_interval

logger = get_logger('web_server')

# 优雅关闭事件
_stop_event = threading.Event()
_shutdown_signal_count = 0

# 全局状态管理器和数据检测器
global_state_manager = StateManager()


def _update_balance(state_mgr: StateManager):
    monitor = CreditMonitor(get_default_config_path())
    monitor.run(dry_run=not get_enable_web_alarm())
    state_mgr.update_balance_state(monitor.results)
    return monitor.results


def _update_subscriptions(state_mgr: StateManager):
    if os.environ.get('ENABLE_SUBSCRIPTIONS', 'false').lower() != 'true':
        state_mgr.update_subscription_state([])
        return []

    from services.subscription_checker import SubscriptionChecker
    subscription_checker = SubscriptionChecker(get_default_config_path())
    subscription_results = subscription_checker.check_subscriptions(dry_run=not get_enable_web_alarm())
    state_mgr.update_subscription_state(subscription_results or [])
    return subscription_results or []


def _update_metrics(balance_results, subscription_results):
    if os.environ.get('ENABLE_PROMETHEUS', 'false').lower() != 'true':
        return
    try:
        from services.prometheus_exporter import metrics_collector
        metrics_collector.update_balance_metrics(balance_results)
        metrics_collector.update_subscription_metrics(subscription_results)
    except Exception as e:
        logger.warning(f"更新 Prometheus 指标失败: {e}")

def update_credits(state_mgr: StateManager = global_state_manager):
    """
    后台定时更新余额数据

    Args:
        state_mgr: 状态管理器实例
    """
    while not _stop_event.is_set():
        try:
            logger.info("开始更新数据")

            # 更新余额数据
            balance_results = _update_balance(state_mgr)
            subscription_results = _update_subscriptions(state_mgr)
            _update_metrics(balance_results, subscription_results)
            logger.info("数据更新完成")

        except Exception as e:
            logger.error(f"更新数据失败: {e}", exc_info=True)

        # 根据配置间隔等待
        sleep_seconds = get_refresh_interval()
        logger.info(f"下次更新将在 {sleep_seconds} 秒后")

        # 使用可中断的 sleep
        _stop_event.wait(sleep_seconds)


if __name__ == '__main__':
    # 从环境变量读取端口配置
    web_port = int(os.environ.get('WEB_PORT', '8080'))
    metrics_port = int(os.environ.get('METRICS_PORT', '9100'))

    # 注册信号处理器实现优雅关闭
    def _shutdown_handler(signum, frame):
        global _shutdown_signal_count
        _shutdown_signal_count += 1
        sig_name = signal.Signals(signum).name
        if _shutdown_signal_count > 1:
            logger.warning(f"再次收到 {sig_name} 信号，强制退出")
            os._exit(128 + signum)

        logger.info(f"收到 {sig_name} 信号，正在优雅关闭...")
        _stop_event.set()
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    update_thread = None

    if os.environ.get('ENABLE_DATABASE', 'false').lower() == 'true':
        try:
            from database import init_database
            if init_database():
                logger.info("数据库已初始化")
        except Exception as e:
            logger.warning(f"数据库初始化失败（将跳过历史数据功能）: {e}")

    try:
        # 创建 Flask 应用
        app = create_app(global_state_manager)

        # 启动后台更新线程
        update_thread = threading.Thread(target=update_credits, daemon=True)
        update_thread.start()

        if os.environ.get('ENABLE_PROMETHEUS', 'false').lower() == 'true':
            from prometheus_client import start_http_server
            logger.info("启动 Prometheus Metrics 服务器")
            logger.info(f"Metrics 端点: http://localhost:{metrics_port}/metrics")
            start_http_server(metrics_port)

        # 启动 Flask 服务器
        logger.info(f"\n🚀 余额监控 Web 服务器启动中（模块化版本）...")
        logger.info(f"📊 访问地址: http://localhost:{web_port}")
        if get_enable_web_alarm():
            logger.warning("⚠️  告警模式: 已启用（Web 会发送真实告警）")
        else:
            logger.info("🔕 告警模式: 仅查询（不发送告警，由定时任务负责）")
        logger.info("ℹ️  要启用 Web 告警，请设置环境变量: ENABLE_WEB_ALARM=true")
        logger.info("🔄 核心版默认关闭数据库、订阅、邮箱、Prometheus；需要时用 ENABLE_* 开关启用")
        logger.info("")

        try:
            from waitress import serve
            logger.info("使用 waitress 生产服务器")
            serve(app, host='0.0.0.0', port=web_port)
        except ImportError:
            logger.warning("waitress 未安装，使用 Flask 开发服务器")
            app.run(host='0.0.0.0', port=web_port, debug=False)

    except KeyboardInterrupt:
        logger.info("主进程退出中...")
        sys.exit(0)
    finally:
        # 优雅关闭：通知后台线程停止
        _stop_event.set()
        if update_thread and update_thread.is_alive():
            update_thread.join(timeout=5)
        logger.info("服务已关闭")
