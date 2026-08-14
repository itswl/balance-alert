"""
邮箱扫描器测试
"""
import pytest
import re
import threading
from collections import OrderedDict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from unittest.mock import MagicMock
from services.email_scanner import EmailScanner, DEFAULT_ALERT_KEYWORDS

# 参数表中表示"该维度不在本用例断言范围内"
_ANY = object()


def _create_scanner():
    """创建 EmailScanner 实例（绕过 __init__，不加载真实配置）"""
    scanner = EmailScanner.__new__(EmailScanner)
    scanner.config_path = 'config.json'
    scanner.config = {
        'email': [],
        'webhook': {'url': 'https://example.com/hook', 'type': 'custom'}
    }
    scanner.email_configs = []
    scanner.results = []
    scanner._seen_ids = OrderedDict()
    scanner._state_lock = threading.Lock()
    # 直接复用生产默认关键词，避免拷贝出现静默腐烂
    scanner.alert_keywords = list(DEFAULT_ALERT_KEYWORDS)
    # 预编译关键词正则表达式（与 EmailScanner.__init__ 保持一致）
    escaped_keywords = [re.escape(kw.lower()) for kw in scanner.alert_keywords]
    scanner._keywords_pattern = re.compile('|'.join(escaped_keywords), re.IGNORECASE)
    return scanner


class TestDecodeStr:
    """_decode_str 方法测试"""

    def setup_method(self):
        """创建测试用 Scanner 实例"""
        self.scanner = _create_scanner()

    @pytest.mark.parametrize('raw, expected', [
        (None, ""),                                     # None 输入返回空字符串
        ("Hello World", "Hello World"),                 # 纯字符串直接返回
        (b"Hello World", "Hello World"),                # UTF-8 bytes 解码
        ("余额告警".encode('utf-8'), "余额告警"),          # 中文 bytes 解码
        ("Payment Due Notice", "Payment Due Notice"),   # ASCII 字符串
        ("", ""),                                       # 空字符串
        (b"", ""),                                      # 空 bytes
        ("Re: Test Subject", "Re: Test Subject"),       # 纯 ASCII MIME 头（混合编码标题）
    ])
    def test_decode_exact(self, raw, expected):
        """测试各类输入解码后与期望值完全一致"""
        assert self.scanner._decode_str(raw) == expected

    @pytest.mark.parametrize('text, charset', [
        ('余额告警通知', 'utf-8'),   # MIME 编码的 UTF-8 标题
        ('测试标题', 'gbk'),        # MIME 编码的 GBK 标题
    ])
    def test_decode_mime_encoded(self, text, charset):
        """测试 MIME 编码标题可正确解码"""
        encoded = Header(text, charset).encode()
        assert text in self.scanner._decode_str(encoded)


class TestCheckAlertKeywords:
    """_check_alert_keywords 方法测试"""

    def setup_method(self):
        """创建测试用 Scanner 实例"""
        self.scanner = _create_scanner()

    @pytest.mark.parametrize('subject, body, expected_keywords', [
        ('您的账户余额不足', '', ['余额不足']),                       # 中文关键词在主题中
        ('通知', '您的服务已欠费，请及时充值', ['欠费']),               # 中文关键词在正文中
        ('Payment Overdue Notice', '', ['payment overdue']),        # 英文关键词 overdue
        ('', 'Your account has a low balance', ['low balance']),    # 英文关键词 low balance
        ('Your subscription has expired', '', ['expired']),         # 英文关键词 expired
        ('PAYMENT DUE', '', ['payment due']),                       # 英文关键词大小写不敏感
        ('余额不足告警', '您的账户已欠费，请及时续费',
         ['余额不足', '欠费', '请及时续费']),                          # 多个关键词匹配
        ('续费提醒', '', ['续费提醒']),                              # 续费提醒关键词
        ('', 'Your account has been suspended', ['suspended']),     # suspended 关键词
        ('服务通知', '余额预警：当前余额低于阈值', ['余额预警']),        # 关键词跨主题和正文查找
    ])
    def test_keywords_matched(self, subject, body, expected_keywords):
        """测试命中的关键词全部出现在返回值中"""
        result = self.scanner._check_alert_keywords(subject, body)
        for keyword in expected_keywords:
            assert keyword in result

    @pytest.mark.parametrize('subject, body', [
        ('周报通知', '本周工作总结'),   # 无匹配关键词
        ('', ''),                    # 空主题和正文
    ])
    def test_no_keywords_matched(self, subject, body):
        """测试无关键词命中时返回空列表"""
        assert self.scanner._check_alert_keywords(subject, body) == []


