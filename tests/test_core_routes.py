"""
核心路由测试：/health 的任务健康判定、/api/jobs、/api/refresh 同步指标
"""
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from core.state_manager import StateManager
from web.app import create_app

AUTH = {'X-API-Key': 'test-key'}
PROJECT = {'project': 'A', 'provider': 'openrouter', 'type': 'credits', 'success': True,
           'credits': 100, 'threshold': 50, 'need_alarm': False}


@pytest.fixture
def state():
    return StateManager()


@pytest.fixture
def client(state, monkeypatch):
    monkeypatch.setenv('WEB_API_KEY', 'test-key')
    app = create_app(state)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestJobsEndpoint:

    def test_requires_api_key(self, client):
        assert client.get('/api/jobs').status_code == 401

    def test_initially_empty_and_healthy(self, client):
        body = client.get('/api/jobs', headers=AUTH).get_json()
        assert body == {'healthy': True, 'jobs': []}

    def test_lists_registered_jobs_with_runs(self, client, state):
        state.register_job('alert_check', description='告警检查', schedule='每天 09:00 / 15:00', enabled=True,
                           next_run=datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc))
        state.record_job_run('alert_check', success=True, started_at=datetime(2026, 9, 14, 7, 0, tzinfo=timezone.utc),
                             duration_seconds=1.234, detail={'projects': 3},
                             next_run=datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc))
        body = client.get('/api/jobs', headers=AUTH).get_json()
        assert body['healthy'] is True
        job = body['jobs'][0]
        assert job['schedule'] == '每天 09:00 / 15:00'
        assert job['last_success'] == '2026-09-14T07:00:00Z'
        assert job['last_duration_seconds'] == 1.234
        assert job['last_detail'] == {'projects': 3}
        assert job['runs'] == 1 and job['failures'] == 0


class TestHealth:

    def test_healthy_with_data_and_good_jobs(self, client, state):
        state.update_balance_state([PROJECT])
        response = client.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'
        assert data['jobs_healthy'] is True and data['failed_jobs'] == []

    def test_degraded_when_a_job_failed(self, client, state):
        state.update_balance_state([PROJECT])
        state.register_job('email_scan', enabled=True)
        state.record_job_run('email_scan', success=False, started_at=datetime.now(timezone.utc),
                             duration_seconds=0.1, error='IMAP login failed')
        response = client.get('/health')
        assert response.status_code == 503
        data = response.get_json()
        assert data['status'] == 'degraded'
        assert data['jobs_healthy'] is False
        assert data['failed_jobs'] == ['email_scan']
        assert 'IMAP' not in json.dumps(data)  # 未认证端点不泄露错误原文

    def test_disabled_job_failure_is_ignored(self, client, state):
        state.update_balance_state([PROJECT])
        state.register_job('alert_check', enabled=False)
        state.record_job_run('alert_check', success=False, started_at=datetime.now(timezone.utc),
                             duration_seconds=0.1, error='x')
        assert client.get('/health').status_code == 200

    def test_recovery_clears_failure(self, client, state):
        state.update_balance_state([PROJECT])
        state.register_job('alert_check', enabled=True)
        now = datetime.now(timezone.utc)
        state.record_job_run('alert_check', success=False, started_at=now, duration_seconds=0.1, error='x')
        state.record_job_run('alert_check', success=True, started_at=now, duration_seconds=0.1)
        assert client.get('/health').status_code == 200


class TestRefreshUpdatesMetrics:

    def test_full_refresh_pushes_merged_projects_to_metrics(self, client, state):
        with patch('web.routes.core.run_credit_monitor', return_value={'success': True, 'results': [PROJECT], 'count': 1}), \
             patch('web.routes.core.metrics_collector') as collector:
            response = client.post('/api/refresh', data=json.dumps({}), content_type='application/json', headers=AUTH)
        assert response.status_code == 200
        collector.update_balance_metrics.assert_called_once()
        pushed = collector.update_balance_metrics.call_args.args[0]
        assert pushed[0]['project'] == 'A'
        assert state.get_balance_state()['summary']['total'] == 1

    def test_partial_refresh_merges_then_pushes_all(self, client, state):
        other = dict(PROJECT, project='B')
        state.update_balance_state([PROJECT, other])
        updated = dict(other, credits=5, need_alarm=True)
        with patch('web.routes.core.run_credit_monitor', return_value={'success': True, 'results': [updated], 'count': 1}), \
             patch('web.routes.core.metrics_collector') as collector:
            response = client.post('/api/refresh', data=json.dumps({'project_name': 'B'}),
                                   content_type='application/json', headers=AUTH)
        assert response.status_code == 200
        pushed = collector.update_balance_metrics.call_args.args[0]
        assert {p['project'] for p in pushed} == {'A', 'B'}  # 推给指标的是合并后的全量
