"""
Webhook 适配器测试
"""
import pytest
import requests
from unittest.mock import patch, MagicMock, PropertyMock
from services.webhook_adapter import WebhookAdapter, _mask_webhook_url


class TestWebhookAdapterInit:
    """WebhookAdapter 初始化测试"""

    def test_init_feishu(self):
        """测试飞书类型初始化"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        assert adapter.webhook_url == 'https://example.com/hook'
        assert adapter.webhook_type == 'feishu'
        assert adapter.source == 'credit-monitor'

    def test_init_dingtalk(self):
        """测试钉钉类型初始化"""
        adapter = WebhookAdapter('https://example.com/hook', 'dingtalk')
        assert adapter.webhook_type == 'dingtalk'

    def test_init_wecom(self):
        """测试企业微信类型初始化"""
        adapter = WebhookAdapter('https://example.com/hook', 'wecom')
        assert adapter.webhook_type == 'wecom'

    def test_init_custom(self):
        """测试自定义类型初始化"""
        adapter = WebhookAdapter('https://example.com/hook', 'custom')
        assert adapter.webhook_type == 'custom'

    def test_init_unknown_type_fallback_to_custom(self):
        """测试未知类型回退为 custom"""
        adapter = WebhookAdapter('https://example.com/hook', 'unknown_type')
        assert adapter.webhook_type == 'custom'

    def test_init_case_insensitive(self):
        """测试类型大小写不敏感"""
        adapter = WebhookAdapter('https://example.com/hook', 'Feishu')
        assert adapter.webhook_type == 'feishu'

    def test_init_custom_source(self):
        """测试自定义来源"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu', source='my-app')
        assert adapter.source == 'my-app'

    def test_init_default_source(self):
        """测试默认来源"""
        adapter = WebhookAdapter('https://example.com/hook')
        assert adapter.source == 'credit-monitor'

    def test_init_default_type(self):
        """测试默认类型为 custom"""
        adapter = WebhookAdapter('https://example.com/hook')
        assert adapter.webhook_type == 'custom'


class TestSendBalanceAlert:
    """余额告警发送调度测试"""

    def setup_method(self):
        """初始化通用参数"""
        self.alert_args = {
            'project_name': 'TestProject',
            'provider': 'openrouter',
            'balance_type': '余额',
            'current_value': 5.0,
            'threshold': 10.0,
            'unit': '¥',
        }

    @patch.object(WebhookAdapter, '_send_request', return_value=True)
    def test_dispatch_feishu(self, mock_send):
        """测试飞书余额告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        result = adapter.send_balance_alert(**self.alert_args)
        assert result is True
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload['msg_type'] == 'text'
        assert 'TestProject' in payload['content']['text']

    @patch.object(WebhookAdapter, '_send_request', return_value=True)
    def test_dispatch_dingtalk(self, mock_send):
        """测试钉钉余额告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'dingtalk')
        result = adapter.send_balance_alert(**self.alert_args)
        assert result is True
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload['msgtype'] == 'markdown'

    @patch.object(WebhookAdapter, '_send_request', return_value=True)
    def test_dispatch_wecom(self, mock_send):
        """测试企业微信余额告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'wecom')
        result = adapter.send_balance_alert(**self.alert_args)
        assert result is True
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload['msgtype'] == 'text'

    @patch.object(WebhookAdapter, '_send_custom_balance_alert', return_value=True)
    def test_dispatch_custom(self, mock_send):
        """测试自定义余额告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'custom')
        result = adapter.send_balance_alert(**self.alert_args)
        assert result is True
        mock_send.assert_called_once()


class TestSendSubscriptionAlert:
    """订阅告警发送调度测试"""

    def setup_method(self):
        """初始化通用参数"""
        self.alert_args = {
            'subscription_name': 'Netflix',
            'renewal_day': 15,
            'days_until_renewal': 3,
            'amount': 15.99,
            
        }

    @patch.object(WebhookAdapter, '_send_request', return_value=True)
    def test_dispatch_feishu(self, mock_send):
        """测试飞书订阅告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        result = adapter.send_subscription_alert(**self.alert_args)
        assert result is True
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload['msg_type'] == 'text'
        assert 'Netflix' in payload['content']['text']

    @patch.object(WebhookAdapter, '_send_request', return_value=True)
    def test_dispatch_dingtalk(self, mock_send):
        """测试钉钉订阅告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'dingtalk')
        result = adapter.send_subscription_alert(**self.alert_args)
        assert result is True
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload['msgtype'] == 'markdown'

    @patch.object(WebhookAdapter, '_send_request', return_value=True)
    def test_dispatch_wecom(self, mock_send):
        """测试企业微信订阅告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'wecom')
        result = adapter.send_subscription_alert(**self.alert_args)
        assert result is True
        mock_send.assert_called_once()
        payload = mock_send.call_args[0][0]
        assert payload['msgtype'] == 'text'

    @patch.object(WebhookAdapter, '_send_custom_subscription_alert', return_value=True)
    def test_dispatch_custom(self, mock_send):
        """测试自定义订阅告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'custom')
        result = adapter.send_subscription_alert(**self.alert_args)
        assert result is True
        mock_send.assert_called_once()


