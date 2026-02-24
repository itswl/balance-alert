#!/usr/bin/env python3
"""
Prometheus Exporter - 暴露监控指标
"""
from prometheus_client import Gauge, Counter, Info, Histogram, generate_latest, CONTENT_TYPE_LATEST
from flask import Response
import json
import os
import time
from datetime import datetime
from logger import get_logger

logger = get_logger('prometheus_exporter')


class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        # 余额/积分指标
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
            ['name', 'cycle_type', 'currency']
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
        
        self.check_success_gauge = Gauge(
            'balance_alert_check_success',
            'Check success status (1=success, 0=failed)',
            ['check_type']
        )
        
        # 项目信息
        self.project_info = Info(
            'balance_alert_project',
            'Project information'
        )

        # ========== 新增关键指标 ==========

        # 1. 执行时间分布（最重要的性能指标）
        self.monitor_execution_time = Histogram(
            'balance_alert_monitor_execution_time_seconds',
            'Monitor execution time distribution',
            buckets=(0.5, 1, 2, 5, 10, 30, 60, 120)
        )

        # 2. Provider API 延迟
        self.provider_api_latency = Histogram(
            'balance_alert_provider_api_latency_seconds',
            'Provider API call latency',
            ['provider', 'status'],
            buckets=(0.1, 0.5, 1, 2, 5, 10, 15, 30)
        )

        # 3. Provider API 调用计数
        self.provider_api_calls = Counter(
            'balance_alert_provider_api_calls_total',
            'Total provider API calls',
            ['provider', 'status']  # status: success/timeout/error
        )

        # 4. 邮箱扫描耗时
        self.email_scan_duration = Histogram(
            'balance_alert_email_scan_duration_seconds',
            'Email scan duration',
            ['mailbox'],
            buckets=(0.5, 1, 2, 5, 10, 30, 60)
        )

        # 5. Webhook 发送耗时
        self.webhook_delivery_time = Histogram(
            'balance_alert_webhook_delivery_time_seconds',
            'Webhook delivery time',
            ['webhook_type', 'status'],
            buckets=(0.1, 0.5, 1, 2, 5, 10)
        )

        # 6. 缓存命中率
        self.cache_hits = Counter(
            'balance_alert_cache_hits_total',
            'Cache hits',
            ['cache_type']  # response_cache/provider_instance_cache
        )

        self.cache_misses = Counter(
            'balance_alert_cache_misses_total',
            'Cache misses',
            ['cache_type']
        )

        # 7. 配置重载计数
        self.config_reload_count = Counter(
            'balance_alert_config_reload_total',
            'Total config reloads'
        )

        # 8. 活跃项目数
        self.active_projects_count = Gauge(
            'balance_alert_active_projects_count',
            'Number of active projects being monitored'
        )

        # 9. 失败检查计数
        self.failed_checks = Counter(
            'balance_alert_failed_checks_total',
            'Total failed checks',
            ['project', 'provider', 'error_type']
        )

        # 10. 熔断器状态
        self.circuit_breaker_state = Gauge(
            'balance_alert_circuit_breaker_state',
            'Circuit breaker state (0=closed, 1=open)',
            ['provider']
        )

        # 11. 后台任务延迟
        self.background_task_lag = Gauge(
            'balance_alert_background_task_lag_seconds',
            'Background task lag from scheduled time'
        )
    
    def update_balance_metrics(self, results):
        """
        更新余额指标
        
        Args:
            results: 余额检查结果列表
        """
        for result in results:
            if not result.get('success'):
                continue
            
            project = result.get('project', 'unknown')
            provider = result.get('provider', 'unknown')
            balance_type = result.get('type', 'unknown')
            
            credits = result.get('credits', 0)
            threshold = result.get('threshold', 0)
            need_alarm = result.get('need_alarm', False)
            
            # 更新指标
            self.balance_gauge.labels(
                project=project,
                provider=provider,
                type=balance_type
            ).set(credits)
            
            self.balance_threshold_gauge.labels(
                project=project,
                provider=provider,
                type=balance_type
            ).set(threshold)
            
            # 计算比例
            if threshold > 0:
                ratio = credits / threshold
            else:
                ratio = 0
            
            self.balance_ratio_gauge.labels(
                project=project,
                provider=provider,
                type=balance_type
            ).set(ratio)
            
            # 状态：1=正常，0=告警
            status = 0 if need_alarm else 1
            self.balance_status_gauge.labels(
                project=project,
                provider=provider,
                type=balance_type
            ).set(status)
        
        # 更新检查时间
        self.last_check_timestamp.labels(check_type='balance').set(time.time())
        self.check_success_gauge.labels(check_type='balance').set(1)
    
    def update_subscription_metrics(self, results):
        """
        更新订阅指标
        
        Args:
            results: 订阅检查结果列表
        """
        for result in results:
            name = result.get('name', 'unknown')
            cycle_type = result.get('cycle_type', 'monthly')
            days_until = result.get('days_until_renewal', 0)
            amount = result.get('amount', 0)
            currency = result.get('currency', 'CNY')
            need_alert = result.get('need_alert', False)
            already_renewed = result.get('already_renewed_in_cycle', False)
            
            # 更新天数
            self.subscription_days_gauge.labels(
                name=name,
                cycle_type=cycle_type
            ).set(days_until)
            
            # 更新金额
            self.subscription_amount_gauge.labels(
                name=name,
                cycle_type=cycle_type,
                currency=currency
            ).set(amount)
            
            # 状态：1=正常，0=需要续费，-1=本周期已续费
            if already_renewed:
                status = -1
            elif need_alert:
                status = 0
            else:
                status = 1
            
            self.subscription_status_gauge.labels(
                name=name,
                cycle_type=cycle_type
            ).set(status)
        
        # 更新检查时间
        self.last_check_timestamp.labels(check_type='subscription').set(time.time())
        self.check_success_gauge.labels(check_type='subscription').set(1)
    
    def update_email_metrics(self, results):
        """
        更新邮箱扫描指标
        
        Args:
            results: 邮箱扫描结果列表
        """
        # 按邮箱统计
        mailbox_stats = {}
        for result in results:
            mailbox = result.get('mailbox', 'unknown')
            if mailbox not in mailbox_stats:
                mailbox_stats[mailbox] = {
                    'total_scanned': 0,
                    'alerts': 0
                }
            mailbox_stats[mailbox]['total_scanned'] += 1
            if result.get('alert_sent', False):
                mailbox_stats[mailbox]['alerts'] += 1
        
        # 更新指标
        for mailbox, stats in mailbox_stats.items():
            self.email_scan_total_counter.labels(mailbox=mailbox).inc(stats['total_scanned'])
            self.email_alert_counter.labels(mailbox=mailbox).inc(stats['alerts'])
        
        # 更新检查时间
        self.last_check_timestamp.labels(check_type='email').set(time.time())
        self.check_success_gauge.labels(check_type='email').set(1)
    
    def record_email_scan(self, mailbox, total_emails, alert_emails):
        """
        记录邮箱扫描（供邮箱扫描器调用）
        
        Args:
            mailbox: 邮箱名称
            total_emails: 扫描的总邮件数
            alert_emails: 发现的告警邮件数
        """
        self.email_scan_total_counter.labels(mailbox=mailbox).inc(total_emails)
        self.email_alert_counter.labels(mailbox=mailbox).inc(alert_emails)
    
    def set_check_failed(self, check_type):
        """
        设置检查失败
        
        Args:
            check_type: 检查类型 (balance/subscription/email)
        """
        self.check_success_gauge.labels(check_type=check_type).set(0)
    
    def get_metrics(self):
        """
        获取所有指标（Prometheus 格式）
        
        Returns:
            bytes: Prometheus 格式的指标数据
        """
        return generate_latest()


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


