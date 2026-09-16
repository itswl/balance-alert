#!/usr/bin/env python3
"""
邮箱扫描器 - 检测欠费、续费等提醒邮件

流程：每个邮箱一个线程 → IMAP 拉最近 N 天的邮件 → 关键词匹配 → 提取服务名 / 金额 →
发 Webhook 通知（数据库可用时按邮件去重）。每个邮箱的扫描结果自成一个字典，
最后汇总成一份 summary 给命令行、Web 页面和 Prometheus 用。
"""
import email
import hashlib
import imaplib
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from email.header import decode_header
from typing import Any, Dict, List, Optional, Tuple

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config_loader import filter_enabled, load_config
from core.logger import get_logger
from core.settings import get_settings
from services import alert_store
from services.prometheus_exporter import metrics_collector
from services.webhook_adapter import WebhookAdapter

logger = get_logger('email_scanner')

BATCH_SIZE = 100         # 一次 IMAP FETCH 拉多少封
MAX_MAILBOX_WORKERS = 5  # 同时扫描的邮箱数

# 默认告警关键词，可用 EMAIL_ALERT_KEYWORDS 整体替换、EMAIL_EXTRA_ALERT_KEYWORDS 追加
DEFAULT_ALERT_KEYWORDS = [
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

# 服务名一般写在主题的括号里：【阿里云】/ [AWS] / （腾讯云）/ (Azure)
_SERVICE_PATTERNS = [r'【(.+?)】', r'\[(.+?)\]', r'（(.+?)）', r'\((.+?)\)']
_AMOUNT_PATTERNS = [
    r'余额[：:]\s*([0-9,]+\.?[0-9]*)\s*元',
    r'金额[：:]\s*([0-9,]+\.?[0-9]*)',
    r'([0-9,]+\.?[0-9]*)\s*元',
    r'CNY\s*([0-9,]+\.?[0-9]*)',
]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((imaplib.IMAP4.error, ConnectionError, TimeoutError)),
    reraise=True
)
def _open_imap(host: str, port: int, username: str, password: str, use_ssl: bool = True):
    logger.info(f"正在连接IMAP服务器 {host}:{port} (SSL: {use_ssl})")
    mail = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
    mail.login(username, password)
    mail.select('INBOX')
    return mail


@contextmanager
def imap_connection(host: str, port: int, username: str, password: str, use_ssl: bool = True):
    """IMAP 连接上下文管理器：连接失败直接抛出，退出时 logout"""
    mail = _open_imap(host, port, username, password, use_ssl)
    logger.info(f"成功连接到邮箱 {username}@{host}")
    try:
        yield mail
    finally:
        try:
            mail.logout()
        except Exception as e:
            logger.warning(f"断开邮箱连接时出错: {e}")


