#!/usr/bin/env python3
"""
余额监控 Web 服务器

一个进程里跑三件事：Flask Web / API、Prometheus 指标、进程内定时任务。
定时任务以前由容器里的 cron 起独立进程执行，那些进程里记的指标 Prometheus 抓不到，
现在统一收进这个进程：

- dashboard_refresh  每 BALANCE_REFRESH_INTERVAL_SECONDS 刷新看板（默认只查不发告警，见 ENABLE_WEB_ALARM）
- alert_check        每天 ALERT_SCHEDULE 时刻做余额 + 订阅检查并发送真实告警
- email_scan         每天 EMAIL_SCAN_SCHEDULE 时刻扫描邮箱并发送真实告警
- weekly_report      每周 WEEKLY_REPORT_SCHEDULE 时刻推送一次周报
"""
import os
import signal
import threading
from typing import Any, Dict, List

from web import create_app
from core.scheduler import Job, JobScheduler
from core.state_manager import StateManager
from services.monitor import run_credit_monitor
from services.prometheus_exporter import metrics_collector
from core.logger import get_logger
from core.config_loader import get_default_config_path, get_refresh_interval
from core.settings import get_settings

logger = get_logger('web_server')

# 优雅关闭事件
_stop_event = threading.Event()
_shutdown_signal_count = 0

# 全局状态管理器
global_state_manager = StateManager()


# ---------- 任务体：更新状态 + 指标，返回给 /api/jobs 看的摘要 ----------

def refresh_balances(state_mgr: StateManager, dry_run: bool) -> Dict[str, Any]:
    """检查全部项目余额，写入看板状态与指标"""
    result = run_credit_monitor(get_default_config_path(), dry_run=dry_run)
    if not result.get('success'):
        raise RuntimeError(result.get('error') or '余额检查失败')

    results = result.get('results') or []
    state_mgr.update_balance_state(results)
    metrics_collector.update_balance_metrics(results)
    return {
        'projects': len(results),
        'failed': sum(1 for r in results if not r.get('success')),
        'need_alarm': sum(1 for r in results if r.get('need_alarm')),
        'dry_run': dry_run,
    }


def refresh_subscriptions(state_mgr: StateManager, dry_run: bool) -> Dict[str, Any]:
    """检查订阅续费，写入看板状态与指标；功能未启用时清空"""
    if not get_settings().enable_subscriptions:
        state_mgr.update_subscription_state([])
        metrics_collector.update_subscription_metrics([])
        return {'subscriptions': 0, 'enabled': False}

    from services.subscription_checker import SubscriptionChecker
    results = SubscriptionChecker(get_default_config_path()).check_subscriptions(dry_run=dry_run) or []
    state_mgr.update_subscription_state(results)
    metrics_collector.update_subscription_metrics(results)
    return {
        'subscriptions': len(results),
        'need_alert': sum(1 for r in results if r.get('need_alert')),
        'dry_run': dry_run,
    }


def scan_mailboxes(state_mgr: StateManager, days: int, dry_run: bool) -> Dict[str, Any]:
    """扫描所有启用的邮箱；扫描器内部会更新邮箱指标"""
    from services.email_scanner import EmailScanner
    scanner = EmailScanner(get_default_config_path())
    if not scanner.email_configs:
        return {'mailboxes': 0, 'skipped': '未配置邮箱'}

    summary = scanner.scan_emails(days=days, dry_run=dry_run)
    state_mgr.update_email_state(summary)
    return {
        'mailboxes': len(summary['mailboxes']),
        'failed_mailboxes': sum(1 for m in summary['mailboxes'] if m.get('error')),
        'emails': summary['total_emails'],
        'alerts': summary['total_alerts'],
        'alerts_sent': summary['alerts_sent'],
        'dry_run': dry_run,
    }


def send_weekly_report(state_mgr: StateManager) -> Dict[str, Any]:
    """汇总本周余额、消耗、跑道、订阅、邮箱，推一张周报卡片"""
    from services import weekly_report
    summary = weekly_report.build(
        state_mgr.get_balance_state(), state_mgr.get_subscription_state(), state_mgr.get_email_state()
    )
    sent = weekly_report.send(summary)
    return {
        'accounts': summary['accounts']['total'],
        'consumed': summary['total_consumed'],
        'upcoming_amount': summary['upcoming_amount'],
        'sent': sent,
    }