def metrics_endpoint():
    """
    Prometheus metrics 端点
    
    Returns:
        Flask Response
    """
    return Response(metrics_collector.get_metrics(), mimetype=CONTENT_TYPE_LATEST)


def load_cached_metrics():
    """从缓存文件加载指标数据"""
    cache_file = os.environ.get('CACHE_FILE_PATH', '/tmp/balance_cache.json')
    try:
        # 从 web_server 的缓存读取数据
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # 更新余额指标
            if 'projects' in data:
                metrics_collector.update_balance_metrics(data['projects'])
            
            # 更新订阅指标
            if 'subscriptions' in data:
                metrics_collector.update_subscription_metrics(data['subscriptions'])
            
            return True
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.error(f"加载缓存失败: {e}")
        return False


# ========== 新增指标使用的便捷函数 ==========

def record_monitor_execution(duration_seconds):
    """记录监控执行时间"""
    metrics_collector.monitor_execution_time.observe(duration_seconds)


def record_provider_api_call(provider, status, latency_seconds):
    """
    记录 Provider API 调用
    
    Args:
        provider: Provider 名称 (openrouter, aliyun, volc, etc.)
        status: 调用状态 (success, timeout, error)
        latency_seconds: 延迟时间（秒）
    """
    metrics_collector.provider_api_calls.labels(provider=provider, status=status).inc()
    metrics_collector.provider_api_latency.labels(provider=provider, status=status).observe(latency_seconds)