class EmailScanner:
    """邮箱扫描器"""

    def __init__(self):
        self.email_configs = filter_enabled(load_config().get('email') or [])
        self.results: List[Dict[str, Any]] = []  # 上次扫描命中的告警邮件
        self.alert_keywords = self._load_keywords()
        self._keywords_pattern = re.compile(
            '|'.join(re.escape(kw.lower()) for kw in self.alert_keywords), re.IGNORECASE
        )
        # 同一封邮件（Message-ID）在本次扫描里只处理一次，多个邮箱并发共享
        self._seen_ids: set = set()
        self._seen_lock = threading.Lock()

    @staticmethod
    def _load_keywords() -> List[str]:
        """EMAIL_ALERT_KEYWORDS 整体替换默认表，EMAIL_EXTRA_ALERT_KEYWORDS 在其上追加"""
        settings = get_settings()
        keywords = settings.alert_keyword_override or list(DEFAULT_ALERT_KEYWORDS)
        return keywords + settings.alert_keyword_extras

    # ---------- 扫描 ----------

    def scan_emails(self, days=1, dry_run=False) -> Dict[str, Any]:
        """
        扫描所有启用的邮箱

        Args:
            days: 扫描最近几天的邮件（默认1天）
            dry_run: 测试模式，不发送告警、不做去重

        Returns:
            dict: days / dry_run / mailboxes（逐邮箱统计与错误）/ total_emails / total_alerts /
                  alerts_sent / results（告警邮件明细）
        """
        self._seen_ids = set()
        if not self.email_configs:
            logger.error("未配置邮箱信息或所有邮箱均已禁用")
            mailboxes: List[Dict[str, Any]] = []
        else:
            logger.info(f"开始扫描 {len(self.email_configs)} 个邮箱，范围: 最近 {days} 天")
            with ThreadPoolExecutor(max_workers=min(len(self.email_configs), MAX_MAILBOX_WORKERS)) as pool:
                mailboxes = list(pool.map(lambda cfg: self._scan_single_mailbox(cfg, days, dry_run), self.email_configs))

        self.results = [alert for mailbox in mailboxes for alert in mailbox.pop('alerts')]
        summary = {
            'days': days,
            'dry_run': dry_run,
            'mailboxes': mailboxes,
            'total_emails': sum(m['total_emails'] for m in mailboxes),
            'total_alerts': sum(m['alert_count'] for m in mailboxes),
            'alerts_sent': sum(1 for r in self.results if r.get('alert_sent')),
            'results': self.results,
        }
        if mailboxes:
            logger.info(
                f"邮箱扫描总汇总: 邮箱数={len(mailboxes)}, 总邮件={summary['total_emails']}, "
                f"告警邮件={summary['total_alerts']}, 已发送告警={summary['alerts_sent']}"
            )
        metrics_collector.update_email_metrics(summary)
        return summary

    @staticmethod
    def _mailbox_display_name(email_config: Dict[str, Any]) -> str:
        return str(email_config.get('name') or email_config.get('username') or '(未命名)')

    def _scan_single_mailbox(self, email_config: Dict[str, Any], days: int, dry_run: bool) -> Dict[str, Any]:
        """扫描一个邮箱，返回它的统计与命中的告警邮件；任何失败都记进 error，不向外抛"""
        host, port = email_config.get('host'), email_config.get('port', 993)
        username, password = email_config.get('username'), email_config.get('password')
        stat = {
            'name': self._mailbox_display_name(email_config),
            'host': host, 'port': port, 'username': username,
            'total_emails': 0, 'alert_count': 0, 'success': True, 'error': None, 'alerts': [],
        }
        if not (host and username and password):
            logger.warning(f"邮箱 {stat['name']} 配置不完整，跳过")
            stat.update(success=False, error='配置不完整，需要 host / username / password')
            return stat

        try:
            with imap_connection(host, port, username, password, email_config.get('use_ssl', True)) as mail:
                self._scan_inbox(mail, stat, days, dry_run)
        except Exception as e:
            stat.update(success=False, error=str(e))
            logger.error(f"[{stat['name']}] 扫描失败: {e}", exc_info=not isinstance(e, imaplib.IMAP4.error))
            if not dry_run:
                self._send_error_alert(stat['name'], str(e))
        return stat

    def _scan_inbox(self, mail, stat: Dict[str, Any], days: int, dry_run: bool) -> None:
        """在已连接的邮箱里逐批检查邮件，命中的告警写进 stat"""
        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'SINCE {since}')
        email_ids = messages[0].split() if status == 'OK' else []
        if not email_ids:
            logger.info(f"[{stat['name']}] 没有需要检查的邮件")
            return

        limit = max(1, get_settings().max_emails_to_scan)
        if len(email_ids) > limit:
            logger.warning(f"[{stat['name']}] 邮件数量 {len(email_ids)} 超过上限 {limit}，仅扫描最新 {limit} 封")
            email_ids = email_ids[-limit:]
        stat['total_emails'] = len(email_ids)
        logger.info(f"[{stat['name']}] 找到 {len(email_ids)} 封邮件")

        for start in range(0, len(email_ids), BATCH_SIZE):
            for msg in self._batch_fetch_emails(mail, email_ids[start:start + BATCH_SIZE]):
                alert = self._inspect_message(msg, stat['name'], days, dry_run)
                if alert:
                    stat['alert_count'] += 1
                    stat['alerts'].append(alert)
            logger.info(f"[{stat['name']}] 扫描进度: {min(start + BATCH_SIZE, len(email_ids))}/{len(email_ids)}")

        logger.info(f"[{stat['name']}] 扫描汇总: 总邮件={stat['total_emails']}, 告警邮件={stat['alert_count']}")

    def _inspect_message(self, msg, mailbox_name: str, days: int, dry_run: bool) -> Optional[Dict[str, Any]]:
        """判断一封邮件是否告警邮件；是则（按需）发送通知并返回明细，否则返回 None"""
        if not self._mark_seen(self._get_email_id(msg)):
            return None

        subject, sender, date, body = self._parse_message(msg)
        matched_keywords = self._check_alert_keywords(subject, body)
        if not matched_keywords:
            return None

        service_name, amount = self._extract_service_info(subject, body)
        alert = {
            'mailbox': mailbox_name, 'subject': subject, 'sender': sender, 'date': date,
            'keywords': matched_keywords, 'service_name': service_name, 'amount': amount,
            'alert_sent': False,
        }
        logger.warning(
            f"发现告警邮件 | 邮箱: {mailbox_name} | 发件人: {sender} | 主题: {subject} | 日期: {date} | "
            f"关键词: {', '.join(matched_keywords)} | 服务: {service_name}" + (f" | 金额: {amount}" if amount else "")
        )

        if dry_run:
            logger.info("[测试模式] 跳过发送告警")
        elif alert_store.email_alert_sent_recently(mailbox_name, sender, subject, date, days=max(days, 1)):
            alert['duplicate'] = True
            logger.info(f"邮件告警已发送过，跳过重复通知 | 邮箱: {mailbox_name} | 主题: {subject}")
        else:
            alert['alert_sent'] = self._send_alert(alert)
        return alert

    def _mark_seen(self, email_uid: str) -> bool:
        with self._seen_lock:
            if email_uid in self._seen_ids:
                return False
            self._seen_ids.add(email_uid)
            return True

    # ---------- 邮件解析 ----------

    def _batch_fetch_emails(self, mail, batch_ids):
        """批量获取邮件，失败时降级为逐条获取"""
        try:
            status, msg_data = mail.fetch(b','.join(batch_ids), '(RFC822)')
            if status == 'OK':
                return [email.message_from_bytes(item[1]) for item in msg_data if isinstance(item, tuple)]
        except Exception as e:
            logger.warning(f"批量 fetch 失败，降级为逐条获取: {e}")

        messages = []
        for email_id in batch_ids:
            try:
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                if status == 'OK':
                    messages.append(email.message_from_bytes(msg_data[0][1]))
            except Exception as e:
                logger.warning(f"获取邮件 {email_id} 失败: {e}")
        return messages

    def _parse_message(self, msg) -> Tuple[str, str, str, str]:
        return (
            self._decode_str(msg.get('Subject', '')),
            self._decode_str(msg.get('From', '')),
            self._decode_str(msg.get('Date', '')),
            self._extract_text_from_email(msg),
        )

    def _decode_str(self, s) -> str:
        """解码邮件标题或内容（支持 MIME 编码头）"""
        if s is None:
            return ""
        if isinstance(s, bytes):
            s = s.decode('utf-8', errors='ignore')
        try:
            return ''.join(
                content.decode(encoding or 'utf-8', errors='ignore') if isinstance(content, bytes) else str(content)
                for content, encoding in decode_header(s)
            )
        except (UnicodeDecodeError, LookupError):
            return str(s)

    def _extract_text_from_email(self, msg) -> str:
        """取出正文文本：text/plain 直接用，text/html 去掉标签，附件跳过"""
        texts = []
        for part in (msg.walk() if msg.is_multipart() else [msg]):
            if 'attachment' in str(part.get('Content-Disposition')):
                continue
            content_type = part.get_content_type()
            if content_type not in ('text/plain', 'text/html'):
                continue
            try:
                payload = part.get_payload(decode=True)
                text = payload.decode(part.get_content_charset() or 'utf-8', errors='ignore') if payload else ''
            except (UnicodeDecodeError, LookupError, AttributeError):
                continue
            if content_type == 'text/html':
                text = re.sub(r'<[^>]+>', ' ', text)
            if text:
                texts.append(text)
        return '\n'.join(texts)

    def _check_alert_keywords(self, subject: str, body: str) -> List[str]:
        """返回命中的关键词（保持配置里的原始大小写与顺序）"""
        matched = {m.lower() for m in self._keywords_pattern.findall(f"{subject}\n{body}")}
        return [kw for kw in self.alert_keywords if kw.lower() in matched] if matched else []

    def _get_email_id(self, msg) -> str:
        """邮件唯一标识，优先 Message-ID，回退 md5(date|subject|from)"""
        message_id = (msg.get('Message-ID') or '').strip()
        if message_id:
            return message_id
        raw = f"{msg.get('Date', '')}|{msg.get('Subject', '')}|{msg.get('From', '')}"
        return hashlib.md5(raw.encode('utf-8', errors='ignore')).hexdigest()

    def _extract_service_info(self, subject: str, body: str):
        """从主题括号里提取服务名，从正文提取金额；提不到时分别为 '未知服务' / None"""
        service_name = "未知服务"
        for pattern in _SERVICE_PATTERNS:
            matches = re.findall(pattern, subject)
            if matches:
                service_name = matches[0]
                break

        amount = None
        full_text = f"{subject}\n{body}"
        for pattern in _AMOUNT_PATTERNS:
            matched = re.search(pattern, full_text)
            if matched:
                try:
                    amount = float(matched.group(1).replace(',', ''))
                    break
                except ValueError:
                    continue
        return service_name, amount

    # ---------- 通知 ----------

    def _send_error_alert(self, mailbox_name, error_msg) -> bool:
        """邮箱连接失败时发一条系统告警"""
        adapter = WebhookAdapter.from_settings('email-scanner')
        if adapter is None:
            return False
        content = (
            f"**邮箱**: {mailbox_name}\n**错误信息**: {error_msg}\n"
            f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        return adapter.send_custom_alert("❌ 邮箱连接失败告警", content, kind='mailbox_error')

    def _send_alert(self, email_info) -> bool:
        """发送告警邮件通知并留痕"""
        adapter = WebhookAdapter.from_settings('email-scanner')
        if adapter is None:
            logger.error("未配置 webhook 地址")
            return False

        lines = [
            f"**邮箱**: {email_info.get('mailbox', '未知')}",
            f"**发件人**: {email_info['sender']}",
            f"**日期**: {email_info['date']}",
            f"**服务**: {email_info['service_name']}",
        ]
        if email_info['amount']:
            lines.append(f"**金额**: {email_info['amount']}")
        lines.append(f"**关键词**: {', '.join(email_info['keywords'])}")

        alert_sent = adapter.send_custom_alert(f"📧 邮件告警: {email_info['subject']}", '\n'.join(lines), kind='email')
        alert_store.record_email_alert(
            mailbox=email_info.get('mailbox', '未知'),
            sender=email_info['sender'],
            subject=email_info['subject'],
            date=email_info['date'],
            service_name=email_info['service_name'],
            amount=email_info['amount'],
            matched_keywords=email_info['keywords'],
            alert_sent=alert_sent,
        )
        return alert_sent


def main():
    """命令行入口：手动扫描一次"""
    import argparse

    parser = argparse.ArgumentParser(description='邮箱告警扫描器')
    parser.add_argument('--days', type=int, default=1, help='扫描最近几天的邮件（默认1天）')
    parser.add_argument('--dry-run', action='store_true', help='测试模式，不发送告警')
    args = parser.parse_args()

    try:
        EmailScanner().scan_emails(days=args.days, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
