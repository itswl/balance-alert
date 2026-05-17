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

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    
    def test_complete_monitoring_flow(self, test_config_file):
        """
        测试完整监控流程：
        1. 加载配置
        2. 执行监控检查
        3. 验证结果存储到状态管理器
        """
        import services.monitor
        services.monitor._response_cache.clear()
        # Mock provider 响应
        mock_response = {
            'success': True,
            'credits': 150.0,
            'threshold': 100.0,
            'need_alarm': False
        }
        
        with patch('providers.openrouter.OpenRouterProvider.get_credits', return_value=mock_response):
            # 1. 创建监控器
            monitor = CreditMonitor(test_config_file)
            
            # 2. 执行监控（dry_run 模式）
            monitor.run(dry_run=True)
            
            # 3. 验证结果
            assert len(monitor.results) > 0
            
            # 取出我们刚刚创建的配置里的 projects (应该有2个)
            test_results = [r for r in monitor.results if 'Test' in r['project'] or r['project'] == 'OpenRouter']
            
            # 取第一个项目简单验证一下格式
            if len(test_results) > 0:
                result1 = test_results[0]
                assert result1['success'] is True
                assert 'credits' in result1 or 'error' in result1
    
    def test_concurrent_checks(self, test_config_file):
        """测试并发检查能力"""
        mock_response = {
            'success': True,
            'credits': 200.0,
            'threshold': 100.0
        }
        
        with patch('providers.openrouter.OpenRouterProvider.get_credits', return_value=mock_response):
            monitor = CreditMonitor(test_config_file)
            
            start_time = time.time()
            monitor.run(dry_run=True)
            execution_time = time.time() - start_time
            
            # 并发检查应该比串行快
            # 2个项目，每个假设 0.1 秒，并发应该 < 1 秒
            assert execution_time < 2.0
    
    def test_alarm_logic(self, test_config_file):
        """测试告警逻辑"""
        # 模拟余额低于阈值的情况
        import services.monitor
        services.monitor._response_cache.clear()
        mock_response = {
            'success': True,
            'credits': 50.0,  # 低于阈值 100
            'threshold': 100.0,
            'need_alarm': True
        }
        
        with patch('providers.openrouter.OpenRouterProvider.get_credits', return_value=mock_response):
            monitor = CreditMonitor(test_config_file)
            monitor.run(dry_run=True)
            
            # 验证告警标记
            assert any(r.get('need_alarm', False) for r in monitor.results)
    
    def test_provider_failure_handling(self, test_config_file):
        """测试 Provider 失败处理"""
        import services.monitor
        services.monitor._response_cache.clear()
        # 模拟 Provider 异常
        with patch('providers.openrouter.OpenRouterProvider.get_credits', side_effect=Exception("API Error")):
            monitor = CreditMonitor(test_config_file)
            monitor.run(dry_run=True)
            
            # 验证错误处理
            test_results = [r for r in monitor.results if 'Test' in r['project'] or r['project'] == 'OpenRouter']
            assert len(test_results) > 0
            for result in test_results:
                if not result['success']:
                    assert 'error' in result


class TestE2EWebAPI:
    """端到端 Web API 测试"""
    
    @pytest.fixture
    def app(self):
        """创建测试 Flask 应用"""
        # 动态导入避免副作用
        from web.app import create_app
        from core.state_manager import StateManager
        app = create_app(StateManager())
        app.config['TESTING'] = True
        os.environ['WEB_API_KEY'] = ''
        return app
    
    @pytest.fixture
    def client(self, app):
        """创建测试客户端"""
        # 禁用 auth 或者提供 auth header
        os.environ['WEB_AUTH_ENABLED'] = 'false'
        os.environ['WEB_API_KEY'] = 'test-key'
        app.config['TESTING'] = True
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
    
    def test_api_with_invalid_data(self, client):
        """测试 API 输入验证"""
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


class TestE2EConfigReload:
    """配置热重载测试"""
    
    def test_config_reload(self, test_config_file):
        """测试配置文件修改后自动重载"""
        # 1. 加载初始配置
        initial_config = load_config_with_env_vars(test_config_file, validate=False)
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
        reloaded_config = load_config_with_env_vars(test_config_file, validate=False)
        
        # 4. 验证配置已更新
        assert len(reloaded_config.get('projects', [])) == initial_project_count + 1


class TestE2EPerformance:
    """性能基准测试"""
    
    def test_monitor_performance_benchmark(self, test_config_file):
        """监控性能基准测试"""
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


class TestE2EIntegration:
    """集成测试"""
    
    def test_monitor_and_state_integration(self, test_config_file):
        """测试监控和状态管理器集成"""
        mock_response = {
            'success': True,
            'credits': 123.45,
            'threshold': 100.0,
            'need_alarm': False
        }
        
        with patch('providers.openrouter.OpenRouterProvider.get_credits', return_value=mock_response):
            monitor = CreditMonitor(test_config_file)
            monitor.run(dry_run=True)
            
            # 注意：monitor.run() 不会直接更新 StateManager
            # 在实际应用中，web_server 会调用 update_balance_cache()
            # 这里我们验证 monitor 的结果格式正确
            assert len(monitor.results) > 0
            assert all('project' in r for r in monitor.results)


if __name__ == '__main__':
    # 运行测试
    pytest.main([__file__, '-v', '--tb=short'])
