"""
余额监控器测试
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from core import config_loader
from services import monitor as monitor_module
from services.monitor import CreditMonitor

PROJECT = {
    'name': 'TestProject', 'provider': 'openrouter', 'api_key': 'sk-test',
    'threshold': 10.0, 'type': 'credits', 'enabled': True,
}


def _db(projects):
    """项目清单来自数据库动态配置，不再有配置文件"""
    return patch.object(config_loader, '_db_sections', return_value={
        'projects': projects, 'subscriptions': [], 'email': [],
    })


def _provider(mock_get_provider, **credits):
    provider_class = MagicMock()
    provider_class.return_value.get_credits.return_value = credits
    mock_get_provider.return_value = provider_class
    return provider_class


class TestCreditMonitor:
    """余额监控器测试"""

    @pytest.fixture(autouse=True)
    def clear_response_cache(self):
        """每个测试前清空 provider 响应缓存和实例缓存"""
        monitor_module._response_cache.clear()
        monitor_module._provider_cache.clear()

    def test_loads_projects_from_config(self):
        with _db([PROJECT]):
            assert [p['name'] for p in CreditMonitor().config['projects']] == ['TestProject']

    def test_no_projects_is_not_an_error(self):
        """一个项目都没有时照样能起来，页面上加就是了"""
        with _db([]):
            assert CreditMonitor().config['projects'] == []

    def test_get_max_concurrent_checks_default(self):
        """未设置 MAX_CONCURRENT_CHECKS 时使用默认并发数"""
        os.environ.pop('MAX_CONCURRENT_CHECKS', None)
        with _db([]):
            assert CreditMonitor()._get_max_concurrent_checks() == 20

    def test_get_max_concurrent_checks_clamped(self):
        """MAX_CONCURRENT_CHECKS 环境变量钳制在 [1, 50]"""
        with _db([]):
            monitor = CreditMonitor()
        try:
            os.environ['MAX_CONCURRENT_CHECKS'] = '100'
            assert monitor._get_max_concurrent_checks() == 50  # 上限
            os.environ['MAX_CONCURRENT_CHECKS'] = '-5'
            assert monitor._get_max_concurrent_checks() == 1   # 下限
        finally:
            os.environ.pop('MAX_CONCURRENT_CHECKS', None)

    @patch('services.monitor.get_provider')
    def test_check_project_success(self, mock_get_provider):
        """测试项目检查成功"""
        _provider(mock_get_provider, success=True, credits=50.0)
        with _db([PROJECT]):
            result = CreditMonitor().check_project(PROJECT)

        assert result['success'] is True
        assert result['credits'] == 50.0
        assert result['need_alarm'] is False

    @patch('services.monitor.get_provider')
    def test_check_project_need_alarm(self, mock_get_provider):
        """测试项目余额不足触发告警"""
        _provider(mock_get_provider, success=True, credits=5.0)
        with _db([PROJECT]):
            result = CreditMonitor().check_project(PROJECT, dry_run=True)

        assert result['success'] is True
        assert result['credits'] == 5.0
        assert result['need_alarm'] is True
        assert result['alarm_sent'] is False  # dry_run 不发送

    @patch('services.monitor.get_provider')
    def test_check_project_provider_error(self, mock_get_provider):
        """测试 provider 获取失败"""
        mock_get_provider.side_effect = ValueError("Unknown provider: test")
        with _db([PROJECT]):
            result = CreditMonitor().check_project(PROJECT)

        assert result['success'] is False
        assert 'Unknown provider' in result['error']

    @patch('services.monitor.get_provider')
    def test_check_project_api_error(self, mock_get_provider):
        """测试 API 调用失败"""
        _provider(mock_get_provider, success=False, error='API timeout')
        with _db([PROJECT]):
            result = CreditMonitor().check_project(PROJECT)

        assert result['success'] is False
        assert result['error'] == 'API timeout'

    @patch('services.monitor.get_provider')
    def test_run_filters_disabled_projects(self, mock_get_provider):
        """测试跳过禁用的项目"""
        _provider(mock_get_provider, success=True, credits=100)
        projects = [
            {'name': 'Enabled', 'provider': 'openrouter', 'api_key': 'k', 'threshold': 5, 'enabled': True},
            {'name': 'Disabled', 'provider': 'openrouter', 'api_key': 'k', 'threshold': 5, 'enabled': False},
        ]
        with _db(projects):
            monitor = CreditMonitor()
            monitor.run(dry_run=True)

        assert [r['project'] for r in monitor.results] == ['Enabled']

    @patch('services.monitor.get_provider')
    def test_env_discovered_project_is_checked(self, mock_get_provider):
        """只在环境变量里放了密钥，也照样会被检查"""
        _provider(mock_get_provider, success=True, credits=42.0)
        os.environ['OPENROUTER_API_KEY'] = 'sk-from-env'
        try:
            with _db([]):
                monitor = CreditMonitor()
                monitor.run(dry_run=True)
        finally:
            os.environ.pop('OPENROUTER_API_KEY', None)

        assert [r['project'] for r in monitor.results] == ['openrouter']
        assert monitor.results[0]['credits'] == 42.0

class TestProviderCache:
    """Provider 实例缓存测试（Phase 2.2）"""

    @pytest.fixture(autouse=True)
    def clear_caches(self):
        """每个测试前清空缓存"""
        monitor_module._response_cache.clear()
        monitor_module._provider_cache.clear()

    @patch('services.monitor.get_provider')
    def test_cache_reuse(self, mock_get_provider):
        """相同 provider+key 复用缓存实例"""
        mock_class = MagicMock()
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        mock_get_provider.return_value = mock_class

        p1 = monitor_module._get_or_create_provider('openrouter', 'sk-test')
        p2 = monitor_module._get_or_create_provider('openrouter', 'sk-test')

        assert p1 is p2
        # 只创建了一次实例
        assert mock_class.call_count == 1

    @patch('services.monitor.get_provider')
    def test_different_keys_independent(self, mock_get_provider):
        """不同 api_key 创建独立实例"""
        instance_a = MagicMock(name='instance_a')
        instance_b = MagicMock(name='instance_b')
        mock_class = MagicMock(side_effect=[instance_a, instance_b])
        mock_get_provider.return_value = mock_class

        p1 = monitor_module._get_or_create_provider('openrouter', 'sk-key-a')
        p2 = monitor_module._get_or_create_provider('openrouter', 'sk-key-b')

        assert p1 is instance_a
        assert p2 is instance_b
        assert mock_class.call_count == 2

    @patch('services.monitor.get_provider')
    def test_ttl_expiry(self, mock_get_provider):
        """TTL 过期后创建新实例"""
        instance_old = MagicMock(name='instance_old')
        instance_new = MagicMock(name='instance_new')
        mock_class = MagicMock(side_effect=[instance_old, instance_new])
        mock_get_provider.return_value = mock_class

        p1 = monitor_module._get_or_create_provider('openrouter', 'sk-test')
        assert p1 is instance_old

        # 手动把缓存写入时间拨到 TTL 之前
        cache = monitor_module._provider_cache._data
        for key, (cached_at, provider) in list(cache.items()):
            cache[key] = (cached_at - monitor_module.PROVIDER_CACHE_TTL - 1, provider)

        p2 = monitor_module._get_or_create_provider('openrouter', 'sk-test')

        assert p2 is instance_new
        assert mock_class.call_count == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
