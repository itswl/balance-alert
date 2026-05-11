"""
Provider 适配器测试 — OpenRouter/UniAPI/WxRank/TikHub mock HTTP 测试
"""
import pytest
import requests
from unittest.mock import patch, MagicMock
from providers.openrouter import OpenRouterProvider
from providers.uniapi import UniAPIProvider
from providers.wxrank import WxRankProvider
from providers.tikhub import TikHubProvider


def _mock_response(status_code=200, json_data=None, text=''):
    """创建 mock HTTP 响应"""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.reason = 'OK' if status_code == 200 else 'Error'
    resp.text = text or str(json_data)
    resp.json.return_value = json_data
    return resp


# ==================== OpenRouter ====================

class TestOpenRouterProvider:

    def test_provider_name(self):
        assert OpenRouterProvider.get_provider_name() == 'OpenRouter'

    @patch.object(OpenRouterProvider, '_make_request')
    def test_success_nested_data(self, mock_req):
        """成功获取余额 — 嵌套 data 结构"""
        mock_req.return_value = _mock_response(200, {
            'data': {'total_credits': 100.0, 'total_usage': 25.5}
        })
        provider = OpenRouterProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(74.5)

    @patch.object(OpenRouterProvider, '_make_request')
    def test_success_flat_data(self, mock_req):
        """成功获取余额 — 平铺结构"""
        mock_req.return_value = _mock_response(200, {
            'total_credits': 50.0, 'total_usage': 10.0
        })
        provider = OpenRouterProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(40.0)

    @patch.object(OpenRouterProvider, '_make_request')
    def test_missing_total_credits(self, mock_req):
        """缺少 total_credits 字段"""
        mock_req.return_value = _mock_response(200, {
            'data': {'total_usage': 25.5}
        })
        provider = OpenRouterProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert 'total_credits' in result['error']

    @patch.object(OpenRouterProvider, '_make_request')
    def test_missing_total_usage(self, mock_req):
        """缺少 total_usage 字段"""
        mock_req.return_value = _mock_response(200, {
            'data': {'total_credits': 100.0}
        })
        provider = OpenRouterProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert 'total_usage' in result['error']

    @patch.object(OpenRouterProvider, '_make_request')
    def test_http_error(self, mock_req):
        """HTTP 错误"""
        mock_req.return_value = _mock_response(401, text='Unauthorized')
        provider = OpenRouterProvider('bad-key')
        result = provider.get_credits()
        assert result['success'] is False

    @patch.object(OpenRouterProvider, '_make_request')
    def test_network_timeout(self, mock_req):
        """网络超时"""
        mock_req.side_effect = requests.exceptions.Timeout('timeout')
        provider = OpenRouterProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert '超时' in result['error']


# ==================== UniAPI ====================

class TestUniAPIProvider:

    def test_provider_name(self):
        assert UniAPIProvider.get_provider_name() == 'UniAPI'

    @patch.object(UniAPIProvider, '_make_request')
    def test_success(self, mock_req):
        """成功获取余额"""
        mock_req.return_value = _mock_response(200, {
            'success': True,
            'data': {'balance': 10446.05, 'used': 48280.24, 'cache_used': 0}
        })
        provider = UniAPIProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(10446.05)

    @patch.object(UniAPIProvider, '_make_request')
    def test_api_success_false(self, mock_req):
        """API 返回 success=false"""
        mock_req.return_value = _mock_response(200, {
            'success': False, 'data': {}
        })
        provider = UniAPIProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False

    @patch.object(UniAPIProvider, '_make_request')
    def test_missing_balance(self, mock_req):
        """缺少 balance 字段"""
        mock_req.return_value = _mock_response(200, {
            'success': True, 'data': {'used': 100}
        })
        provider = UniAPIProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert 'balance' in result['error']

    @patch.object(UniAPIProvider, '_make_request')
    def test_connection_error(self, mock_req):
        """连接错误"""
        mock_req.side_effect = requests.exceptions.ConnectionError('refused')
        provider = UniAPIProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert '连接' in result['error']


# ==================== WxRank ====================

class TestWxRankProvider:

    def test_provider_name(self):
        assert WxRankProvider.get_provider_name() == 'WxRank'

    @patch.object(WxRankProvider, '_make_request')
    def test_success_msg_format(self, mock_req):
        """成功 — 从 msg 字段解析余额"""
        mock_req.return_value = _mock_response(200, {
            'code': 0, 'msg': '剩余263419余额'
        })
        provider = WxRankProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(263419.0)

    @patch.object(WxRankProvider, '_make_request')
    def test_success_data_field(self, mock_req):
        """成功 — 从 data 数值字段获取"""
        mock_req.return_value = _mock_response(200, {
            'code': 0, 'msg': '查询成功', 'data': 5000
        })
        provider = WxRankProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(5000.0)

    @patch.object(WxRankProvider, '_make_request')
    def test_success_data_dict(self, mock_req):
        """成功 — 从 data.score 获取"""
        mock_req.return_value = _mock_response(200, {
            'code': 0, 'msg': '查询成功', 'data': {'score': 1234}
        })
        provider = WxRankProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(1234.0)

    @patch.object(WxRankProvider, '_make_request')
    def test_api_error_code(self, mock_req):
        """API 返回错误码"""
        mock_req.return_value = _mock_response(200, {
            'code': -1, 'msg': '密钥无效'
        })
        provider = WxRankProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert '密钥无效' in result['error']

    @patch.object(WxRankProvider, '_make_request')
    def test_unparseable_credits(self, mock_req):
        """无法解析余额"""
        mock_req.return_value = _mock_response(200, {
            'code': 0, 'msg': '无数据'
        })
        provider = WxRankProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False


# ==================== TikHub ====================

class TestTikHubProvider:

    def test_provider_name(self):
        assert TikHubProvider.get_provider_name() == 'TikHub'

    @patch.object(TikHubProvider, '_make_request')
    def test_success_user_data(self, mock_req):
        """成功 — user_data 结构"""
        mock_req.return_value = _mock_response(200, {
            'code': 200, 'user_data': {'balance': 99.5}
        })
        provider = TikHubProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(99.5)

    @patch.object(TikHubProvider, '_make_request')
    def test_success_data_field(self, mock_req):
        """成功 — data 结构回退"""
        mock_req.return_value = _mock_response(200, {
            'data': {'balance': 50.0}
        })
        provider = TikHubProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(50.0)

    @patch.object(TikHubProvider, '_make_request')
    def test_success_flat(self, mock_req):
        """成功 — 平铺结构回退"""
        mock_req.return_value = _mock_response(200, {
            'balance': 20.0
        })
        provider = TikHubProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(20.0)

    @patch.object(TikHubProvider, '_make_request')
    def test_missing_balance(self, mock_req):
        """缺少 balance 字段"""
        mock_req.return_value = _mock_response(200, {
            'user_data': {'name': 'test'}
        })
        provider = TikHubProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert 'balance' in result['error']

    @patch.object(TikHubProvider, '_make_request')
    def test_http_403(self, mock_req):
        """HTTP 403 禁止访问"""
        mock_req.return_value = _mock_response(403, text='Forbidden')
        provider = TikHubProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