def build_jobs(state_mgr: StateManager) -> List[Job]:
    settings = get_settings()

    def dashboard_refresh():
        dry_run = not get_settings().enable_web_alarm
        balance = refresh_balances(state_mgr, dry_run=dry_run)
        subs = refresh_subscriptions(state_mgr, dry_run=dry_run)
        return {**balance, 'subscriptions': subs['subscriptions']}

    def alert_check():
        balance = refresh_balances(state_mgr, dry_run=False)
        subs = refresh_subscriptions(state_mgr, dry_run=False)
        return {**balance, 'subscriptions': subs['subscriptions'], 'need_alert': subs.get('need_alert', 0)}

    def email_scan():
        return scan_mailboxes(state_mgr, days=get_settings().email_scan_days, dry_run=False)

    report_weekdays, report_times = settings.weekly_report_plan
    web_alarm_note = '会发送真实告警' if settings.enable_web_alarm else '只查不发告警'
    return [
        Job('dashboard_refresh', dashboard_refresh,
            description=f'刷新看板的余额与订阅状态（{web_alarm_note}）',
            interval_seconds=get_refresh_interval(), run_at_start=True),
        Job('alert_check', alert_check,
            description='余额与订阅告警检查，发送真实通知',
            daily_times=settings.alert_schedule_times),
        Job('email_scan', email_scan,
            description=f'扫描邮箱最近 {settings.email_scan_days} 天的欠费 / 续费邮件，发送真实通知',
            daily_times=settings.email_scan_schedule_times),
        Job('weekly_report', lambda: send_weekly_report(state_mgr),
            description='推送一周的消耗、跑道与待续费汇总',
            daily_times=report_times, weekdays=report_weekdays),
    ]


def _make_result_handler(state_mgr: StateManager):
    def handle(job: Job, result) -> None:
        state_mgr.record_job_run(
            job.name,
            success=result.success,
            started_at=result.started_at,
            duration_seconds=result.duration_seconds,
            error=result.error,
            detail=result.detail,
            next_run=job.next_run,
        )
        metrics_collector.record_job_run(job.name, result.success, result.duration_seconds, result.started_at)
    return handle


def start_scheduler(state_mgr: StateManager) -> JobScheduler:
    jobs = build_jobs(state_mgr)
    scheduler = JobScheduler(jobs, stop_event=_stop_event, on_result=_make_result_handler(state_mgr))
    for job in jobs:
        state_mgr.register_job(
            job.name,
            description=job.description,
            schedule=job.schedule_text(),
            enabled=job.enabled,
            next_run=job.next_run,
        )
        logger.info(f"定时任务 {job.name}: {job.schedule_text()} — {job.description}")
    scheduler.start()
    return scheduler


def _install_signal_handlers() -> None:
    """SIGTERM / SIGINT 优雅关闭，第二次信号强制退出"""
    def handler(signum, frame):
        global _shutdown_signal_count
        _shutdown_signal_count += 1
        sig_name = signal.Signals(signum).name
        if _shutdown_signal_count > 1:
            logger.warning(f"再次收到 {sig_name} 信号，强制退出")
            os._exit(128 + signum)
        logger.info(f"收到 {sig_name} 信号，正在优雅关闭...")
        _stop_event.set()
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def _init_database() -> None:
    try:
        from database import init_database
        if init_database():
            logger.info("数据库已初始化")
    except Exception as e:
        logger.warning(f"数据库初始化失败（将跳过历史数据功能）: {e}")


def _serve(app, port: int) -> None:
    try:
        from waitress import serve
    except ImportError:
        logger.warning("waitress 未安装，使用 Flask 开发服务器")
        app.run(host='0.0.0.0', port=port, debug=False)
        return
    serve(app, host='0.0.0.0', port=port)


def main() -> None:
    settings = get_settings()
    _install_signal_handlers()
    if settings.enable_database:
        _init_database()

    scheduler = None
    try:
        app = create_app(global_state_manager)
        scheduler = start_scheduler(global_state_manager)

        if settings.enable_prometheus:
            from prometheus_client import start_http_server
            start_http_server(settings.metrics_port)
            logger.info(f"Prometheus 指标: http://localhost:{settings.metrics_port}/metrics")

        logger.info(f"Web 服务: http://localhost:{settings.web_port}")
        if settings.enable_web_alarm:
            logger.warning("看板刷新会发送真实告警（ENABLE_WEB_ALARM=true）")
        else:
            logger.info("看板刷新只查不发告警，真实告警由 alert_check / email_scan 定时任务发送")
        _serve(app, settings.web_port)
    except KeyboardInterrupt:
        logger.info("主进程退出中...")
    finally:
        _stop_event.set()
        if scheduler is not None:
            scheduler.stop(timeout=5)
        logger.info("服务已关闭")


if __name__ == '__main__':
    main()
