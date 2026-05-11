"""
BaseProvider 基类工具方法测试
"""
import pytest
import json
import requests
from unittest.mock import patch, MagicMock, PropertyMock
from providers.base import BaseProvider


class ConcreteProvider(BaseProvider):
    """用于测试的具体 Provider 实现"""

    def get_credits(self):
        return {'success': True, 'credits': 100.0, 'error': None, 'raw_data': {}}

    @classmethod
    def get_provider_name(cls):
        return 'test_provider'


class TestExtractField:
    """_extract_field 方法测试"""

    def setup_method(self):
        """创建测试用 Provider 实例"""
        with patch.object(BaseProvider, '_create_session', return_value=MagicMock()):
            self.provider = ConcreteProvider(api_key='test-key')

    def test_simple_path(self):
        """测试简单路径提取"""
        data = {'balance': 100.5}
        result = self.provider._extract_field(data, 'balance')
        assert result == 100.5

    def test_nested_path(self):
        """测试嵌套路径提取"""
        data = {'data': {'balance': 50.0}}
        result = self.provider._extract_field(data, 'data.balance')
        assert result == 50.0

    def test_deeply_nested_path(self):
        """测试深度嵌套路径提取"""
        data = {'Result': {'Account': {'AvailableBalance': 99.9}}}
        result = self.provider._extract_field(data, 'Result.Account.AvailableBalance')
        assert result == 99.9

    def test_missing_key_returns_none(self):
        """测试不存在的键返回 None"""
        data = {'balance': 100}
        result = self.provider._extract_field(data, 'credits')
        assert result is None

    def test_missing_nested_key_returns_none(self):
        """测试不存在的嵌套键返回 None"""
        data = {'data': {'balance': 100}}
        result = self.provider._extract_field(data, 'data.credits')
        assert result is None

    def test_multiple_paths_first_match(self):
        """测试多路径优先返回第一个匹配"""
        data = {'data': {'balance': 50.0}, 'credits': 100.0}
        result = self.provider._extract_field(data, 'data.balance', 'credits')
        assert result == 50.0

    def test_multiple_paths_fallback(self):
        """测试多路径回退到后续路径"""
        data = {'credits': 100.0}
        result = self.provider._extract_field(data, 'data.balance', 'credits')
        assert result == 100.0

    def test_multiple_paths_all_missing(self):
        """测试多路径全部未找到返回 None"""
        data = {'other': 'value'}
        result = self.provider._extract_field(data, 'data.balance', 'credits')
        assert result is None

    def test_non_dict_intermediate_value(self):
        """测试中间节点非字典时返回 None"""
        data = {'data': 'string_value'}
        result = self.provider._extract_field(data, 'data.balance')
        assert result is None

    def test_empty_dict(self):
        """测试空字典返回 None"""
        data = {}
        result = self.provider._extract_field(data, 'balance')
        assert result is None

    def test_value_is_zero(self):
        """测试值为 0 时正确返回（不被视为 None）"""
        data = {'balance': 0}
        # 0 被视为 None 并跳过（因为 if value is not None 对 0 返回 True）
        result = self.provider._extract_field(data, 'balance')
        assert result == 0

    def test_value_is_empty_string(self):
        """测试值为空字符串时正确返回"""
        data = {'name': ''}
        result = self.provider._extract_field(data, 'name')
        assert result == ''


class TestClassifyException:
    """_classify_exception 方法测试"""

    def setup_method(self):
        """创建测试用 Provider 实例"""
        with patch.object(BaseProvider, '_create_session', return_value=MagicMock()):
            self.provider = ConcreteProvider(api_key='test-key')

    def test_timeout_exception(self):
        """测试超时异常分类"""
        exc = requests.exceptions.Timeout('Connection timed out')
        result = self.provider._classify_exception(exc)

        assert result['success'] is False
        assert result['credits'] is None
        assert result['error'] == '请求超时'
        assert result['raw_data'] is None

    def test_connection_error(self):
        """测试连接错误分类"""
        exc = requests.exceptions.ConnectionError('Connection refused')
        result = self.provider._classify_exception(exc)

        assert result['success'] is False
        assert '网络连接错误' in result['error']
        assert 'Connection refused' in result['error']

    def test_http_error(self):
        """测试 HTTP 错误分类"""
        exc = requests.exceptions.HTTPError('403 Forbidden')
        result = self.provider._classify_exception(exc)

        assert result['success'] is False
        assert 'HTTP错误' in result['error']
        assert '403 Forbidden' in result['error']

    def test_value_error(self):
        """测试 ValueError 分类"""
        exc = ValueError('invalid literal')
        result = self.provider._classify_exception(exc)

        assert result['success'] is False
        assert '数据解析错误' in result['error']

    def test_json_decode_error(self):
        """测试 JSONDecodeError 分类"""
        exc = json.JSONDecodeError('Expecting value', '', 0)
        result = self.provider._classify_exception(exc)

        assert result['success'] is False
        assert '数据解析错误' in result['error']

    def test_unknown_exception(self):
        """测试未知异常分类"""
        exc = RuntimeError('Something unexpected')
        result = self.provider._classify_exception(exc)

        assert result['success'] is False
        assert '未知错误' in result['error']
        assert 'Something unexpected' in result['error']

    def test_result_structure(self):
        """测试返回结构包含所有必要字段"""
        exc = Exception('test')
        result = self.provider._classify_exception(exc)

        assert 'success' in result
        assert 'credits' in result
        assert 'error' in result
        assert 'raw_data' in result