def record_email_scan(mailbox, duration_seconds):
    """记录邮箱扫描耗时"""
    metrics_collector.email_scan_duration.labels(mailbox=mailbox).observe(duration_seconds)


def record_webhook_delivery(webhook_type, status, duration_seconds):
    """
    记录 Webhook 发送
    
    Args:
        webhook_type: webhook 类型 (feishu, dingtalk, wecom, custom)
        status: 发送状态 (success, timeout, error)
        duration_seconds: 耗时（秒）
    """
    metrics_collector.webhook_delivery_time.labels(
        webhook_type=webhook_type,
        status=status
    ).observe(duration_seconds)


def record_cache_access(cache_type, hit):
    """
    记录缓存访问
    
    Args:
        cache_type: 缓存类型 (response_cache, provider_instance_cache)
        hit: 是否命中 (True/False)
    """
    if hit:
        metrics_collector.cache_hits.labels(cache_type=cache_type).inc()
    else:
        metrics_collector.cache_misses.labels(cache_type=cache_type).inc()


def record_config_reload():
    """记录配置重载"""
    metrics_collector.config_reload_count.inc()


def set_active_projects_count(count):
    """设置活跃项目数"""
    metrics_collector.active_projects_count.set(count)


def record_failed_check(project, provider, error_type):
    """
    记录失败的检查
    
    Args:
        project: 项目名称
        provider: Provider 名称
        error_type: 错误类型 (timeout, api_error, network_error, etc.)
    """
    metrics_collector.failed_checks.labels(
        project=project,
        provider=provider,
        error_type=error_type
    ).inc()


def set_circuit_breaker_state(provider, is_open):
    """
    设置熔断器状态
    
    Args:
        provider: Provider 名称
        is_open: 是否打开 (True=打开, False=关闭)
    """
    metrics_collector.circuit_breaker_state.labels(provider=provider).set(1 if is_open else 0)


def set_background_task_lag(lag_seconds):
    """设置后台任务延迟（秒）"""
    metrics_collector.background_task_lag.set(lag_seconds)


# 导出所有新增的函数
__all__ = [
    'metrics_endpoint',
    'metrics_collector',
    'record_monitor_execution',
    'record_provider_api_call',
    'record_email_scan',
    'record_webhook_delivery',
    'record_cache_access',
    'record_config_reload',
    'set_active_projects_count',
    'record_failed_check',
    'set_circuit_breaker_state',
    'set_background_task_lag',
]
