"""
Provider 适配器测试 — OpenRouter/UniAPI/WxRank/TikHub/DeepSeek/GLM mock HTTP 测试
"""
import pytest
import requests
from unittest.mock import patch, MagicMock
from providers.openrouter import OpenRouterProvider
from providers.uniapi import UniAPIProvider
from providers.wxrank import WxRankProvider
from providers.tikhub import TikHubProvider
from providers.deepseek import DeepSeekProvider
from providers.glm import GLMProvider


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


# ==================== DeepSeek ====================

class TestDeepSeekProvider:

    def test_provider_name(self):
        assert DeepSeekProvider.get_provider_name() == 'DeepSeek'

    @patch.object(DeepSeekProvider, '_make_request')
    def test_success_real_shape(self, mock_req):
        """成功 — 线上真实结构，金额是字符串"""
        mock_req.return_value = _mock_response(200, {
            'is_available': True,
            'balance_infos': [
                {'currency': 'CNY', 'total_balance': '430.37',
                 'granted_balance': '0.00', 'topped_up_balance': '430.37'}
            ]
        })
        provider = DeepSeekProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(430.37)
        assert mock_req.call_args.kwargs['headers']['Authorization'] == 'Bearer test-key'

    @patch.object(DeepSeekProvider, '_make_request')
    def test_prefers_cny_account(self, mock_req):
        """多币种时优先取人民币账户"""
        mock_req.return_value = _mock_response(200, {
            'is_available': True,
            'balance_infos': [
                {'currency': 'USD', 'total_balance': '12.00'},
                {'currency': 'CNY', 'total_balance': '88.00'},
            ]
        })
        provider = DeepSeekProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(88.0)

    @patch.object(DeepSeekProvider, '_make_request')
    def test_falls_back_to_first_account(self, mock_req):
        """没有人民币账户时退回第一条"""
        mock_req.return_value = _mock_response(200, {
            'is_available': True,
            'balance_infos': [{'currency': 'USD', 'total_balance': '12.50'}]
        })
        provider = DeepSeekProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(12.5)

    @patch.object(DeepSeekProvider, '_make_request')
    def test_unavailable_account_still_reports_balance(self, mock_req):
        """欠费 is_available=false 也是有效读数，余额照常返回给阈值判断"""
        mock_req.return_value = _mock_response(200, {
            'is_available': False,
            'balance_infos': [{'currency': 'CNY', 'total_balance': '0.00'}]
        })
        provider = DeepSeekProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(0.0)

    @patch.object(DeepSeekProvider, '_make_request')
    def test_missing_balance_infos(self, mock_req):
        """缺少 balance_infos 字段"""
        mock_req.return_value = _mock_response(200, {'is_available': True})
        provider = DeepSeekProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert 'balance_infos' in result['error']

    @patch.object(DeepSeekProvider, '_make_request')
    def test_empty_balance_infos(self, mock_req):
        """balance_infos 为空列表"""
        mock_req.return_value = _mock_response(200, {'is_available': True, 'balance_infos': []})
        provider = DeepSeekProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False

    @patch.object(DeepSeekProvider, '_make_request')
    def test_missing_total_balance(self, mock_req):
        """缺少 total_balance 字段"""
        mock_req.return_value = _mock_response(200, {
            'balance_infos': [{'currency': 'CNY', 'granted_balance': '0.00'}]
        })
        provider = DeepSeekProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert 'total_balance' in result['error']

    @patch.object(DeepSeekProvider, '_make_request')
    def test_http_401(self, mock_req):
        """HTTP 401 密钥无效"""
        mock_req.return_value = _mock_response(401, text='Unauthorized')
        provider = DeepSeekProvider('bad-key')
        result = provider.get_credits()
        assert result['success'] is False

    @patch.object(DeepSeekProvider, '_make_request')
    def test_network_timeout(self, mock_req):
        """网络超时"""
        mock_req.side_effect = requests.exceptions.Timeout('timeout')
        provider = DeepSeekProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert '超时' in result['error']


# ==================== GLM (智谱 Coding Plan) ====================

