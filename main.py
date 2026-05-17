#!/usr/bin/env python3
"""
余额监控 Web 服务器 - 模块化版本

使用新的模块化架构启动 Web 服务
"""
import os
import signal
import sys
import threading
import time
from web import create_app
from core.state_manager import StateManager
from services.monitor import CreditMonitor
from services.subscription_checker import SubscriptionChecker
from services.prometheus_exporter import metrics_collector
from core.config_loader import start_config_watcher, stop_config_watcher
from core.logger import get_logger
from web.utils import get_enable_web_alarm, get_refresh_interval, get_smart_refresh_config
from web.handlers import update_balance_cache, update_subscription_cache
from pathlib import Path

logger = get_logger('web_server')

# 优雅关闭事件
_stop_event = threading.Event()
_shutdown_signal_count = 0

# 全局状态管理器和数据检测器
from database.repository import BalanceRepository, SubscriptionRepository
from sqlalchemy import desc, func, and_
from database.models import BalanceHistory, SubscriptionHistory
from database.engine import get_session

# ======= State Init =======
def init_state_from_db(state_mgr: StateManager):
    """从数据库加载最近的状态，以便重启后 UI 立即可用"""
    session = None
    try:
        session = get_session()
        if not session:
            return
            
        # 1. 恢复 Balance 状态
        # 每个项目取最新的一条记录
        balance_subquery = session.query(
            BalanceHistory.project_id,
            func.max(BalanceHistory.timestamp).label('max_timestamp')
        ).group_by(BalanceHistory.project_id).subquery()
        latest_balances = session.query(BalanceHistory).join(
            balance_subquery,
            and_(
                BalanceHistory.project_id == balance_subquery.c.project_id,
                BalanceHistory.timestamp == balance_subquery.c.max_timestamp
            )
        ).all()
        if latest_balances:
            projects_state = []
            for b in latest_balances:
                projects_state.append({
                    'project': b.project_name,
                    'provider': b.provider,
                    'type': b.balance_type,
                    'success': True, # 假设查到的都是最后成功的，如果不准确也没关系，马上会刷新
                    'credits': b.balance,
                    'threshold': b.threshold,
                    'need_alarm': b.need_alarm,
                    'alarm_sent': False,
                    'error': None
                })
            state_mgr.update_balance_state(projects_state)
            
        # 2. 恢复 Subscription 状态
        sub_subquery = session.query(
            SubscriptionHistory.subscription_id,
            func.max(SubscriptionHistory.timestamp).label('max_timestamp')
        ).group_by(SubscriptionHistory.subscription_id).subquery()
        latest_subs = session.query(SubscriptionHistory).join(
            sub_subquery,
            and_(
                SubscriptionHistory.subscription_id == sub_subquery.c.subscription_id,
                SubscriptionHistory.timestamp == sub_subquery.c.max_timestamp
            )
        ).all()
        if latest_subs:
            subs_state = []
            for s in latest_subs:
                subs_state.append({
                    'name': s.subscription_name,
                    'cycle_type': s.cycle_type,
                    'days_until_renewal': s.days_until_renewal,
                    'amount': s.amount,
                    'need_alert': s.need_renewal,
                    'alert_sent': False,
                    'already_renewed': False,
                    'last_renewed_date': None
                })
            state_mgr.update_subscription_state(subs_state)
            
        logger.info("已从数据库恢复初始状态")
    except Exception as e:
        logger.error(f"从数据库恢复状态失败: {e}")
    finally:
        if session:
            session.close()

global_state_manager = StateManager()


class DataChangeDetector:
    """数据变化检测器（用于智能刷新）"""

    def __init__(self):
        self._previous_data = {}
        self._change_count = {}

    def detect_changes(self, current_data, data_type: str) -> bool:
        """检测数据是否有变化"""
        import hashlib
        import json

        current_hash = hashlib.md5(json.dumps(current_data, sort_keys=True).encode()).hexdigest()
        previous_hash = self._previous_data.get(data_type)

        if previous_hash != current_hash:
            self._previous_data[data_type] = current_hash
            self._change_count[data_type] = self._change_count.get(data_type, 0) + 1
            return True

        return False

    def should_force_refresh(self, data_type: str, threshold_percent: float) -> bool:
        """判断是否需要强制刷新（基于变化率）"""
        # 简化逻辑：暂时总是返回 False
        return False


data_detector = DataChangeDetector()





