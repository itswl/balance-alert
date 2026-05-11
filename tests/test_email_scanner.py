"""
邮箱扫描器测试
"""
import pytest
import re
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from unittest.mock import patch, MagicMock
from services.email_scanner import EmailScanner


def _create_scanner():
    """创建 EmailScanner 实例（跳过真实配置加载）"""
    with patch.object(EmailScanner, '_load_config', return_value={
        'email': [],
        'webhook': {'url': 'https://example.com/hook', 'type': 'custom'}
    }):
        with patch.object(EmailScanner, '_parse_email_configs', return_value=[]):
            scanner = EmailScanner.__new__(EmailScanner)
            scanner.config_path = 'config.json'
            scanner.config = {
                'email': [],
                'webhook': {'url': 'https://example.com/hook', 'type': 'custom'}
            }
            scanner.email_configs = []
            scanner.results = []
            scanner.alert_keywords = [
                # 中文关键词
                '欠费', '余额不足', '余额预警', '余额告警',
                '即将到期', '已到期', '续费提醒', '续费通知',
                '账单逾期', '缴费通知', '请及时续费', '停机',
                '暂停服务', '服务即将暂停', '充值提醒',
                # 英文关键词
                'overdue', 'past due', 'payment due', 'payment overdue',
                'low balance', 'insufficient balance', 'balance alert',
                'expiring soon', 'expired', 'expiration notice',
                'renewal reminder', 'renewal notice', 'renew now',
                'payment reminder', 'payment required', 'bill overdue',
                'service suspension', 'service suspended', 'suspended',
                'recharge reminder', 'top up', 'account suspended',
                'unpaid invoice', 'outstanding balance', 'payment failed'
            ]
            # 预编译关键词正则表达式（与 EmailScanner.__init__ 保持一致）
            escaped_keywords = [re.escape(kw.lower()) for kw in scanner.alert_keywords]
            scanner._keywords_pattern = re.compile('|'.join(escaped_keywords), re.IGNORECASE)
            return scanner


class TestDecodeStr:
    """_decode_str 方法测试"""

    def setup_method(self):
        """创建测试用 Scanner 实例"""
        self.scanner = _create_scanner()

    def test_decode_none(self):
        """测试 None 输入返回空字符串"""
        result = self.scanner._decode_str(None)
        assert result == ""

    def test_decode_plain_str(self):
        """测试纯字符串直接返回"""
        result = self.scanner._decode_str("Hello World")
        assert result == "Hello World"

    def test_decode_bytes_utf8(self):
        """测试 UTF-8 bytes 解码"""
        result = self.scanner._decode_str(b"Hello World")
        assert result == "Hello World"

    def test_decode_bytes_chinese(self):
        """测试中文 bytes 解码"""
        result = self.scanner._decode_str("余额告警".encode('utf-8'))
        assert result == "余额告警"

    def test_decode_mime_encoded_utf8(self):
        """测试 MIME 编码的 UTF-8 标题"""
        header = Header('余额告警通知', 'utf-8')
        encoded = header.encode()
        result = self.scanner._decode_str(encoded)
        assert '余额告警通知' in result

    def test_decode_mime_encoded_gbk(self):
        """测试 MIME 编码的 GBK 标题"""
        header = Header('测试标题', 'gbk')
        encoded = header.encode()
        result = self.scanner._decode_str(encoded)
        assert '测试标题' in result

    def test_decode_ascii_string(self):
        """测试 ASCII 字符串"""
        result = self.scanner._decode_str("Payment Due Notice")
        assert result == "Payment Due Notice"

    def test_decode_empty_string(self):
        """测试空字符串"""
        result = self.scanner._decode_str("")
        assert result == ""

    def test_decode_empty_bytes(self):
        """测试空 bytes"""
        result = self.scanner._decode_str(b"")
        assert result == ""

    def test_decode_mixed_encoding_header(self):
        """测试混合编码标题"""
        # 纯 ASCII MIME 头
        result = self.scanner._decode_str("Re: Test Subject")
        assert result == "Re: Test Subject"


