#!/usr/bin/env python3
"""
Prometheus Exporter - 暴露监控指标
"""
from prometheus_client import Gauge, Counter, Info, generate_latest, CONTENT_TYPE_LATEST
from flask import Response
import json
import os
import time
from datetime import datetime


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


# 全局指标收集器实例
metrics_collector = MetricsCollector()


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
        print(f"加载缓存失败: {e}")
        return False