def update_credits(state_mgr: StateManager = global_state_manager, detector: DataChangeDetector = None):
    """
    后台定时更新余额数据

    Args:
        state_mgr: 状态管理器实例
        detector: 数据变化检测器
    """
    if detector is None:
        detector = data_detector

    while not _stop_event.is_set():
        try:
            # 获取智能刷新配置
            smart_config = get_smart_refresh_config()
            smart_refresh_enabled = smart_config['enabled']

            logger.info(f"开始更新数据 (智能刷新: {'启用' if smart_refresh_enabled else '禁用'})")

            # 更新余额数据
            monitor = CreditMonitor('config.json')
            monitor.run(dry_run=not get_enable_web_alarm())

            # 检测余额数据变化（智能刷新）
            balance_changed = False
            if smart_refresh_enabled:
                balance_changed = detector.detect_changes(monitor.results, 'balance')

            # 更新缓存
            update_balance_cache(monitor.results, state_mgr)

            # 更新订阅数据
            subscription_checker = SubscriptionChecker('config.json')
            subscription_results = subscription_checker.check_subscriptions(dry_run=not get_enable_web_alarm())

            # 检测订阅数据变化（智能刷新）
            subscription_changed = False
            if smart_refresh_enabled and subscription_results:
                subscription_changed = detector.detect_changes(subscription_results, 'subscription')

            # 更新缓存
            update_subscription_cache(subscription_results or [], state_mgr)

            # 更新 Prometheus 指标
            metrics_collector.update_balance_metrics(monitor.results)
            metrics_collector.update_subscription_metrics(subscription_results or [])

            # 智能刷新日志
            if smart_refresh_enabled:
                logger.info(f"数据更新完成 - 余额变化: {'是' if balance_changed else '否'}, "
                           f"订阅变化: {'是' if subscription_changed else '否'}")

        except Exception as e:
            logger.error(f"更新数据失败: {e}", exc_info=True)
            metrics_collector.set_check_failed('balance')

        # 根据配置间隔等待
        sleep_seconds = get_refresh_interval()

        # 智能刷新逻辑
        if smart_config['enabled']:
            # 检查是否需要强制刷新
            force_balance_refresh = detector.should_force_refresh(
                'balance', smart_config['threshold_percent']
            )
            force_subscription_refresh = detector.should_force_refresh(
                'subscription', smart_config['threshold_percent']
            )

            if force_balance_refresh or force_subscription_refresh:
                logger.info(f"达到强制刷新阈值，下次将在 {sleep_seconds} 秒后更新")
            elif balance_changed or subscription_changed:
                logger.info(f"检测到数据变化，下次将在 {sleep_seconds} 秒后更新")
            else:
                logger.info(f"数据无变化，下次将在 {sleep_seconds} 秒后更新")
        else:
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

    # 启动配置文件监听器
    start_config_watcher('config.json')

    # 初始化数据库（如果启用）
    update_thread = None

    try:
        from database import init_database
        if init_database():
            logger.info("✅ 数据库已初始化")
            init_state_from_db(global_state_manager)
    except Exception as e:
        logger.warning(f"数据库初始化失败（将跳过历史数据功能）: {e}")

    try:
        # 创建 Flask 应用
        app = create_app(global_state_manager)

        # 启动后台更新线程
        update_thread = threading.Thread(target=update_credits, daemon=True)
        update_thread.start()

        # 启动独立的 Prometheus Metrics 服务器
        from prometheus_client import start_http_server
        logger.info(f"📊 启动 Prometheus Metrics 服务器...")
        logger.info(f"🔗 Metrics 端点: http://localhost:{metrics_port}/metrics")
        start_http_server(metrics_port)

        # 启动 Flask 服务器
        logger.info(f"\n🚀 余额监控 Web 服务器启动中（模块化版本）...")
        logger.info(f"📊 访问地址: http://localhost:{web_port}")
        if get_enable_web_alarm():
            logger.warning("⚠️  告警模式: 已启用（Web 会发送真实告警）")
        else:
            logger.info("🔕 告警模式: 仅查询（不发送告警，由定时任务负责）")
        logger.info("ℹ️  要启用 Web 告警，请设置环境变量: ENABLE_WEB_ALARM=true")
        logger.info("🔄 配置加载已简化：每次读取时生效（不做文件监听）")
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
        # 停止配置文件监听器
        stop_config_watcher()
        logger.info("服务已关闭")
