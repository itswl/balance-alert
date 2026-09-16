"""
main.py 任务装配测试：三个定时任务的计划、任务体对状态与指标的更新
"""
from datetime import datetime, time as dtime, timezone
from unittest.mock import MagicMock, patch

import pytest

import main
from core.scheduler import Job, JobResult
from core.state_manager import StateManager


@pytest.fixture
def state():
    return StateManager()


@pytest.fixture
def metrics():
    fake = MagicMock()
    with patch.object(main, 'metrics_collector', fake):
        yield fake


class TestBuildJobs:

    def test_default_schedules(self, state, monkeypatch):
        for key in ('ALERT_SCHEDULE', 'EMAIL_SCAN_SCHEDULE', 'WEEKLY_REPORT_SCHEDULE'):
            monkeypatch.delenv(key, raising=False)
        jobs = {job.name: job for job in main.build_jobs(state)}
        assert set(jobs) == {'dashboard_refresh', 'alert_check', 'email_scan', 'weekly_report'}
        assert jobs['dashboard_refresh'].run_at_start is True
        assert jobs['dashboard_refresh'].interval_seconds == 3600
        assert jobs['alert_check'].daily_times == [dtime(9, 0), dtime(15, 0)]
        assert jobs['email_scan'].daily_times == [dtime(10, 0)]
        assert jobs['weekly_report'].daily_times == [dtime(9, 0)]
        assert jobs['weekly_report'].weekdays == {1}   # 每周一

    def test_schedules_follow_env_and_can_be_disabled(self, state, monkeypatch):
        monkeypatch.setenv('ALERT_SCHEDULE', 'off')
        monkeypatch.setenv('EMAIL_SCAN_SCHEDULE', '08:00,20:00')
        monkeypatch.setenv('BALANCE_REFRESH_INTERVAL_SECONDS', '600')
        jobs = {job.name: job for job in main.build_jobs(state)}
        assert jobs['alert_check'].enabled is False
        assert jobs['email_scan'].daily_times == [dtime(8, 0), dtime(20, 0)]
        assert jobs['dashboard_refresh'].interval_seconds == 600

    def test_weekly_report_can_be_disabled(self, state, monkeypatch):
        monkeypatch.setenv('WEEKLY_REPORT_SCHEDULE', 'off')
        jobs = {job.name: job for job in main.build_jobs(state)}
        assert jobs['weekly_report'].enabled is False


class TestJobBodies:
    results = [
        {'project': 'A', 'provider': 'openrouter', 'type': 'credits', 'success': True, 'credits': 100, 'threshold': 50, 'need_alarm': False},
        {'project': 'B', 'provider': 'glm', 'type': 'quota', 'success': False, 'error': 'boom'},
    ]

    def test_refresh_balances_updates_state_and_metrics(self, state, metrics):
        with patch.object(main, 'run_credit_monitor', return_value={'success': True, 'results': self.results, 'count': 2}) as run:
            detail = main.refresh_balances(state, dry_run=True)
        run.assert_called_once()
        assert run.call_args.kwargs['dry_run'] is True
        assert detail == {'projects': 2, 'failed': 1, 'need_alarm': 0, 'dry_run': True}
        assert state.get_balance_state()['summary']['total'] == 2
        metrics.update_balance_metrics.assert_called_once_with(self.results)

    def test_refresh_balances_raises_on_failure(self, state, metrics):
        with patch.object(main, 'run_credit_monitor', return_value={'success': False, 'error': '配置文件不存在'}):
            with pytest.raises(RuntimeError, match='配置文件不存在'):
                main.refresh_balances(state, dry_run=False)
        metrics.update_balance_metrics.assert_not_called()

    def test_refresh_subscriptions_disabled_clears_state(self, state, metrics, monkeypatch):
        monkeypatch.delenv('ENABLE_SUBSCRIPTIONS', raising=False)
        detail = main.refresh_subscriptions(state, dry_run=True)
        assert detail == {'subscriptions': 0, 'enabled': False}
        assert state.get_subscription_state()['subscriptions'] == []
        metrics.update_subscription_metrics.assert_called_once_with([])

    def test_scan_mailboxes_skips_without_mailboxes(self, state, metrics):
        with patch('services.email_scanner.EmailScanner') as scanner_cls:
            scanner_cls.return_value.email_configs = []
            detail = main.scan_mailboxes(state, days=1, dry_run=False)
        assert detail['mailboxes'] == 0 and 'skipped' in detail
        assert state.get_email_state()['last_update'] is None

    def test_scan_mailboxes_updates_state(self, state, metrics):
        summary = {
            'days': 1, 'dry_run': False,
            'mailboxes': [{'name': 'A', 'total_emails': 3, 'alert_count': 1, 'error': None},
                          {'name': 'B', 'total_emails': 0, 'alert_count': 0, 'error': 'login failed'}],
            'total_emails': 3, 'total_alerts': 1, 'alerts_sent': 1,
            'results': [{'mailbox': 'A', 'subject': 's', 'alert_sent': True}],
        }
        with patch('services.email_scanner.EmailScanner') as scanner_cls:
            scanner = scanner_cls.return_value
            scanner.email_configs = [{'name': 'A'}, {'name': 'B'}]
            scanner.scan_emails.return_value = summary
            detail = main.scan_mailboxes(state, days=1, dry_run=False)
        scanner.scan_emails.assert_called_once_with(days=1, dry_run=False)
        assert detail == {'mailboxes': 2, 'failed_mailboxes': 1, 'emails': 3, 'alerts': 1, 'alerts_sent': 1, 'dry_run': False}
        assert state.get_email_state()['summary']['failed_mailboxes'] == 1


class TestWeeklyReportJob:

    def test_builds_from_state_and_sends(self, state, metrics):
        state.update_balance_state([
            {'project': 'A', 'provider': 'openrouter', 'success': True, 'credits': 70, 'threshold': 50,
             'need_alarm': False},
        ])
        with patch('services.weekly_report.runway_service.compute_all', return_value={}), \
             patch('services.weekly_report.send', return_value=True) as send:
            detail = main.send_weekly_report(state)
        send.assert_called_once()
        assert detail['accounts'] == 1 and detail['sent'] is True


class TestResultHandler:

    def test_records_state_and_metrics(self, state, metrics):
        handler = main._make_result_handler(state)
        job = Job('alert_check', lambda: None, description='d', daily_times=[dtime(9, 0)])
        job.next_run = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
        started = datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc)
        handler(job, JobResult('alert_check', False, started, 0.5, error='webhook 502'))

        recorded = state.get_job_state()
        assert recorded['healthy'] is False
        entry = recorded['jobs'][0]
        assert entry['name'] == 'alert_check'
        assert entry['last_error'] == 'webhook 502'
        assert entry['last_run'] == '2026-09-14T07:00:00Z'
        assert entry['next_run'] == '2026-09-15T01:00:00Z'
        metrics.record_job_run.assert_called_once_with('alert_check', False, 0.5, started)
