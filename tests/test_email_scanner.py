"""
邮箱扫描器测试
"""
import imaplib
import re
import threading
from contextlib import contextmanager
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch

import pytest

from services.email_scanner import DEFAULT_ALERT_KEYWORDS, EmailScanner

# 参数表中表示"该维度不在本用例断言范围内"
_ANY = object()


def _create_scanner():
    """创建 EmailScanner 实例（绕过 __init__，不加载真实配置）"""
    scanner = EmailScanner.__new__(EmailScanner)
    scanner.config_path = 'config.json'
    scanner.config = {'email': []}
    scanner.email_configs = []
    scanner.results = []
    # 直接复用生产默认关键词，避免拷贝出现静默腐烂
    scanner.alert_keywords = list(DEFAULT_ALERT_KEYWORDS)
    scanner._keywords_pattern = re.compile(
        '|'.join(re.escape(kw.lower()) for kw in scanner.alert_keywords), re.IGNORECASE
    )
    scanner._seen_ids = set()
    scanner._seen_lock = threading.Lock()
    return scanner


def _stat(cfg, **overrides):
    """_scan_single_mailbox 返回值的样板"""
    stat = {
        'name': cfg['name'], 'host': cfg.get('host'), 'port': cfg.get('port', 993), 'username': cfg.get('username'),
        'total_emails': 0, 'alert_count': 0, 'success': True, 'error': None, 'alerts': [],
    }
    stat.update(overrides)
    return stat


def _alert_message(subject='【阿里云】余额不足提醒', body='您的账户余额不足，请及时充值。余额：12.50元', message_id='<alert-1@aliyun.com>'):
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = 'noreply@aliyun.com'
    msg['Date'] = 'Mon, 01 Sep 2026 10:00:00 +0800'
    msg['Message-ID'] = message_id
    return msg


class TestDecodeStr:
    """_decode_str 方法测试"""

    def setup_method(self):
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
        assert self.scanner._decode_str(raw) == expected

    @pytest.mark.parametrize('text, charset', [
        ('余额告警通知', 'utf-8'),   # MIME 编码的 UTF-8 标题
        ('测试标题', 'gbk'),        # MIME 编码的 GBK 标题
    ])
    def test_decode_mime_encoded(self, text, charset):
        encoded = Header(text, charset).encode()
        assert text in self.scanner._decode_str(encoded)


class TestCheckAlertKeywords:
    """_check_alert_keywords 方法测试"""

    def setup_method(self):
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
        result = self.scanner._check_alert_keywords(subject, body)
        for keyword in expected_keywords:
            assert keyword in result

    @pytest.mark.parametrize('subject, body', [
        ('周报通知', '本周工作总结'),   # 无匹配关键词
        ('', ''),                    # 空主题和正文
    ])
    def test_no_keywords_matched(self, subject, body):
        assert self.scanner._check_alert_keywords(subject, body) == []


class TestExtractServiceInfo:
    """_extract_service_info 方法测试"""

    def setup_method(self):
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
        service, amount = self.scanner._extract_service_info(subject, body)
        if expected_service is not _ANY:
            assert service == expected_service
        if expected_amount is not _ANY:
            assert amount == expected_amount