class TestCheckAlertKeywords:
    """_check_alert_keywords 方法测试"""

    def setup_method(self):
        """创建测试用 Scanner 实例"""
        self.scanner = _create_scanner()

    def test_chinese_keyword_in_subject(self):
        """测试中文关键词在主题中"""
        result = self.scanner._check_alert_keywords('您的账户余额不足', '')
        assert '余额不足' in result

    def test_chinese_keyword_in_body(self):
        """测试中文关键词在正文中"""
        result = self.scanner._check_alert_keywords('通知', '您的服务已欠费，请及时充值')
        assert '欠费' in result

    def test_english_keyword_overdue(self):
        """测试英文关键词 overdue"""
        result = self.scanner._check_alert_keywords('Payment Overdue Notice', '')
        assert 'payment overdue' in result

    def test_english_keyword_low_balance(self):
        """测试英文关键词 low balance"""
        result = self.scanner._check_alert_keywords('', 'Your account has a low balance')
        assert 'low balance' in result

    def test_english_keyword_expired(self):
        """测试英文关键词 expired"""
        result = self.scanner._check_alert_keywords('Your subscription has expired', '')
        assert 'expired' in result

    def test_case_insensitive_english(self):
        """测试英文关键词大小写不敏感"""
        result = self.scanner._check_alert_keywords('PAYMENT DUE', '')
        assert 'payment due' in result

    def test_no_keywords_matched(self):
        """测试无匹配关键词"""
        result = self.scanner._check_alert_keywords('周报通知', '本周工作总结')
        assert result == []

    def test_multiple_keywords_matched(self):
        """测试多个关键词匹配"""
        result = self.scanner._check_alert_keywords('余额不足告警', '您的账户已欠费，请及时续费')
        assert '余额不足' in result
        assert '欠费' in result
        assert '请及时续费' in result

    def test_empty_subject_and_body(self):
        """测试空主题和正文"""
        result = self.scanner._check_alert_keywords('', '')
        assert result == []

    def test_keyword_renewal_reminder(self):
        """测试续费提醒关键词"""
        result = self.scanner._check_alert_keywords('续费提醒', '')
        assert '续费提醒' in result

    def test_english_keyword_suspended(self):
        """测试 suspended 关键词"""
        result = self.scanner._check_alert_keywords('', 'Your account has been suspended')
        assert 'suspended' in result

    def test_keyword_in_combined_text(self):
        """测试关键词跨主题和正文查找"""
        result = self.scanner._check_alert_keywords('服务通知', '余额预警：当前余额低于阈值')
        assert '余额预警' in result


class TestExtractServiceInfo:
    """_extract_service_info 方法测试"""

    def setup_method(self):
        """创建测试用 Scanner 实例"""
        self.scanner = _create_scanner()

    def test_service_name_chinese_brackets(self):
        """测试从中文方括号提取服务名"""
        service, amount = self.scanner._extract_service_info('【阿里云】余额告警', '')
        assert service == '阿里云'

    def test_service_name_square_brackets(self):
        """测试从英文方括号提取服务名"""
        service, amount = self.scanner._extract_service_info('[AWS] Balance Alert', '')
        assert service == 'AWS'

    def test_service_name_chinese_parentheses(self):
        """测试从中文括号提取服务名"""
        service, amount = self.scanner._extract_service_info('（腾讯云）余额告警', '')
        assert service == '腾讯云'

    def test_service_name_english_parentheses(self):
        """测试从英文括号提取服务名"""
        service, amount = self.scanner._extract_service_info('(Azure) 续费通知', '')
        assert service == 'Azure'

    def test_service_name_not_found(self):
        """测试无法提取服务名时返回默认值"""
        service, amount = self.scanner._extract_service_info('余额告警', '')
        assert service == '未知服务'

    def test_amount_with_yuan_suffix(self):
        """测试提取金额（元后缀）"""
        service, amount = self.scanner._extract_service_info('余额告警', '余额：100.50 元')
        assert amount == 100.50

    def test_amount_with_currency_symbol(self):
        """测试提取金额"""
        service, amount = self.scanner._extract_service_info('余额告警', '当前金额: 200.00')
        assert amount == 200.00



    def test_amount_with_cny_prefix(self):
        """测试提取金额（CNY 前缀）"""
        service, amount = self.scanner._extract_service_info('余额告警', '当前余额 CNY 1000.00')
        assert amount == 1000.00

    def test_amount_with_comma_separator(self):
        """测试提取带千位分隔符的金额"""
        service, amount = self.scanner._extract_service_info('余额告警', '余额：1,234.56 元')
        assert amount == 1234.56

    def test_amount_not_found(self):
        """测试无法提取金额时返回 None"""
        service, amount = self.scanner._extract_service_info('余额告警', '请及时充值')
        assert amount is None

    def test_service_and_amount_together(self):
        """测试同时提取服务名和金额"""
        service, amount = self.scanner._extract_service_info(
            '【阿里云】余额告警', '当前余额：50.00 元'
        )
        assert service == '阿里云'
        assert amount == 50.00

    def test_amount_integer(self):
        """测试提取整数金额"""
        service, amount = self.scanner._extract_service_info('告警', '余额：100 元')
        assert amount == 100.0

    def test_amount_with_balance_prefix(self):
        """测试余额：前缀模式优先匹配"""
        service, amount = self.scanner._extract_service_info('告警', '余额：88.88 元')
        assert amount == 88.88

    def test_multiple_brackets_uses_first(self):
        """测试多个括号使用第一个"""
        service, amount = self.scanner._extract_service_info('【阿里云】【余额】告警', '')
        assert service == '阿里云'


