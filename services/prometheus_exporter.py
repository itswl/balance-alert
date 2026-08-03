#!/usr/bin/env python3
"""
Prometheus Exporter - 暴露监控指标

指标服务器由 main.py 的 prometheus_client.start_http_server 启动（独立端口）。
"""
import time

from prometheus_client import Counter, Gauge, Histogram

from core.logger import get_logger

logger = get_logger('prometheus_exporter')


class MetricsCollector:
    """指标收集器"""

    def __init__(self):
        # 余额指标
        self.balance_gauge = Gauge(
            'balance_alert_balance',
            'Current balance or credits',
            ['project', 'provider', 'type']
        )

        self.balance_threshold_gauge = Gauge(
            'balance_alert_threshold',
            'Alert threshold',
            ['project', 'provider', 'type']
        )

        self.balance_ratio_gauge = Gauge(
            'balance_alert_ratio',
            'Balance to threshold ratio',
            ['project', 'provider', 'type']
        )

        self.balance_status_gauge = Gauge(
            'balance_alert_status',
            'Balance status (1=ok, 0=alert)',
            ['project', 'provider', 'type']
        )

        # 订阅续费指标
        self.subscription_days_gauge = Gauge(
            'balance_alert_subscription_days',
            'Days until subscription renewal',
            ['name', 'cycle_type']
        )

        self.subscription_amount_gauge = Gauge(
            'balance_alert_subscription_amount',
            'Subscription renewal amount',
            ['name', 'cycle_type']
        )

        self.subscription_status_gauge = Gauge(
            'balance_alert_subscription_status',
            'Subscription status (1=normal, 0=needs_renewal, -1=renewed_in_cycle)',
            ['name', 'cycle_type']
        )

        # 邮箱扫描指标
        self.email_scan_total_counter = Counter(
            'balance_alert_email_scan_total',
            'Total emails scanned',
            ['mailbox']
        )

        self.email_alert_counter = Counter(
            'balance_alert_email_alerts',
            'Total alert emails found',
            ['mailbox']
        )

        # 系统指标
        self.last_check_timestamp = Gauge(
            'balance_alert_last_check_timestamp',
            'Timestamp of last check',
            ['check_type']
        )

        self.active_projects_count = Gauge(
            'balance_alert_active_projects_count',
            'Number of active projects being monitored'
        )

        self.monitor_execution_time = Histogram(
            'balance_alert_monitor_execution_time_seconds',
            'Monitor execution time distribution',
            buckets=(0.5, 1, 2, 5, 10, 30, 60, 120)
        )

    def update_balance_metrics(self, results):
        """更新余额指标"""
        for result in results:
            if not result.get('success'):
                continue

            labels = {
                'project': result.get('project', 'unknown'),
                'provider': result.get('provider', 'unknown'),
                'type': result.get('type', 'unknown'),
            }
            credits = result.get('credits', 0)
            threshold = result.get('threshold', 0)

            self.balance_gauge.labels(**labels).set(credits)
            self.balance_threshold_gauge.labels(**labels).set(threshold)
            self.balance_ratio_gauge.labels(**labels).set(credits / threshold if threshold > 0 else 0)
            self.balance_status_gauge.labels(**labels).set(0 if result.get('need_alarm', False) else 1)

        self.last_check_timestamp.labels(check_type='balance').set(time.time())

    def update_subscription_metrics(self, results):
        """更新订阅指标"""
        for result in results:
            labels = {
                'name': result.get('name', 'unknown'),
                'cycle_type': result.get('cycle_type', 'monthly'),
            }
            already_renewed = result.get('already_renewed', result.get('already_renewed_in_cycle', False))
            if already_renewed:
                status = -1
            elif result.get('need_alert', False):
                status = 0
            else:
                status = 1

            self.subscription_days_gauge.labels(**labels).set(result.get('days_until_renewal', 0))
            self.subscription_amount_gauge.labels(**labels).set(result.get('amount', 0))
            self.subscription_status_gauge.labels(**labels).set(status)

        self.last_check_timestamp.labels(check_type='subscription').set(time.time())

    def record_email_scan(self, mailbox, total_emails, alert_emails):
        """记录邮箱扫描（供邮箱扫描器调用）"""
        self.email_scan_total_counter.labels(mailbox=mailbox).inc(total_emails)
        self.email_alert_counter.labels(mailbox=mailbox).inc(alert_emails)
        self.last_check_timestamp.labels(check_type='email').set(time.time())


# 全局指标收集器实例（延迟初始化，避免重复注册）
_metrics_collector = None


def _get_metrics_collector():
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


class _MetricsProxy:
    """延迟代理，首次访问属性时才创建 MetricsCollector"""
    def __getattr__(self, name):
        return getattr(_get_metrics_collector(), name)


metrics_collector = _MetricsProxy()
