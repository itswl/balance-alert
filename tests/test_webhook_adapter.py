"""
Webhook 适配器测试
"""
import pytest
import requests
from unittest.mock import patch, MagicMock
from services.webhook_adapter import WebhookAdapter, _mask_webhook_url

WEBHOOK_URL = 'https://example.com/hook'
SAMPLE_PAYLOAD = {'msg_type': 'text', 'content': {'text': 'test'}}

# 各平台 payload 中承载正文的字段路径
_TEXT_FIELD = {
    'feishu': ('content', 'text'),
    'dingtalk': ('markdown', 'text'),
    'wecom': ('text', 'content'),
}

# (webhook_type, payload 类型键, 期望值)
DISPATCH_CASES = [
    ('feishu', 'msg_type', 'text'),
    ('dingtalk', 'msgtype', 'markdown'),
    ('wecom', 'msgtype', 'text'),
]

BALANCE_ARGS = {
    'project_name': 'TestProject',
    'provider': 'openrouter',
    'balance_type': '余额',
    'current_value': 5.0,
    'threshold': 10.0,
    'unit': '¥',
}

SUBSCRIPTION_ARGS = {
    'subscription_name': 'Netflix',
    'renewal_day': 15,
    'days_until_renewal': 3,
    'amount': 15.99,
}

# (调度方法名, 自定义 webhook 的处理方法名, 调用参数, 正文中应出现的名称)
ALERT_CASES = [
    ('send_balance_alert', '_send_custom_balance_alert', BALANCE_ARGS, 'TestProject'),
    ('send_subscription_alert', '_send_custom_subscription_alert', SUBSCRIPTION_ARGS, 'Netflix'),
]


def _message_text(webhook_type, payload):
    """取出指定平台 payload 中的正文文本"""
    outer, inner = _TEXT_FIELD[webhook_type]
    return payload[outer][inner]


def _mock_response(status_code, text=''):
    """构造 requests 响应替身"""
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


@pytest.fixture
def adapter_with_session():
    """工厂 fixture：创建 adapter 并注入 mock session，返回 (adapter, mock_session)"""
    def _make(webhook_type='feishu', *, response=None, side_effect=None):
        adapter = WebhookAdapter(WEBHOOK_URL, webhook_type)
        mock_session = MagicMock()
        if side_effect is not None:
            mock_session.post.side_effect = side_effect
        else:
            mock_session.post.return_value = response
        adapter._session = mock_session
        return adapter, mock_session

    return _make


class TestWebhookAdapterInit:
    """WebhookAdapter 初始化测试"""

    @pytest.mark.parametrize('given_type, expected_type', [
        ('feishu', 'feishu'),          # 飞书类型
        ('dingtalk', 'dingtalk'),      # 钉钉类型
        ('wecom', 'wecom'),            # 企业微信类型
        ('custom', 'custom'),          # 自定义类型
        ('unknown_type', 'custom'),    # 未知类型回退为 custom
        ('Feishu', 'feishu'),          # 类型大小写不敏感
    ])
    def test_init_type_normalization(self, given_type, expected_type):
        """测试各类型初始化与归一化"""
        adapter = WebhookAdapter(WEBHOOK_URL, given_type)
        assert adapter.webhook_url == WEBHOOK_URL
        assert adapter.webhook_type == expected_type
        assert adapter.source == 'credit-monitor'

    @pytest.mark.parametrize('kwargs, expected_type, expected_source', [
        ({'webhook_type': 'feishu', 'source': 'my-app'}, 'feishu', 'my-app'),  # 自定义来源
        ({}, 'custom', 'credit-monitor'),                                      # 默认类型 + 默认来源
    ])
    def test_init_defaults(self, kwargs, expected_type, expected_source):
        """测试类型与来源的默认值/覆盖"""
        adapter = WebhookAdapter(WEBHOOK_URL, **kwargs)
        assert adapter.webhook_type == expected_type
        assert adapter.source == expected_source


class TestAlertDispatch:
    """余额告警 / 订阅告警发送调度测试"""

    @pytest.mark.parametrize('method_name, _custom_handler, alert_args, expected_name', ALERT_CASES)
    @pytest.mark.parametrize('webhook_type, payload_key, payload_value', DISPATCH_CASES)
    def test_dispatch_builds_payload(self, method_name, _custom_handler, alert_args, expected_name,
                                     webhook_type, payload_key, payload_value):
        """测试飞书/钉钉/企业微信按平台格式包装 payload 后发送"""
        with patch.object(WebhookAdapter, '_send_request', return_value=True) as mock_send:
            adapter = WebhookAdapter(WEBHOOK_URL, webhook_type)
            result = getattr(adapter, method_name)(**alert_args)

        assert result is True
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload[payload_key] == payload_value
        assert expected_name in _message_text(webhook_type, payload)

    @pytest.mark.parametrize('method_name, custom_handler, alert_args, _expected_name', ALERT_CASES)
    def test_dispatch_custom(self, method_name, custom_handler, alert_args, _expected_name):
        """测试自定义 webhook 走专属的 _send_custom_* 方法"""
        with patch.object(WebhookAdapter, custom_handler, return_value=True) as mock_send:
            adapter = WebhookAdapter(WEBHOOK_URL, 'custom')
            result = getattr(adapter, method_name)(**alert_args)

        assert result is True
        mock_send.assert_called_once()