class TestExtractTextFromEmail:
    """_extract_text_from_email 方法测试"""

    def setup_method(self):
        """创建测试用 Scanner 实例"""
        self.scanner = _create_scanner()

    def test_plain_text_email(self):
        """测试纯文本邮件提取"""
        msg = MIMEText('这是一封测试邮件', 'plain', 'utf-8')
        result = self.scanner._extract_text_from_email(msg)
        assert '测试邮件' in result

    def test_html_email(self):
        """测试 HTML 邮件提取"""
        msg = MIMEText('<html><body><p>HTML内容</p></body></html>', 'html', 'utf-8')
        result = self.scanner._extract_text_from_email(msg)
        assert 'HTML内容' in result

    def test_multipart_email(self):
        """测试多部分邮件提取"""
        msg = MIMEMultipart()
        msg.attach(MIMEText('纯文本部分', 'plain', 'utf-8'))
        msg.attach(MIMEText('<p>HTML部分</p>', 'html', 'utf-8'))

        result = self.scanner._extract_text_from_email(msg)
        assert '纯文本部分' in result

    def test_empty_email(self):
        """测试空邮件"""
        msg = MIMEMultipart()
        result = self.scanner._extract_text_from_email(msg)
        assert result == ''

    def test_email_with_attachment_skipped(self):
        """测试跳过附件"""
        msg = MIMEMultipart()
        msg.attach(MIMEText('正文内容', 'plain', 'utf-8'))

        attachment = MIMEText('附件内容', 'plain', 'utf-8')
        attachment.add_header('Content-Disposition', 'attachment', filename='test.txt')
        msg.attach(attachment)

        result = self.scanner._extract_text_from_email(msg)
        assert '正文内容' in result
        # 附件内容不应出现在提取文本中
        # 注意：附件的 content_type 仍为 text/plain，但 Content-Disposition 标记为 attachment

    def test_plain_text_english(self):
        """测试英文纯文本"""
        msg = MIMEText('Your balance is low', 'plain', 'utf-8')
        result = self.scanner._extract_text_from_email(msg)
        assert 'Your balance is low' in result


class TestBatchFetchEmails:
    """_batch_fetch_emails 批量获取测试"""

    def setup_method(self):
        self.scanner = _create_scanner()
        from collections import OrderedDict
        self.scanner._seen_ids = OrderedDict()

    def test_batch_fetch_success(self):
        """批量 fetch 成功返回解析后的消息"""
        mock_mail = MagicMock()
        # 模拟批量 fetch 响应：多个 (header, body) tuple + bytes 分隔符
        raw_msg1 = MIMEText('Message 1', 'plain', 'utf-8').as_bytes()
        raw_msg2 = MIMEText('Message 2', 'plain', 'utf-8').as_bytes()
        mock_mail.fetch.return_value = ('OK', [
            (b'1 (RFC822 {100}', raw_msg1),
            b')',
            (b'2 (RFC822 {100}', raw_msg2),
            b')',
        ])
        batch_ids = [b'1', b'2']
        messages = self.scanner._batch_fetch_emails(mock_mail, batch_ids)

        assert len(messages) == 2
        # 确认使用了批量 fetch（逗号分隔的 ID）
        mock_mail.fetch.assert_called_once_with(b'1,2', '(RFC822)')

    def test_batch_fetch_fallback_to_sequential(self):
        """批量 fetch 失败时降级为逐条获取"""
        mock_mail = MagicMock()
        raw_msg = MIMEText('Fallback msg', 'plain', 'utf-8').as_bytes()

        # 第一次调用（批量）失败，后续逐条调用成功
        mock_mail.fetch.side_effect = [
            Exception('batch failed'),
            ('OK', [(b'1 (RFC822 {100}', raw_msg)]),
            ('OK', [(b'2 (RFC822 {100}', raw_msg)]),
        ]
        batch_ids = [b'1', b'2']
        messages = self.scanner._batch_fetch_emails(mock_mail, batch_ids)

        assert len(messages) == 2
        assert mock_mail.fetch.call_count == 3  # 1 batch + 2 sequential


class TestBoundedSeenIds:
    """有界去重集合测试"""

    def setup_method(self):
        self.scanner = _create_scanner()
        from collections import OrderedDict
        self.scanner._seen_ids = OrderedDict()

    def test_seen_ids_eviction(self):
        """超过 MAX_SEEN_IDS 时淘汰最旧条目"""
        from services.email_scanner import MAX_SEEN_IDS

        # 填满 seen_ids
        for i in range(MAX_SEEN_IDS):
            self.scanner._seen_ids[f'id_{i}'] = None

        assert len(self.scanner._seen_ids) == MAX_SEEN_IDS
        assert 'id_0' in self.scanner._seen_ids

        # 添加一个新条目，触发淘汰
        self.scanner._seen_ids['new_id'] = None
        if len(self.scanner._seen_ids) > MAX_SEEN_IDS:
            self.scanner._seen_ids.popitem(last=False)

        assert len(self.scanner._seen_ids) == MAX_SEEN_IDS
        assert 'id_0' not in self.scanner._seen_ids  # 最旧的被淘汰
        assert 'new_id' in self.scanner._seen_ids  # 新的保留
        assert 'id_1' in self.scanner._seen_ids  # 第二旧的保留

    def test_seen_ids_is_ordered_dict(self):
        """验证 _seen_ids 是 OrderedDict"""
        from collections import OrderedDict
        assert isinstance(self.scanner._seen_ids, OrderedDict)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