class TestExtractTextFromEmail:
    """_extract_text_from_email 方法测试"""

    def setup_method(self):
        self.scanner = _create_scanner()

    @pytest.mark.parametrize('content, subtype, expected_fragment', [
        ('这是一封测试邮件', 'plain', '测试邮件'),                              # 纯文本邮件提取
        ('<html><body><p>HTML内容</p></body></html>', 'html', 'HTML内容'),   # HTML 邮件提取
        ('Your balance is low', 'plain', 'Your balance is low'),           # 英文纯文本
    ])
    def test_single_part_email(self, content, subtype, expected_fragment):
        msg = MIMEText(content, subtype, 'utf-8')
        assert expected_fragment in self.scanner._extract_text_from_email(msg)

    def test_single_part_html_tags_are_stripped(self):
        msg = MIMEText('<p>余额<b>不足</b></p>', 'html', 'utf-8')
        assert '<b>' not in self.scanner._extract_text_from_email(msg)

    def test_multipart_email(self):
        msg = MIMEMultipart()
        msg.attach(MIMEText('纯文本部分', 'plain', 'utf-8'))
        msg.attach(MIMEText('<p>HTML部分</p>', 'html', 'utf-8'))
        result = self.scanner._extract_text_from_email(msg)
        assert '纯文本部分' in result
        assert 'HTML部分' in result and '<p>' not in result

    def test_empty_email(self):
        assert self.scanner._extract_text_from_email(MIMEMultipart()) == ''

    def test_email_with_attachment_skipped(self):
        msg = MIMEMultipart()
        msg.attach(MIMEText('正文内容', 'plain', 'utf-8'))
        attachment = MIMEText('附件内容', 'plain', 'utf-8')
        attachment.add_header('Content-Disposition', 'attachment', filename='test.txt')
        msg.attach(attachment)

        result = self.scanner._extract_text_from_email(msg)
        assert '正文内容' in result
        assert '附件内容' not in result


class TestBatchFetchEmails:
    """_batch_fetch_emails 批量获取测试"""

    def setup_method(self):
        self.scanner = _create_scanner()

    def test_batch_fetch_success(self):
        mock_mail = MagicMock()
        raw_msg1 = MIMEText('Message 1', 'plain', 'utf-8').as_bytes()
        raw_msg2 = MIMEText('Message 2', 'plain', 'utf-8').as_bytes()
        mock_mail.fetch.return_value = ('OK', [
            (b'1 (RFC822 {100}', raw_msg1),
            b')',
            (b'2 (RFC822 {100}', raw_msg2),
            b')',
        ])
        messages = self.scanner._batch_fetch_emails(mock_mail, [b'1', b'2'])

        assert len(messages) == 2
        mock_mail.fetch.assert_called_once_with(b'1,2', '(RFC822)')

    def test_batch_fetch_fallback_to_sequential(self):
        mock_mail = MagicMock()
        raw_msg = MIMEText('Fallback msg', 'plain', 'utf-8').as_bytes()
        mock_mail.fetch.side_effect = [
            Exception('batch failed'),
            ('OK', [(b'1 (RFC822 {100}', raw_msg)]),
            ('OK', [(b'2 (RFC822 {100}', raw_msg)]),
        ]
        messages = self.scanner._batch_fetch_emails(mock_mail, [b'1', b'2'])

        assert len(messages) == 2
        assert mock_mail.fetch.call_count == 3  # 1 batch + 2 sequential


