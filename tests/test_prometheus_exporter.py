"""
Prometheus 导出器测试 — 每个用例用独立 registry，避免默认注册表重复注册
"""
import time

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from services.prometheus_exporter import MetricsCollector


@pytest.fixture
def registry():
    return CollectorRegistry()


@pytest.fixture
def collector(registry):
    return MetricsCollector(registry=registry)


def value(registry, metric, **labels):
    return registry.get_sample_value(metric, labels or None)


def _project(name, credits=100.0, threshold=50.0, success=True, provider='openrouter',
             type_='credits', need_alarm=False):
    result = {'project': name, 'provider': provider, 'type': type_, 'success': success, 'need_alarm': need_alarm}
    if success:
        result.update({'credits': credits, 'threshold': threshold})
    else:
        result['error'] = 'boom'
    return result


class TestBalanceMetrics:

    def test_sets_all_gauges(self, collector, registry):
        collector.update_balance_metrics([_project('A', credits=100, threshold=50)])
        labels = {'project': 'A', 'provider': 'openrouter', 'type': 'credits'}
        assert value(registry, 'balance_alert_balance', **labels) == 100
        assert value(registry, 'balance_alert_threshold', **labels) == 50
        assert value(registry, 'balance_alert_ratio', **labels) == pytest.approx(2.0)
        assert value(registry, 'balance_alert_status', **labels) == 1
        assert value(registry, 'balance_alert_check_status', **labels) == 1
        assert value(registry, 'balance_alert_last_check_timestamp', check_type='balance') == pytest.approx(time.time(), abs=5)

    def test_alarm_and_zero_threshold(self, collector, registry):
        collector.update_balance_metrics([_project('A', credits=5, threshold=0, need_alarm=True)])
        labels = {'project': 'A', 'provider': 'openrouter', 'type': 'credits'}
        assert value(registry, 'balance_alert_status', **labels) == 0
        assert value(registry, 'balance_alert_ratio', **labels) == 0  # 阈值 0 不做除法

    def test_removed_project_is_pruned_from_every_gauge(self, collector, registry):
        collector.update_balance_metrics([_project('A'), _project('B')])
        collector.update_balance_metrics([_project('A')])
        b = {'project': 'B', 'provider': 'openrouter', 'type': 'credits'}
        for name in ('balance_alert_balance', 'balance_alert_threshold', 'balance_alert_ratio',
                     'balance_alert_status', 'balance_alert_check_status'):
            assert value(registry, name, **b) is None, name
        assert value(registry, 'balance_alert_balance', project='A', provider='openrouter', type='credits') == 100

    def test_type_change_prunes_old_series(self, collector, registry):
        collector.update_balance_metrics([_project('A', type_='credits')])
        collector.update_balance_metrics([_project('A', type_='quota', credits=98.7, threshold=10)])
        assert value(registry, 'balance_alert_balance', project='A', provider='openrouter', type='credits') is None
        assert value(registry, 'balance_alert_balance', project='A', provider='openrouter', type='quota') == pytest.approx(98.7)

    def test_failed_check_keeps_last_balance(self, collector, registry):
        collector.update_balance_metrics([_project('A', credits=100)])
        collector.update_balance_metrics([_project('A', success=False)])
        labels = {'project': 'A', 'provider': 'openrouter', 'type': 'credits'}
        assert value(registry, 'balance_alert_balance', **labels) == 100
        assert value(registry, 'balance_alert_check_status', **labels) == 0

    def test_failed_check_without_history_has_no_balance(self, collector, registry):
        collector.update_balance_metrics([_project('A', success=False)])
        labels = {'project': 'A', 'provider': 'openrouter', 'type': 'credits'}
        assert value(registry, 'balance_alert_balance', **labels) is None
        assert value(registry, 'balance_alert_check_status', **labels) == 0

    def test_empty_results_clear_everything(self, collector, registry):
        collector.update_balance_metrics([_project('A')])
        collector.update_balance_metrics([])
        assert value(registry, 'balance_alert_balance', project='A', provider='openrouter', type='credits') is None


class TestSubscriptionMetrics:

    def test_status_mapping_and_prune(self, collector, registry):
        collector.update_subscription_metrics([
            {'name': 'Netflix', 'cycle_type': 'monthly', 'days_until_renewal': 3, 'amount': 15.99, 'need_alert': True},
            {'name': 'Domain', 'cycle_type': 'yearly', 'days_until_renewal': 100, 'amount': 88, 'already_renewed': True},
            {'name': 'Spotify', 'cycle_type': 'monthly', 'days_until_renewal': 20, 'amount': 10},
        ])
        assert value(registry, 'balance_alert_subscription_status', name='Netflix', cycle_type='monthly') == 0
        assert value(registry, 'balance_alert_subscription_status', name='Domain', cycle_type='yearly') == -1
        assert value(registry, 'balance_alert_subscription_status', name='Spotify', cycle_type='monthly') == 1
        assert value(registry, 'balance_alert_subscription_days', name='Netflix', cycle_type='monthly') == 3
        assert value(registry, 'balance_alert_subscription_amount', name='Domain', cycle_type='yearly') == 88

        collector.update_subscription_metrics([{'name': 'Spotify', 'cycle_type': 'monthly', 'days_until_renewal': 19, 'amount': 10}])
        assert value(registry, 'balance_alert_subscription_days', name='Netflix', cycle_type='monthly') is None
        assert value(registry, 'balance_alert_subscription_days', name='Spotify', cycle_type='monthly') == 19


