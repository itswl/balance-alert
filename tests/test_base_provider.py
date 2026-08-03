"""
BaseProvider 基类工具方法测试
"""
import pytest
import json
import requests
from unittest.mock import patch, MagicMock
from providers.base import BaseProvider


class ConcreteProvider(BaseProvider):
    """用于测试的具体 Provider 实现"""

    def get_credits(self):
        return {'success': True, 'credits': 100.0, 'error': None, 'raw_data': {}}

    @classmethod
    def get_provider_name(cls):
        return 'test_provider'


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
        assert result['error'] == '请求超时'
        assert result['credits'] is None

    def test_connection_error(self):
        """测试连接错误分类"""
        exc = requests.exceptions.ConnectionError('Failed to establish connection')
        result = self.provider._classify_exception(exc)

        assert result['success'] is False
        assert '网络连接错误' in result['error']

    def test_http_error(self):
        """测试 HTTP 错误分类"""
        exc = requests.exceptions.HTTPError('500 Server Error')
        result = self.provider._classify_exception(exc)

        assert result['success'] is False
        assert 'HTTP错误' in result['error']

    def test_value_error(self):
        """测试数据解析错误分类"""
        exc = ValueError('invalid literal')
        result = self.provider._classify_exception(exc)

        assert result['success'] is False
        assert '数据解析错误' in result['error']

    def test_json_decode_error(self):
        """测试 JSON 解析错误分类"""
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


class TestMakeRequest:
    """_make_request 方法测试"""

    def setup_method(self):
        with patch.object(BaseProvider, '_create_session', return_value=MagicMock()):
            self.provider = ConcreteProvider(api_key='test-key')

    def test_default_timeout_applied(self):
        """未显式传 timeout 时使用默认超时"""
        self.provider._make_request('GET', 'https://example.com/api')
        _, kwargs = self.provider.session.request.call_args
        assert kwargs['timeout'] == 15

    def test_explicit_timeout_kept(self):
        """显式传入的 timeout 不被覆盖"""
        self.provider._make_request('GET', 'https://example.com/api', timeout=3)
        _, kwargs = self.provider.session.request.call_args
        assert kwargs['timeout'] == 3

    def test_network_exception_propagates(self):
        """网络异常向上抛出，由调用方分类"""
        self.provider.session.request.side_effect = requests.exceptions.Timeout('boom')
        with pytest.raises(requests.exceptions.Timeout):
            self.provider._make_request('GET', 'https://example.com/api')


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

    def test_context_manager_closes_session(self):
        """with 语法退出时关闭 session"""
        with patch.object(BaseProvider, '_create_session', return_value=MagicMock()) as _:
            with ConcreteProvider(api_key='sk-test') as provider:
                session = provider.session
            session.close.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