class TestInspectMessage:
    """单封邮件的判定：去重、关键词、dry_run 与数据库去重"""

    def setup_method(self):
        self.scanner = _create_scanner()

    def test_non_alert_message_returns_none(self):
        msg = _alert_message(subject='Weekly report', body='周报请查收')
        assert self.scanner._inspect_message(msg, 'A', 1, dry_run=True) is None

    def test_same_message_id_is_only_handled_once(self):
        first, second = _alert_message(), _alert_message()
        assert self.scanner._inspect_message(first, 'A', 1, dry_run=True) is not None
        assert self.scanner._inspect_message(second, 'B', 1, dry_run=True) is None  # 跨邮箱同一封邮件跳过

    def test_seen_ids_reset_per_scan(self):
        assert self.scanner._mark_seen('x') is True
        assert self.scanner._mark_seen('x') is False
        with patch('services.email_scanner.metrics_collector'):
            self.scanner.scan_emails(days=1, dry_run=True)
        assert self.scanner._mark_seen('x') is True

    def test_dry_run_neither_dedups_nor_sends(self):
        with patch('services.email_scanner.alert_store') as store, patch.object(self.scanner, '_send_alert') as send:
            alert = self.scanner._inspect_message(_alert_message(), 'A', 1, dry_run=True)
        assert alert['alert_sent'] is False and 'duplicate' not in alert
        assert alert['service_name'] == '阿里云' and alert['amount'] == 12.5 and '余额不足' in alert['keywords']
        store.email_alert_sent_recently.assert_not_called()
        send.assert_not_called()

    def test_recent_duplicate_is_skipped(self):
        with patch('services.email_scanner.alert_store') as store, patch.object(self.scanner, '_send_alert') as send:
            store.email_alert_sent_recently.return_value = True
            alert = self.scanner._inspect_message(_alert_message(), 'A', 3, dry_run=False)
        assert alert['duplicate'] is True and alert['alert_sent'] is False
        assert store.email_alert_sent_recently.call_args.kwargs['days'] == 3
        send.assert_not_called()

    def test_new_alert_is_sent(self):
        with patch('services.email_scanner.alert_store') as store, \
             patch.object(self.scanner, '_send_alert', return_value=True) as send:
            store.email_alert_sent_recently.return_value = False
            alert = self.scanner._inspect_message(_alert_message(), 'A', 1, dry_run=False)
        assert alert['alert_sent'] is True
        send.assert_called_once_with(alert)