class TestSendCustomAlert:
    """自定义告警发送调度测试"""

    @pytest.mark.parametrize('webhook_type, handler_name', [
        ('feishu', '_send_feishu_custom'),
        ('dingtalk', '_send_dingtalk_custom'),
        ('wecom', '_send_wecom_custom'),
        ('custom', '_send_custom_webhook_custom'),
    ])
    def test_dispatch_by_type(self, webhook_type, handler_name):
        """测试按 webhook 类型调度到对应的处理方法"""
        with patch.object(WebhookAdapter, handler_name, return_value=True) as mock_send:
            adapter = WebhookAdapter(WEBHOOK_URL, webhook_type)
            result = adapter.send_custom_alert('标题', '内容')

        assert result is True
        mock_send.assert_called_once_with('标题', '内容')

    def test_exception_returns_false(self):
        """测试发送异常时返回 False"""
        adapter = WebhookAdapter(WEBHOOK_URL, 'feishu')
        with patch.object(adapter, '_send_feishu_custom', side_effect=RuntimeError('boom')):
            result = adapter.send_custom_alert('标题', '内容')
            assert result is False


class TestSendRequest:
    """HTTP 请求发送与重试行为测试"""

    def test_mask_webhook_url(self):
        """日志中的 webhook URL 不应暴露完整 token"""
        masked = _mask_webhook_url('https://open.feishu.cn/open-apis/bot/v2/hook/abcdef1234567890')
        assert 'abcdef1234567890' not in masked
        assert masked.endswith('abcd***')

        masked_query = _mask_webhook_url('https://example.com/hook?access_token=secret-token-value')
        assert 'secret-token-value' not in masked_query

    @pytest.mark.parametrize('webhook_type, status_code, text, expected, expected_calls', [
        ('feishu', 200, 'OK', True, 1),                          # 发送成功
        ('custom', 201, 'Created', True, 1),                     # 2xx 均视为成功
        ('feishu', 400, 'Bad Request', False, 1),                # 4xx 客户端错误不重试
        ('feishu', 404, 'Not Found', False, 1),                  # 4xx 客户端错误不重试
        ('feishu', 500, 'Internal Server Error', False, 3),      # 5xx 触发 tenacity 重试 3 次
        ('feishu', 502, 'Bad Gateway', False, 3),                # 5xx 触发 tenacity 重试 3 次
    ])
    def test_status_code_handling(self, adapter_with_session, webhook_type, status_code,
                                  text, expected, expected_calls):
        """测试各 HTTP 状态码的返回值与重试次数"""
        adapter, mock_session = adapter_with_session(
            webhook_type, response=_mock_response(status_code, text)
        )

        assert adapter._send_request(SAMPLE_PAYLOAD) is expected
        assert mock_session.post.call_count == expected_calls

    @pytest.mark.parametrize('exception, expected_calls', [
        (requests.exceptions.Timeout('Connection timed out'), 3),        # 超时触发重试
        (requests.exceptions.ConnectionError('Connection refused'), 3),  # 连接错误触发重试
        (RuntimeError('Unexpected error'), 1),                           # 未预期异常不重试
        (ValueError('unexpected'), 1),                                   # 未预期异常不重试
    ])
    def test_exception_handling(self, adapter_with_session, exception, expected_calls):
        """测试异常场景的返回值与重试次数"""
        adapter, mock_session = adapter_with_session(side_effect=exception)

        assert adapter._send_request(SAMPLE_PAYLOAD) is False
        assert mock_session.post.call_count == expected_calls

    def test_retry_then_success(self, adapter_with_session):
        """第一次超时，第二次成功"""
        adapter, mock_session = adapter_with_session(side_effect=[
            requests.exceptions.Timeout('timeout'),
            _mock_response(200, 'OK'),
        ])

        result = adapter._send_request(SAMPLE_PAYLOAD)

        assert result is True
        assert mock_session.post.call_count == 2