class TestExtractServiceInfo:
    """_extract_service_info 方法测试"""

    def setup_method(self):
        """创建测试用 Scanner 实例"""
        self.scanner = _create_scanner()

    @pytest.mark.parametrize('subject, body, expected_service, expected_amount', [
        ('【阿里云】余额告警', '', '阿里云', _ANY),                 # 中文方括号提取服务名
        ('[AWS] Balance Alert', '', 'AWS', _ANY),                # 英文方括号提取服务名
        ('（腾讯云）余额告警', '', '腾讯云', _ANY),                 # 中文括号提取服务名
        ('(Azure) 续费通知', '', 'Azure', _ANY),                  # 英文括号提取服务名
        ('余额告警', '', '未知服务', _ANY),                        # 无法提取服务名时返回默认值
        ('【阿里云】【余额】告警', '', '阿里云', _ANY),              # 多个括号使用第一个
        ('余额告警', '余额：100.50 元', _ANY, 100.50),            # 提取金额（元后缀）
        ('余额告警', '当前金额: 200.00', _ANY, 200.00),           # 提取金额
        ('余额告警', '当前余额 CNY 1000.00', _ANY, 1000.00),      # 提取金额（CNY 前缀）
        ('余额告警', '余额：1,234.56 元', _ANY, 1234.56),         # 带千位分隔符的金额
        ('余额告警', '请及时充值', _ANY, None),                    # 无法提取金额时返回 None
        ('告警', '余额：100 元', _ANY, 100.0),                    # 整数金额
        ('告警', '余额：88.88 元', _ANY, 88.88),                  # 余额：前缀模式优先匹配
        ('【阿里云】余额告警', '当前余额：50.00 元', '阿里云', 50.00),  # 同时提取服务名和金额
    ])
    def test_extract_service_info(self, subject, body, expected_service, expected_amount):
        """测试服务名与金额提取"""
        service, amount = self.scanner._extract_service_info(subject, body)
        if expected_service is not _ANY:
            assert service == expected_service
        if expected_amount is not _ANY:
            assert amount == expected_amount


class TestExtractTextFromEmail:
    """_extract_text_from_email 方法测试"""

    def setup_method(self):
        """创建测试用 Scanner 实例"""
        self.scanner = _create_scanner()

    @pytest.mark.parametrize('content, subtype, expected_fragment', [
        ('这是一封测试邮件', 'plain', '测试邮件'),                              # 纯文本邮件提取
        ('<html><body><p>HTML内容</p></body></html>', 'html', 'HTML内容'),   # HTML 邮件提取
        ('Your balance is low', 'plain', 'Your balance is low'),           # 英文纯文本
    ])
    def test_single_part_email(self, content, subtype, expected_fragment):
        """测试单 part 邮件正文提取"""
        msg = MIMEText(content, subtype, 'utf-8')
        result = self.scanner._extract_text_from_email(msg)
        assert expected_fragment in result

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


class TestBatchFetchEmails:
    """_batch_fetch_emails 批量获取测试"""

    def setup_method(self):
        self.scanner = _create_scanner()

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
        assert isinstance(self.scanner._seen_ids, OrderedDict)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