class TestScanSummary:
    """scan_emails 的返回值：逐邮箱统计 + 告警明细，供 Web 页面展示"""

    def setup_method(self):
        self.scanner = _create_scanner()
        self.cfg_a = {'name': 'A', 'host': 'imap.a.com', 'port': 993, 'username': 'a@a.com', 'password': 'x'}
        self.cfg_b = {'name': 'B', 'host': 'imap.b.com', 'port': 143, 'username': 'b@b.com', 'password': 'y'}

    def test_without_mailboxes_returns_empty_summary(self):
        self.scanner.email_configs = []
        summary = self.scanner.scan_emails(days=3, dry_run=True)
        assert summary == {
            'days': 3, 'dry_run': True, 'mailboxes': [],
            'total_emails': 0, 'total_alerts': 0, 'alerts_sent': 0, 'results': [],
        }

    def test_aggregates_per_mailbox_in_config_order(self):
        self.scanner.email_configs = [self.cfg_a, self.cfg_b]

        def fake_scan(cfg, days, dry_run):
            if cfg['name'] == 'A':
                return _stat(cfg, total_emails=10, alert_count=1,
                             alerts=[{'mailbox': 'A', 'subject': '欠费', 'alert_sent': True}])
            return _stat(cfg, success=False, error='login failed')

        with patch.object(self.scanner, '_scan_single_mailbox', side_effect=fake_scan):
            summary = self.scanner.scan_emails(days=1, dry_run=False)

        assert [m['name'] for m in summary['mailboxes']] == ['A', 'B']
        a, b = summary['mailboxes']
        assert a['success'] is True and a['total_emails'] == 10 and a['alert_count'] == 1
        assert a['host'] == 'imap.a.com' and a['port'] == 993 and a['username'] == 'a@a.com'
        assert 'alerts' not in a  # 明细统一放在 results
        assert b['success'] is False and b['error'] == 'login failed' and b['total_emails'] == 0
        assert summary['total_emails'] == 10
        assert summary['total_alerts'] == 1
        assert summary['alerts_sent'] == 1
        assert summary['results'][0]['subject'] == '欠费'
        assert summary['days'] == 1 and summary['dry_run'] is False
        assert self.scanner.results == summary['results']

    def test_rescan_resets_previous_results(self):
        self.scanner.email_configs = [self.cfg_a]
        self.scanner.results.append({'mailbox': 'stale', 'alert_sent': True})
        with patch.object(self.scanner, '_scan_single_mailbox', return_value=_stat(self.cfg_a, total_emails=2)):
            summary = self.scanner.scan_emails(days=1, dry_run=True)
        assert summary['results'] == [] and self.scanner.results == []
        assert summary['mailboxes'][0]['success'] is True

    def test_connection_failure_marks_mailbox_failed(self):
        with patch('services.email_scanner.imap_connection', side_effect=imaplib.IMAP4.error('login failed')), \
             patch.object(self.scanner, '_send_error_alert') as error_alert:
            stat = self.scanner._scan_single_mailbox(self.cfg_a, days=1, dry_run=True)
        assert stat['success'] is False and stat['error'] == 'login failed'
        error_alert.assert_not_called()  # dry_run 不发系统告警

        with patch('services.email_scanner.imap_connection', side_effect=imaplib.IMAP4.error('login failed')), \
             patch.object(self.scanner, '_send_error_alert') as error_alert:
            self.scanner._scan_single_mailbox(self.cfg_a, days=1, dry_run=False)
        error_alert.assert_called_once_with('A', 'login failed')

    def test_incomplete_config_is_recorded(self):
        stat = self.scanner._scan_single_mailbox({'name': 'bad', 'host': 'imap.x.com'}, days=1, dry_run=True)
        assert stat['success'] is False
        assert '配置不完整' in stat['error']
        assert stat['alerts'] == []

    def test_publishes_metrics_once_per_scan(self):
        """无论有没有邮箱，一次 scan_emails 只推一次指标，推的就是返回的汇总"""
        self.scanner.email_configs = []
        with patch('services.email_scanner.metrics_collector') as collector:
            summary = self.scanner.scan_emails(days=1, dry_run=True)
        collector.update_email_metrics.assert_called_once_with(summary)

        self.scanner.email_configs = [self.cfg_a]
        with patch.object(self.scanner, '_scan_single_mailbox', return_value=_stat(self.cfg_a, total_emails=4)), \
             patch('services.email_scanner.metrics_collector') as collector:
            summary = self.scanner.scan_emails(days=1, dry_run=True)
        collector.update_email_metrics.assert_called_once_with(summary)
        assert summary['mailboxes'][0]['total_emails'] == 4

    def test_display_name_falls_back_to_username(self):
        assert EmailScanner._mailbox_display_name({'username': 'u@x.com'}) == 'u@x.com'
        assert EmailScanner._mailbox_display_name({}) == '(未命名)'

    def test_scan_single_mailbox_end_to_end_with_mocked_imap(self):
        """走真实的单邮箱扫描流程（IMAP 用 mock），确认命中邮件进入 results 且统计正确"""
        alert_msg = _alert_message()
        normal_msg = MIMEText('周报请查收', 'plain', 'utf-8')
        normal_msg['Subject'] = 'Weekly report'
        normal_msg['From'] = 'boss@example.com'
        normal_msg['Message-ID'] = '<weekly-1@example.com>'

        mock_mail = MagicMock()
        mock_mail.search.return_value = ('OK', [b'1 2'])
        mock_mail.fetch.return_value = ('OK', [
            (b'1 (RFC822 {100}', alert_msg.as_bytes()), b')',
            (b'2 (RFC822 {100}', normal_msg.as_bytes()), b')',
        ])

        @contextmanager
        def fake_connection(*args, **kwargs):
            yield mock_mail

        self.scanner.email_configs = [self.cfg_a]
        with patch('services.email_scanner.imap_connection', fake_connection):
            summary = self.scanner.scan_emails(days=1, dry_run=True)

        assert summary['total_emails'] == 2
        assert summary['total_alerts'] == 1
        assert summary['alerts_sent'] == 0  # dry_run 不发通知
        mailbox = summary['mailboxes'][0]
        assert mailbox['success'] is True and mailbox['total_emails'] == 2 and mailbox['alert_count'] == 1
        alert = summary['results'][0]
        assert alert['mailbox'] == 'A'
        assert alert['subject'] == '【阿里云】余额不足提醒'
        assert alert['service_name'] == '阿里云'
        assert alert['amount'] == 12.5
        assert '余额不足' in alert['keywords']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