class TestSendCustomAlert:
    """自定义告警发送调度测试"""

    @patch.object(WebhookAdapter, '_send_feishu_custom', return_value=True)
    def test_dispatch_feishu(self, mock_send):
        """测试飞书自定义告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        result = adapter.send_custom_alert('标题', '内容')
        assert result is True
        mock_send.assert_called_once_with('标题', '内容')

    @patch.object(WebhookAdapter, '_send_dingtalk_custom', return_value=True)
    def test_dispatch_dingtalk(self, mock_send):
        """测试钉钉自定义告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'dingtalk')
        result = adapter.send_custom_alert('标题', '内容')
        assert result is True
        mock_send.assert_called_once_with('标题', '内容')

    @patch.object(WebhookAdapter, '_send_wecom_custom', return_value=True)
    def test_dispatch_wecom(self, mock_send):
        """测试企业微信自定义告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'wecom')
        result = adapter.send_custom_alert('标题', '内容')
        assert result is True
        mock_send.assert_called_once_with('标题', '内容')

    @patch.object(WebhookAdapter, '_send_custom_webhook_custom', return_value=True)
    def test_dispatch_custom(self, mock_send):
        """测试自定义 webhook 自定义告警调度"""
        adapter = WebhookAdapter('https://example.com/hook', 'custom')
        result = adapter.send_custom_alert('标题', '内容')
        assert result is True
        mock_send.assert_called_once_with('标题', '内容')

    def test_exception_returns_false(self):
        """测试发送异常时返回 False"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        with patch.object(adapter, '_send_feishu_custom', side_effect=RuntimeError('boom')):
            result = adapter.send_custom_alert('标题', '内容')
            assert result is False


class TestSendRequest:
    """HTTP 请求发送测试"""

    def test_mask_webhook_url(self):
        """日志中的 webhook URL 不应暴露完整 token"""
        masked = _mask_webhook_url('https://open.feishu.cn/open-apis/bot/v2/hook/abcdef1234567890')
        assert 'abcdef1234567890' not in masked
        assert masked.endswith('abcd***')

        masked_query = _mask_webhook_url('https://example.com/hook?access_token=secret-token-value')
        assert 'secret-token-value' not in masked_query

    def test_send_request_success_200(self):
        """测试发送成功 (HTTP 200)"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = 'OK'

        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text', 'content': {'text': 'test'}})

        assert result is True
        mock_session.post.assert_called_once()

    def test_send_request_success_201(self):
        """测试发送成功 (HTTP 201)"""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = 'Created'

        adapter = WebhookAdapter('https://example.com/hook', 'custom')
        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        adapter._session = mock_session

        result = adapter._send_request({'key': 'value'})
        assert result is True

    def test_send_request_http_500(self):
        """测试 HTTP 500 错误"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'

        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text'})
        assert result is False

    def test_send_request_http_404(self):
        """测试 HTTP 404 错误"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = 'Not Found'

        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()
        mock_session.post.return_value = mock_response
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text'})
        assert result is False

    def test_send_request_timeout(self):
        """测试请求超时"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()
        mock_session.post.side_effect = requests.exceptions.Timeout('Connection timed out')
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text'})
        assert result is False

    def test_send_request_connection_error(self):
        """测试连接错误"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()
        mock_session.post.side_effect = requests.exceptions.ConnectionError('Connection refused')
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text'})
        assert result is False

    def test_send_request_unexpected_exception(self):
        """测试未预期的异常"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()
        mock_session.post.side_effect = RuntimeError('Unexpected error')
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text'})
        assert result is False


class TestSupportedTypes:
    """支持类型常量测试"""

    def test_supported_types_list(self):
        """测试支持的类型列表"""
        assert 'feishu' in WebhookAdapter.SUPPORTED_TYPES
        assert 'dingtalk' in WebhookAdapter.SUPPORTED_TYPES
        assert 'wecom' in WebhookAdapter.SUPPORTED_TYPES
        assert 'custom' in WebhookAdapter.SUPPORTED_TYPES
        assert len(WebhookAdapter.SUPPORTED_TYPES) == 4