class TestFromSettings:
    """按环境变量构建 adapter"""

    def test_full_env(self, monkeypatch):
        monkeypatch.setenv('WEBHOOK_URL', 'https://open.feishu.cn/open-apis/bot/v2/hook/token')
        monkeypatch.setenv('WEBHOOK_TYPE', 'feishu')
        monkeypatch.setenv('WEBHOOK_SOURCE', 'balance-alert')
        adapter = WebhookAdapter.from_settings('fallback-source')
        assert adapter is not None
        assert adapter.webhook_url == 'https://open.feishu.cn/open-apis/bot/v2/hook/token'
        assert adapter.webhook_type == 'feishu'
        assert adapter.source == 'balance-alert'

    def test_defaults_when_only_url(self, monkeypatch):
        monkeypatch.delenv('WEBHOOK_TYPE', raising=False)
        monkeypatch.delenv('WEBHOOK_SOURCE', raising=False)
        monkeypatch.setenv('WEBHOOK_URL', 'https://example.com/hook/x')
        adapter = WebhookAdapter.from_settings('my-source')
        assert adapter.webhook_type == 'custom'
        assert adapter.source == 'my-source'

    def test_none_when_url_unset(self, monkeypatch):
        monkeypatch.delenv('WEBHOOK_URL', raising=False)
        assert WebhookAdapter.from_settings('src') is None


class TestSupportedTypes:
    """支持类型常量测试"""

    def test_supported_types_list(self):
        """测试支持的类型列表"""
        assert 'feishu' in WebhookAdapter.SUPPORTED_TYPES
        assert 'dingtalk' in WebhookAdapter.SUPPORTED_TYPES
        assert 'wecom' in WebhookAdapter.SUPPORTED_TYPES
        assert 'custom' in WebhookAdapter.SUPPORTED_TYPES
        assert len(WebhookAdapter.SUPPORTED_TYPES) == 4


class TestFormatDaysText:
    """_format_days_text 静态方法测试（Phase 3.2）"""

    @pytest.mark.parametrize('days, expected', [
        (0, "今天"),
        (1, "明天"),
        (3, "3 天后"),
        (30, "30 天后"),
    ])
    def test_format_days_text(self, days, expected):
        """0/1 天返回今天/明天，其余返回 N 天后"""
        assert WebhookAdapter._format_days_text(days) == expected


class TestBuildBalanceText:
    """_build_balance_text 方法测试（Phase 3.2）"""

    def test_contains_all_fields(self):
        """生成文本包含所有字段"""
        adapter = WebhookAdapter(WEBHOOK_URL, 'feishu')
        text = adapter._build_balance_text('MyProject', 'openrouter', '余额', 5.0, 10.0, '')
        assert 'MyProject' in text
        assert 'openrouter' in text
        assert '5.00' in text
        assert '10.00' in text
        assert '余额不足' in text


class TestBuildSubscriptionText:
    """_build_subscription_text 方法测试（Phase 3.2）"""

    def test_contains_all_fields(self):
        """生成文本包含所有字段"""
        adapter = WebhookAdapter(WEBHOOK_URL, 'feishu')
        text = adapter._build_subscription_text('Netflix', 15, 3, 15.99)

        assert 'Netflix' in text
        assert '15' in text
        assert '3 天后' in text

        assert '15.99' in text

    def test_uses_format_days_text(self):
        """使用 _format_days_text 格式化天数"""
        adapter = WebhookAdapter(WEBHOOK_URL, 'feishu')
        text = adapter._build_subscription_text('Spotify', 1, 0, 9.99)
        assert '今天' in text

    def test_yearly_mmdd_text(self):
        """年付 MMDD 不应被渲染成每月 N 号"""
        adapter = WebhookAdapter(WEBHOOK_URL, 'feishu')
        text = adapter._build_subscription_text('Annual', 315, 3, 99.0, cycle_type='yearly')
        assert '每年 3月15日' in text
        assert '每月 315 号' not in text


class TestWrapPayload:
    """_wrap_payload 方法测试（Phase 3.2）"""

    def test_feishu_payload(self):
        """飞书格式 payload"""
        adapter = WebhookAdapter(WEBHOOK_URL, 'feishu')
        payload = adapter._wrap_payload('测试标题', '内容行1\n内容行2')

        assert payload['msg_type'] == 'text'
        assert '测试标题' in payload['content']['text']
        assert '内容行1' in payload['content']['text']
        assert 'credit-monitor' in payload['content']['text']

    def test_dingtalk_payload(self):
        """钉钉格式 payload"""
        adapter = WebhookAdapter(WEBHOOK_URL, 'dingtalk')
        payload = adapter._wrap_payload('测试标题', '项目: Test\n余额: 100')

        assert payload['msgtype'] == 'markdown'
        assert payload['markdown']['title'] == '测试标题'
        assert '## 测试标题' in payload['markdown']['text']

    def test_wecom_payload(self):
        """企业微信格式 payload"""
        adapter = WebhookAdapter(WEBHOOK_URL, 'wecom')
        payload = adapter._wrap_payload('测试标题', '内容')

        assert payload['msgtype'] == 'text'
        assert '测试标题' in payload['text']['content']
        assert '内容' in payload['text']['content']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
