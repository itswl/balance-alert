#!/usr/bin/env python3
"""
端到端测试

测试完整的业务流程，确保各组件协作正常
"""
import pytest
import json
import time
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import sys
import os

from services.monitor import CreditMonitor
from core.config_loader import load_config_with_env_vars


@pytest.fixture
def test_config_file():
    """创建测试配置文件"""
    config = {
        "settings": {
            "balance_refresh_interval_seconds": 60,
            "max_concurrent_checks": 5
        },
        "webhook": {
            "url": "https://example.com/webhook",
            "source": "test",
            "type": "feishu"
        },
        "projects": [
            {
                "name": "Test Project 1",
                "provider": "openrouter",
                "api_key": "test-key-1",
                "threshold": 100.0,
                "type": "credits",
                "enabled": True
            },
            {
                "name": "Test Project 2",
                "provider": "openrouter",
                "api_key": "test-key-2",
                "threshold": 50.0,
                "type": "credits",
                "enabled": True
            }
        ],
        "subscriptions": [],
        "email": []
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config, f)
        config_path = f.name
    
    yield config_path
    
    # 清理
    try:
        os.unlink(config_path)
    except Exception:
        pass


class TestE2EMonitoring:
    """端到端监控流程测试"""

    @pytest.mark.parametrize('patch_kwargs, expect_success, expect_alarm', [
        # 余额充足：正常返回，不触发告警
        ({'return_value': {'success': True, 'credits': 150.0,
                           'threshold': 100.0, 'need_alarm': False}}, True, False),
        # 余额低于阈值 100：触发告警标记
        ({'return_value': {'success': True, 'credits': 50.0,
                           'threshold': 100.0, 'need_alarm': True}}, True, True),
        # Provider 抛异常：错误被捕获并写入结果
        ({'side_effect': Exception("API Error")}, False, False),
    ], ids=['balance_ok', 'alarm_triggered', 'provider_failure'])
    def test_complete_monitoring_flow(self, test_config_file, patch_kwargs, expect_success, expect_alarm):
        """
        测试完整监控流程：
        1. 加载配置
        2. 执行监控检查（余额充足 / 低于阈值 / Provider 失败）
        3. 验证结果格式、告警标记与错误处理
        """
        import services.monitor
        services.monitor._response_cache.clear()

        with patch('providers.openrouter.OpenRouterProvider.get_credits', **patch_kwargs):
            monitor = CreditMonitor(test_config_file)
            monitor.run(dry_run=True)

        # 结果格式：monitor.run() 不会直接更新 StateManager，
        # 实际应用中由 web_server 调用 update_balance_cache()，这里验证结果结构正确
        assert len(monitor.results) > 0
        assert all('project' in r for r in monitor.results)

        # 取出我们刚刚创建的配置里的 projects (应该有2个)
        test_results = [r for r in monitor.results if 'Test' in r['project'] or r['project'] == 'OpenRouter']
        assert len(test_results) > 0
        for result in test_results:
            assert result['success'] is expect_success
            if result['success']:
                assert 'credits' in result or 'error' in result
            else:
                assert 'error' in result

        # 告警标记
        assert any(r.get('need_alarm', False) for r in monitor.results) is expect_alarm


class TestE2EWebAPI:
    """端到端 Web API 测试"""
    
    @pytest.fixture
    def client(self):
        """创建测试 Flask 应用与测试客户端"""
        # 动态导入避免副作用
        from web.app import create_app
        from core.state_manager import StateManager
        app = create_app(StateManager())
        app.config['TESTING'] = True
        # 提供 auth header 对应的 API Key
        os.environ['WEB_API_KEY'] = 'test-key'
        with app.test_client() as client:
            yield client
    
    def test_health_endpoint(self, client):
        """测试健康检查端点"""
        response = client.get('/health')
        
        # 状态码应该是 200 或 503
        assert response.status_code in [200, 503]
        
        # 验证响应格式
        data = response.get_json()
        assert 'status' in data
        assert 'has_data' in data

    def test_credits_endpoint(self, client):
        """测试余额查询端点"""
        response = client.get('/api/credits')
        
        # 可能返回 503（未初始化）或 200
        if response.status_code == 200:
            data = response.get_json()
            assert 'projects' in data or 'last_update' in data
    
    def test_concurrent_web_requests(self, client):
        """测试并发 Web 请求"""
        # 测试客户端由于 ContextVar 不适合跨线程并发，这里改为顺序测试多次
        results = []
        for _ in range(20):
            response = client.get('/health')
            results.append(response.status_code)

        assert all(code in [200, 503] for code in results)
    
    def test_api_with_invalid_data(self, client, monkeypatch):
        """测试 API 输入验证（订阅启用时走真实校验路径）"""
        monkeypatch.setenv('ENABLE_SUBSCRIPTIONS', 'true')
        # 发送无效的订阅数据
        invalid_data = {
            "name": "",  # 空名称
            "threshold": -100  # 负数阈值
        }

        response = client.post('/api/subscription/add',
                              data=json.dumps(invalid_data),
                              content_type='application/json',
                              headers={'Authorization': 'Bearer test-key'})

        # 应该返回 400 错误
        assert response.status_code == 400

    def test_subscription_api_disabled_returns_503(self, client, monkeypatch):
        """订阅功能关闭时，订阅写接口统一返回 503"""
        monkeypatch.delenv('ENABLE_SUBSCRIPTIONS', raising=False)
        response = client.post('/api/subscription/add',
                              data=json.dumps({"name": "x"}),
                              content_type='application/json',
                              headers={'Authorization': 'Bearer test-key'})
        assert response.status_code == 503


class TestE2EConfigReload:
    """配置热重载测试"""
    
    def test_config_reload(self, test_config_file):
        """测试配置文件修改后自动重载"""
        # 1. 加载初始配置
        initial_config = load_config_with_env_vars(test_config_file)
        initial_project_count = len(initial_config.get('projects', []))
        
        # 2. 修改配置文件
        config = initial_config.copy()
        config['projects'].append({
            "name": "New Project",
            "provider": "openrouter",
            "api_key": "new-key",
            "threshold": 200.0,
            "type": "credits",
            "enabled": True
        })
        
        with open(test_config_file, 'w') as f:
            json.dump(config, f)
        
        # 3. 重新加载配置
        time.sleep(0.1)  # 等待文件系统同步
        reloaded_config = load_config_with_env_vars(test_config_file)
        
        # 4. 验证配置已更新
        assert len(reloaded_config.get('projects', [])) == initial_project_count + 1


class TestE2EPerformance:
    """性能基准测试"""
    
    def test_monitor_performance_benchmark(self, test_config_file):
        """监控性能基准测试（同时覆盖 2 个项目的并发检查能力）"""
        mock_response = {
            'success': True,
            'credits': 100.0,
            'threshold': 50.0
        }
        
        with patch('providers.openrouter.OpenRouterProvider.get_credits', return_value=mock_response):
            monitor = CreditMonitor(test_config_file)
            
            # 执行 5 次，取平均值
            execution_times = []
            for _ in range(5):
                start_time = time.time()
                monitor.run(dry_run=True)
                execution_times.append(time.time() - start_time)
            
            avg_time = sum(execution_times) / len(execution_times)
            
            # 2 个项目的检查平均应该 < 2 秒
            assert avg_time < 2.0, f"Performance degradation: avg {avg_time:.2f}s"
            
            print(f"\n性能基准: 平均执行时间 {avg_time:.3f}s")


if __name__ == '__main__':
    # 运行测试
    pytest.main([__file__, '-v', '--tb=short'])
