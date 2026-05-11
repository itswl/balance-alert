"""
余额监控器测试
"""
import pytest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock
from services.monitor import CreditMonitor
from services import monitor as monitor_module


class TestCreditMonitor:
    """余额监控器测试"""

    @pytest.fixture(autouse=True)
    def clear_response_cache(self):
        """每个测试前清空 provider 响应缓存和实例缓存"""
        monitor_module._response_cache.clear()
        monitor_module._provider_cache.clear()

    def _create_config_file(self, config_data):
        """创建临时配置文件"""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(config_data, f, ensure_ascii=False)
        f.close()
        return f.name

    def _base_config(self, **overrides):
        """生成基础配置"""
        config = {
            'settings': {'max_concurrent_checks': 5},
            'projects': [
                {
                    'name': 'TestProject',
                    'provider': 'openrouter',
                    'api_key': 'sk-test',
                    'threshold': 10.0,
                    'type': 'credits',
                    'enabled': True
                }
            ],
            'subscriptions': [],
            'email': [],
            'webhook': {
                'url': 'https://example.com/webhook',
                'type': 'custom'
            }
        }
        config.update(overrides)
        return config

    @patch.dict(os.environ, {}, clear=True)
    @patch('core.config_loader.load_env_file')
    def test_load_config(self, mock_load_env):
        """测试加载配置文件"""
        config = self._base_config()
        config_path = self._create_config_file(config)
        try:
            monitor = CreditMonitor(config_path)
            assert any(p['name'] == 'TestProject' for p in monitor.config['projects'])
        finally:
            os.unlink(config_path)

    def test_load_config_file_not_found(self):
        """测试配置文件不存在"""
        with pytest.raises(FileNotFoundError):
            CreditMonitor('/nonexistent/config.json')

    def test_load_config_invalid_json(self):
        """测试无效 JSON 配置"""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        f.write('{invalid json}')
        f.close()
        try:
            with pytest.raises(ValueError):
                CreditMonitor(f.name)
        finally:
            os.unlink(f.name)

    def test_get_max_concurrent_checks_default(self):
        """测试默认并发数"""
        config = self._base_config(settings={})
        config_path = self._create_config_file(config)
        try:
            monitor = CreditMonitor(config_path)
            assert monitor._get_max_concurrent_checks() == 20
        finally:
            os.unlink(config_path)

    def test_get_max_concurrent_checks_clamped(self):
        """测试并发数上下限"""
        config = self._base_config(settings={'max_concurrent_checks': 100})
        config_path = self._create_config_file(config)
        try:
            monitor = CreditMonitor(config_path)
            assert monitor._get_max_concurrent_checks() == 50  # 上限
        finally:
            os.unlink(config_path)

        config = self._base_config(settings={'max_concurrent_checks': -5})
        config_path = self._create_config_file(config)
        try:
            monitor = CreditMonitor(config_path)
            assert monitor._get_max_concurrent_checks() == 1  # 下限
        finally:
            os.unlink(config_path)

    @patch('services.monitor.get_provider')
    def test_check_project_success(self, mock_get_provider):
        """测试项目检查成功"""
        mock_provider_class = MagicMock()
        mock_provider = MagicMock()
        mock_provider.get_credits.return_value = {'success': True, 'credits': 50.0}
        mock_provider_class.return_value = mock_provider
        mock_get_provider.return_value = mock_provider_class

        config = self._base_config()
        config_path = self._create_config_file(config)
        try:
            monitor = CreditMonitor(config_path)
            result = monitor.check_project(config['projects'][0])

            assert result['success'] is True
            assert result['credits'] == 50.0
            assert result['need_alarm'] is False
        finally:
            os.unlink(config_path)

    @patch('services.monitor.get_provider')
    def test_check_project_need_alarm(self, mock_get_provider):
        """测试项目余额不足触发告警"""
        mock_provider_class = MagicMock()
        mock_provider = MagicMock()
        mock_provider.get_credits.return_value = {'success': True, 'credits': 5.0}
        mock_provider_class.return_value = mock_provider
        mock_get_provider.return_value = mock_provider_class

        config = self._base_config()
        config_path = self._create_config_file(config)
        try:
            monitor = CreditMonitor(config_path)
            result = monitor.check_project(config['projects'][0], dry_run=True)

            assert result['success'] is True
            assert result['credits'] == 5.0
            assert result['need_alarm'] is True
            assert result['alarm_sent'] is False  # dry_run 不发送
        finally:
            os.unlink(config_path)

    @patch('services.monitor.get_provider')
    def test_check_project_provider_error(self, mock_get_provider):
        """测试 provider 获取失败"""
        mock_get_provider.side_effect = ValueError("Unknown provider: test")

        config = self._base_config()
        config_path = self._create_config_file(config)
        try:
            monitor = CreditMonitor(config_path)
            result = monitor.check_project(config['projects'][0])

            assert result['success'] is False
            assert 'Unknown provider' in result['error']
        finally:
            os.unlink(config_path)

    @patch('services.monitor.get_provider')
    def test_check_project_api_error(self, mock_get_provider):
        """测试 API 调用失败"""
        mock_provider_class = MagicMock()
        mock_provider = MagicMock()
        mock_provider.get_credits.return_value = {'success': False, 'error': 'API timeout'}
        mock_provider_class.return_value = mock_provider
        mock_get_provider.return_value = mock_provider_class

        config = self._base_config()
        config_path = self._create_config_file(config)
        try:
            monitor = CreditMonitor(config_path)
            result = monitor.check_project(config['projects'][0])

            assert result['success'] is False
            assert result['error'] == 'API timeout'
        finally:
            os.unlink(config_path)

    @patch('services.monitor.get_provider')
    def test_run_filters_disabled_projects(self, mock_get_provider):
        """测试跳过禁用的项目"""
        mock_provider_class = MagicMock()
        mock_provider = MagicMock()
        mock_provider.get_credits.return_value = {'success': True, 'credits': 100}
        mock_provider_class.return_value = mock_provider
        mock_get_provider.return_value = mock_provider_class

        config = self._base_config(projects=[
            {'name': 'Enabled', 'provider': 'openrouter', 'api_key': 'k', 'threshold': 5, 'enabled': True},
            {'name': 'Disabled', 'provider': 'openrouter', 'api_key': 'k', 'threshold': 5, 'enabled': False},
        ])
        config_path = self._create_config_file(config)
        try:
            monitor = CreditMonitor(config_path)
            monitor.run(dry_run=True)

            # 只有 1 个被检查的测试项目
            test_results = [r for r in monitor.results if r['project'] in ['Enabled', 'Disabled']]
            assert len(test_results) == 1
            assert test_results[0]['project'] == 'Enabled'
        finally:
            os.unlink(config_path)


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

        # 手动将缓存时间设为过去（超过 TTL）
        for key in list(monitor_module._provider_cache.keys()):
            old_time, provider = monitor_module._provider_cache[key]
            monitor_module._provider_cache[key] = (old_time - monitor_module.PROVIDER_CACHE_TTL - 1, provider)

        p2 = monitor_module._get_or_create_provider('openrouter', 'sk-test')

        assert p2 is instance_new
        assert mock_class.call_count == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