class TestRetryBehavior:
    """Webhook 重试行为测试"""

    def test_timeout_triggers_retry(self):
        """超时触发重试，最终返回 False"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()
        mock_session.post.side_effect = requests.exceptions.Timeout('timeout')
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text', 'content': {'text': 'test'}})

        assert result is False
        # tenacity 重试 3 次
        assert mock_session.post.call_count == 3

    def test_connection_error_triggers_retry(self):
        """连接错误触发重试"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()
        mock_session.post.side_effect = requests.exceptions.ConnectionError('refused')
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text'})

        assert result is False
        assert mock_session.post.call_count == 3

    def test_4xx_no_retry(self):
        """4xx 客户端错误不重试"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = 'Bad Request'
        mock_session.post.return_value = mock_resp
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text'})

        assert result is False
        assert mock_session.post.call_count == 1  # 无重试

    def test_5xx_triggers_retry(self):
        """5xx 服务端错误触发重试"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 502
        mock_resp.text = 'Bad Gateway'
        mock_session.post.return_value = mock_resp
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text'})

        assert result is False
        # 5xx 抛出 ConnectionError → 被 tenacity 重试 3 次
        assert mock_session.post.call_count == 3

    def test_retry_then_success(self):
        """第一次超时，第二次成功"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()

        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.text = 'OK'

        mock_session.post.side_effect = [
            requests.exceptions.Timeout('timeout'),
            success_resp
        ]
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text'})

        assert result is True
        assert mock_session.post.call_count == 2

    def test_unexpected_exception_no_retry(self):
        """非超时/连接错误不触发重试"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        mock_session = MagicMock()
        mock_session.post.side_effect = ValueError('unexpected')
        adapter._session = mock_session

        result = adapter._send_request({'msg_type': 'text'})

        assert result is False
        assert mock_session.post.call_count == 1


class TestFormatDaysText:
    """_format_days_text 静态方法测试（Phase 3.2）"""

    def test_today(self):
        """0 天返回今天"""
        assert WebhookAdapter._format_days_text(0) == "今天"

    def test_tomorrow(self):
        """1 天返回明天"""
        assert WebhookAdapter._format_days_text(1) == "明天"

    def test_multiple_days(self):
        """多天返回 N 天后"""
        assert WebhookAdapter._format_days_text(3) == "3 天后"
        assert WebhookAdapter._format_days_text(30) == "30 天后"


class TestBuildBalanceText:
    """_build_balance_text 方法测试（Phase 3.2）"""

    def test_contains_all_fields(self):
        """生成文本包含所有字段"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
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
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        text = adapter._build_subscription_text('Netflix', 15, 3, 15.99)

        assert 'Netflix' in text
        assert '15' in text
        assert '3 天后' in text
        
        assert '15.99' in text

    def test_uses_format_days_text(self):
        """使用 _format_days_text 格式化天数"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        text = adapter._build_subscription_text('Spotify', 1, 0, 9.99)
        assert '今天' in text

    def test_yearly_mmdd_text(self):
        """年付 MMDD 不应被渲染成每月 N 号"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        text = adapter._build_subscription_text('Annual', 315, 3, 99.0, cycle_type='yearly')
        assert '每年 3月15日' in text
        assert '每月 315 号' not in text


class TestWrapPayload:
    """_wrap_payload 方法测试（Phase 3.2）"""

    def test_feishu_payload(self):
        """飞书格式 payload"""
        adapter = WebhookAdapter('https://example.com/hook', 'feishu')
        payload = adapter._wrap_payload('测试标题', '内容行1\n内容行2')

        assert payload['msg_type'] == 'text'
        assert '测试标题' in payload['content']['text']
        assert '内容行1' in payload['content']['text']
        assert 'credit-monitor' in payload['content']['text']

    def test_dingtalk_payload(self):
        """钉钉格式 payload"""
        adapter = WebhookAdapter('https://example.com/hook', 'dingtalk')
        payload = adapter._wrap_payload('测试标题', '项目: Test\n余额: 100')

        assert payload['msgtype'] == 'markdown'
        assert payload['markdown']['title'] == '测试标题'
        assert '## 测试标题' in payload['markdown']['text']

    def test_wecom_payload(self):
        """企业微信格式 payload"""
        adapter = WebhookAdapter('https://example.com/hook', 'wecom')
        payload = adapter._wrap_payload('测试标题', '内容')

        assert payload['msgtype'] == 'text'
        assert '测试标题' in payload['text']['content']
        assert '内容' in payload['text']['content']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
