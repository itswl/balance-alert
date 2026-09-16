#!/usr/bin/env python3
"""
端到端测试：配置来自环境变量与数据库，验证各组件协作
"""
import json
import time
from unittest.mock import patch

import pytest

from core import config_loader
from services.monitor import CreditMonitor


def _db(projects=None):
    return patch.object(config_loader, '_db_sections', return_value={
        'projects': projects or [], 'subscriptions': [], 'email': [],
    })


TWO_PROJECTS = [
    {'name': 'Test Project 1', 'provider': 'openrouter', 'api_key': 'test-key-1', 'threshold': 100.0,
     'type': 'credits', 'enabled': True},
    {'name': 'Test Project 2', 'provider': 'openrouter', 'api_key': 'test-key-2', 'threshold': 50.0,
     'type': 'credits', 'enabled': True},
]


class TestE2EMonitoring:
    """完整监控流程"""

    @pytest.mark.parametrize('patch_kwargs, expect_success, expect_alarm', [
        # 余额充足：正常返回，不触发告警
        ({'return_value': {'success': True, 'credits': 150.0, 'threshold': 100.0, 'need_alarm': False}}, True, False),
        # 余额低于阈值 100：触发告警标记
        ({'return_value': {'success': True, 'credits': 50.0, 'threshold': 100.0, 'need_alarm': True}}, True, True),
        # Provider 抛异常：错误被捕获并写入结果
        ({'side_effect': Exception("API Error")}, False, False),
    ], ids=['balance_ok', 'alarm_triggered', 'provider_failure'])
    def test_complete_monitoring_flow(self, patch_kwargs, expect_success, expect_alarm):
        """加载配置 → 并发检查 → 结果格式与告警标记"""
        import services.monitor
        services.monitor._response_cache.clear()

        with _db(TWO_PROJECTS), patch('providers.openrouter.OpenRouterProvider.get_credits', **patch_kwargs):
            monitor = CreditMonitor()
            monitor.run(dry_run=True)

        assert len(monitor.results) == 2
        assert all('project' in r for r in monitor.results)
        for result in monitor.results:
            assert result['success'] is expect_success
            assert ('credits' in result) or ('error' in result)
        assert any(r.get('need_alarm', False) for r in monitor.results) is expect_alarm

    def test_disabled_projects_are_skipped(self):
        projects = TWO_PROJECTS + [dict(TWO_PROJECTS[0], name='停用的', enabled=False)]
        with _db(projects), patch('providers.openrouter.OpenRouterProvider.get_credits',
                                  return_value={'success': True, 'credits': 1, 'threshold': 0}):
            monitor = CreditMonitor()
            monitor.run(dry_run=True)
        assert '停用的' not in {r['project'] for r in monitor.results}

    def test_env_only_configuration_works(self, monkeypatch):
        """完全不配数据库，只靠环境变量也能跑"""
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-x')
        monkeypatch.setenv('OPENROUTER_THRESHOLD', '100')
        with _db(), patch('providers.openrouter.OpenRouterProvider.get_credits',
                          return_value={'success': True, 'credits': 20.0}):
            monitor = CreditMonitor()
            monitor.run(dry_run=True)
        assert len(monitor.results) == 1
        result = monitor.results[0]
        assert result['project'] == 'openrouter' and result['threshold'] == 100.0
        assert result['need_alarm'] is True   # 20 < 100

    def test_no_projects_is_not_an_error(self):
        with _db():
            monitor = CreditMonitor()
            monitor.run(dry_run=True)
        assert monitor.results == []


class TestE2EWebAPI:
    """Web 接口"""

    @pytest.fixture
    def client(self, monkeypatch):
        from core.state_manager import StateManager
        from web.app import create_app

        monkeypatch.setenv('WEB_API_KEY', 'test-key')
        app = create_app(StateManager())
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    def test_health_endpoint(self, client):
        response = client.get('/health')
        assert response.status_code in (200, 503)
        data = response.get_json()
        assert {'status', 'has_data', 'jobs_healthy', 'failed_jobs'} <= set(data)

    def test_credits_endpoint(self, client):
        response = client.get('/api/credits', headers={'X-API-Key': 'test-key'})
        if response.status_code == 200:
            assert 'projects' in response.get_json()

    def test_repeated_requests_are_stable(self, client):
        assert {client.get('/health').status_code for _ in range(20)} <= {200, 503}

    def test_api_with_invalid_data(self, client, monkeypatch):
        monkeypatch.setenv('ENABLE_SUBSCRIPTIONS', 'true')
        response = client.post('/api/subscription/add', data=json.dumps({'name': '', 'threshold': -100}),
                               content_type='application/json', headers={'Authorization': 'Bearer test-key'})
        assert response.status_code == 400

    def test_subscription_api_disabled_returns_503(self, client, monkeypatch):
        monkeypatch.delenv('ENABLE_SUBSCRIPTIONS', raising=False)
        response = client.post('/api/subscription/add', data=json.dumps({'name': 'x'}),
                               content_type='application/json', headers={'Authorization': 'Bearer test-key'})
        assert response.status_code == 503


class TestE2EPerformance:
    """性能基准"""

    def test_monitor_performance_benchmark(self):
        with _db(TWO_PROJECTS), patch('providers.openrouter.OpenRouterProvider.get_credits',
                                      return_value={'success': True, 'credits': 100.0, 'threshold': 50.0}):
            monitor = CreditMonitor()
            times = []
            for _ in range(5):
                start = time.time()
                monitor.run(dry_run=True)
                times.append(time.time() - start)

        average = sum(times) / len(times)
        assert average < 2.0, f"Performance degradation: avg {average:.2f}s"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