class TestEmailMetrics:

    def _summary(self, *mailboxes):
        return {'mailboxes': list(mailboxes), 'results': []}

    def test_gauges_reflect_last_scan_and_counters_accumulate(self, collector, registry):
        collector.update_email_metrics(self._summary(
            {'name': 'A', 'total_emails': 10, 'alert_count': 2, 'error': None},
            {'name': 'B', 'total_emails': 0, 'alert_count': 0, 'error': 'login failed'},
        ))
        assert value(registry, 'balance_alert_email_mailbox_status', mailbox='A') == 1
        assert value(registry, 'balance_alert_email_mailbox_status', mailbox='B') == 0
        assert value(registry, 'balance_alert_email_last_scan_emails', mailbox='A') == 10
        assert value(registry, 'balance_alert_email_last_scan_alerts', mailbox='A') == 2
        assert value(registry, 'balance_alert_email_scan_total', mailbox='A') == 10
        assert value(registry, 'balance_alert_email_alerts_total', mailbox='A') == 2

        collector.update_email_metrics(self._summary({'name': 'A', 'total_emails': 5, 'alert_count': 1, 'error': None}))
        assert value(registry, 'balance_alert_email_last_scan_emails', mailbox='A') == 5   # Gauge 取上次
        assert value(registry, 'balance_alert_email_scan_total', mailbox='A') == 15        # Counter 累计
        assert value(registry, 'balance_alert_email_alerts_total', mailbox='A') == 3
        # B 不在本次扫描里：Gauge 清掉，Counter 保留
        assert value(registry, 'balance_alert_email_mailbox_status', mailbox='B') is None
        assert value(registry, 'balance_alert_email_scan_total', mailbox='B') == 0
        assert value(registry, 'balance_alert_last_check_timestamp', check_type='email') == pytest.approx(time.time(), abs=5)

    def test_empty_summary_is_safe(self, collector, registry):
        collector.update_email_metrics({})
        collector.update_email_metrics(None)
        assert value(registry, 'balance_alert_last_check_timestamp', check_type='email') is not None


class TestJobAndNotificationMetrics:

    def test_job_run_success_then_failure(self, collector, registry):
        from datetime import datetime, timezone
        first = datetime(2026, 9, 14, 1, 0, tzinfo=timezone.utc)
        second = datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc)
        collector.record_job_run('alert_check', True, 1.5, first)
        collector.record_job_run('alert_check', False, 0.2, second)

        assert value(registry, 'balance_alert_job_last_status', task='alert_check') == 0
        assert value(registry, 'balance_alert_job_last_run_timestamp', task='alert_check') == second.timestamp()
        assert value(registry, 'balance_alert_job_last_success_timestamp', task='alert_check') == first.timestamp()
        assert value(registry, 'balance_alert_job_last_duration_seconds', task='alert_check') == pytest.approx(0.2)
        assert value(registry, 'balance_alert_job_runs_total', task='alert_check', status='success') == 1
        assert value(registry, 'balance_alert_job_runs_total', task='alert_check', status='failed') == 1

    def test_notification_counter(self, collector, registry):
        collector.record_notification('balance', True)
        collector.record_notification('balance', True)
        collector.record_notification('email', False)
        assert value(registry, 'balance_alert_notifications_total', kind='balance', status='success') == 2
        assert value(registry, 'balance_alert_notifications_total', kind='email', status='failed') == 1

    def test_exposition_uses_total_suffix_and_task_label(self, collector, registry):
        collector.record_notification('balance', True)
        collector.record_job_run('email_scan', True, 0.1)
        collector.update_email_metrics({'mailbox': [], 'mailboxes': [{'name': 'A', 'total_emails': 1, 'alert_count': 1}]})
        text = generate_latest(registry).decode()
        assert 'balance_alert_notifications_total{kind="balance",status="success"}' in text
        assert 'balance_alert_job_runs_total{status="success",task="email_scan"}' in text
        assert 'balance_alert_email_alerts_total{mailbox="A"}' in text
        assert 'exported_job' not in text and '{job=' not in text