class TestGLMProvider:

    def test_provider_name(self):
        assert GLMProvider.get_provider_name() == 'GLM'

    @patch.object(GLMProvider, '_make_request')
    def test_success_legacy_limits(self, mock_req):
        """成功 — 线上真实结构：TIME_LIMIT 有绝对量，TOKENS_LIMIT 只有百分比，取剩余比例最低者"""
        mock_req.return_value = _mock_response(200, {
            'code': 200, 'msg': '操作成功', 'success': True,
            'data': {
                'level': 'pro',
                'limits': [
                    {'type': 'TIME_LIMIT', 'unit': 5, 'number': 1, 'usage': 1000,
                     'currentValue': 13, 'remaining': 987, 'percentage': 1,
                     'nextResetTime': 1790409645998},
                    {'type': 'TOKENS_LIMIT', 'unit': 3, 'number': 5, 'percentage': 0},
                ],
            },
        })
        provider = GLMProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(98.7)
        assert mock_req.call_args.kwargs['headers']['Authorization'] == 'Bearer test-key'

    @patch.object(GLMProvider, '_make_request')
    def test_success_credit_limits(self, mock_req):
        """成功 — 新版 CREDIT_LIMIT 结构（5 小时窗口 + 周窗口），取更紧的那个"""
        mock_req.return_value = _mock_response(200, {
            'code': 200, 'msg': 'Operation successful', 'success': True,
            'data': {
                'level': 'lite',
                'limits': [
                    {'type': 'CREDIT_LIMIT', 'unit': 3, 'number': 5, 'usage': 2000,
                     'currentValue': 402, 'remaining': 1597, 'percentage': 20},
                    {'type': 'CREDIT_LIMIT', 'unit': 6, 'number': 1, 'usage': 10000,
                     'currentValue': 5207, 'remaining': 4792, 'percentage': 52},
                ],
            },
        })
        provider = GLMProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(47.92)

    @patch.object(GLMProvider, '_make_request')
    def test_percentage_only_depleted(self, mock_req):
        """只有百分比且已用满 → 剩余 0"""
        mock_req.return_value = _mock_response(200, {
            'code': 200, 'success': True,
            'data': {'limits': [{'type': 'TOKENS_LIMIT', 'percentage': 100}]},
        })
        provider = GLMProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(0.0)

    @patch.object(GLMProvider, '_make_request')
    def test_remaining_clamped_to_range(self, mock_req):
        """异常数据钳制在 0-100"""
        mock_req.return_value = _mock_response(200, {
            'code': 200, 'success': True,
            'data': {'limits': [
                {'type': 'CREDIT_LIMIT', 'usage': 100, 'remaining': 150},
                {'type': 'TOKENS_LIMIT', 'percentage': 130},
            ]},
        })
        provider = GLMProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
        assert result['credits'] == pytest.approx(0.0)

    @patch.object(GLMProvider, '_make_request')
    def test_api_error(self, mock_req):
        """业务失败 success=false"""
        mock_req.return_value = _mock_response(200, {
            'code': 401, 'msg': '令牌无效', 'success': False, 'data': None
        })
        provider = GLMProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert '令牌无效' in result['error']

    @patch.object(GLMProvider, '_make_request')
    def test_missing_limits(self, mock_req):
        """缺少 data.limits"""
        mock_req.return_value = _mock_response(200, {
            'code': 200, 'success': True, 'data': {'level': 'pro'}
        })
        provider = GLMProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert 'limits' in result['error']

    @patch.object(GLMProvider, '_make_request')
    def test_no_parseable_window(self, mock_req):
        """limits 里没有任何能算出剩余比例的窗口"""
        mock_req.return_value = _mock_response(200, {
            'code': 200, 'success': True,
            'data': {'limits': [{'type': 'TOKENS_LIMIT', 'unit': 3, 'number': 5}]},
        })
        provider = GLMProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False

    @patch.object(GLMProvider, '_make_request')
    def test_http_500(self, mock_req):
        """HTTP 500"""
        mock_req.return_value = _mock_response(500, text='Internal Server Error')
        provider = GLMProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False

    @patch.object(GLMProvider, '_make_request')
    def test_connection_error(self, mock_req):
        """连接错误"""
        mock_req.side_effect = requests.exceptions.ConnectionError('refused')
        provider = GLMProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is False
        assert '连接' in result['error']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