class TestExtractNumericValue:
    """_extract_numeric_value 方法测试"""

    def setup_method(self):
        """创建测试用 Provider 实例"""
        with patch.object(BaseProvider, '_create_session', return_value=MagicMock()):
            self.provider = ConcreteProvider(api_key='test-key')

    def test_float_value(self):
        """测试浮点数输入"""
        result = self.provider._extract_numeric_value(3.14)
        assert result == 3.14

    def test_int_value(self):
        """测试整数输入"""
        result = self.provider._extract_numeric_value(42)
        assert result == 42.0
        assert isinstance(result, float)

    def test_string_number(self):
        """测试数字字符串"""
        result = self.provider._extract_numeric_value('100.50')
        assert result == 100.50

    def test_string_with_comma_separator(self):
        """测试带千位分隔符的字符串"""
        result = self.provider._extract_numeric_value('1,234,567.89')
        assert result == 1234567.89

    def test_string_with_yen_symbol(self):
        """测试带人民币符号的字符串"""
        result = self.provider._extract_numeric_value('¥100.50')
        assert result == 100.50

    def test_string_with_dollar_symbol(self):
        """测试带美元符号的字符串"""
        result = self.provider._extract_numeric_value('$99.99')
        assert result == 99.99

    def test_string_with_spaces(self):
        """测试带空格的字符串"""
        result = self.provider._extract_numeric_value('  50.00  ')
        assert result == 50.0

    def test_none_value(self):
        """测试 None 输入"""
        result = self.provider._extract_numeric_value(None)
        assert result is None

    def test_invalid_string(self):
        """测试无法转换的字符串"""
        result = self.provider._extract_numeric_value('not_a_number')
        assert result is None

    def test_empty_string(self):
        """测试空字符串"""
        result = self.provider._extract_numeric_value('')
        assert result is None

    def test_zero_value(self):
        """测试零值"""
        result = self.provider._extract_numeric_value(0)
        assert result == 0.0

    def test_negative_value(self):
        """测试负数"""
        result = self.provider._extract_numeric_value(-5.5)
        assert result == -5.5

    def test_string_zero(self):
        """测试字符串零"""
        result = self.provider._extract_numeric_value('0')
        assert result == 0.0

    def test_combined_currency_and_comma(self):
        """测试同时包含货币符号和千位分隔符"""
        result = self.provider._extract_numeric_value('¥1,234.56')
        assert result == 1234.56


class TestHandleResponse:
    """_handle_response 方法测试"""

    def setup_method(self):
        """创建测试用 Provider 实例"""
        with patch.object(BaseProvider, '_create_session', return_value=MagicMock()):
            self.provider = ConcreteProvider(api_key='test-key')

    def test_success_200(self):
        """测试 HTTP 200 成功响应"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'balance': 100.0}

        result = self.provider._handle_response(mock_response)

        assert result['success'] is True
        assert result['credits'] is None  # 基类不设置具体值
        assert result['error'] is None
        assert result['raw_data'] == {'balance': 100.0}

    def test_http_404(self):
        """测试 HTTP 404 错误响应"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.reason = 'Not Found'
        mock_response.text = 'Resource not found'

        result = self.provider._handle_response(mock_response)

        assert result['success'] is False
        assert result['credits'] is None
        assert 'HTTP 404' in result['error']
        assert 'Not Found' in result['error']

    def test_http_500(self):
        """测试 HTTP 500 错误响应"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.reason = 'Internal Server Error'
        mock_response.text = 'Server error'

        result = self.provider._handle_response(mock_response)

        assert result['success'] is False
        assert 'HTTP 500' in result['error']

    def test_invalid_json(self):
        """测试无效 JSON 响应"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError('No JSON object could be decoded')
        mock_response.text = 'not json content'

        result = self.provider._handle_response(mock_response)

        assert result['success'] is False
        assert '不是有效的 JSON 格式' in result['error']
        assert result['raw_data'] == 'not json content'

    def test_success_condition_pass(self):
        """测试自定义成功条件通过"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'ok', 'data': 100}

        condition = lambda r: r.status_code == 200
        result = self.provider._handle_response(mock_response, success_condition=condition)

        assert result['success'] is True

    def test_success_condition_fail(self):
        """测试自定义成功条件失败"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 'error', 'message': 'API error'}

        condition = lambda r: False  # 强制失败
        result = self.provider._handle_response(mock_response, success_condition=condition)

        assert result['success'] is False
        assert 'API 返回业务错误' in result['error']

    def test_response_result_structure(self):
        """测试返回结构完整性"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        result = self.provider._handle_response(mock_response)

        assert 'success' in result
        assert 'credits' in result
        assert 'error' in result
        assert 'raw_data' in result


class TestProviderInit:
    """Provider 初始化测试"""

    def test_api_key_stored(self):
        """测试 API Key 存储"""
        with patch.object(BaseProvider, '_create_session', return_value=MagicMock()):
            provider = ConcreteProvider(api_key='sk-test-key-123')
            assert provider.api_key == 'sk-test-key-123'

    def test_default_timeout(self):
        """测试默认超时时间"""
        with patch.object(BaseProvider, '_create_session', return_value=MagicMock()):
            provider = ConcreteProvider(api_key='sk-test')
            assert provider.timeout == 15

    def test_provider_name(self):
        """测试 Provider 名称"""
        assert ConcreteProvider.get_provider_name() == 'test_provider'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
