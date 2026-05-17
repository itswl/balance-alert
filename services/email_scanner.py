#!/usr/bin/env python3
"""
邮箱扫描器 - 检测欠费、续费等提醒邮件
支持重试机制和连接池
"""
import imaplib
import email
import hashlib
import os
import sys
from email.header import decode_header
import re
from datetime import datetime, timedelta
from collections import OrderedDict
from contextlib import contextmanager
from typing import Optional, Dict, Any, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from services.webhook_adapter import WebhookAdapter
from core.logger import get_logger

# 创建 logger
logger = get_logger('email_scanner')

# 邮件扫描常量
DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_EMAILS = 1000
MAX_SEEN_IDS = 10000

# 默认告警关键词
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

def _get_max_emails_to_scan() -> int:
    try:
        return max(1, int(os.environ.get('MAX_EMAILS_TO_SCAN', str(DEFAULT_MAX_EMAILS))))
    except (TypeError, ValueError):
        return DEFAULT_MAX_EMAILS


def _iter_batches(items, batch_size: int):
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((imaplib.IMAP4.error, ConnectionError, TimeoutError)),
    reraise=True
)
def _open_imap(host: str, port: int, username: str, password: str, use_ssl: bool = True):
    logger.info(f"正在连接IMAP服务器 {host}:{port} (SSL: {use_ssl})")
    if use_ssl:
        mail = imaplib.IMAP4_SSL(host, port)
    else:
        mail = imaplib.IMAP4(host, port)

    mail.login(username, password)
    mail.select('INBOX')
    logger.info("✅ IMAP连接成功")
    return mail


def _record_email_scan_metrics(mailbox_name: str, total_emails: int, alert_count: int) -> None:
    try:
        from services.prometheus_exporter import metrics_collector
        metrics_collector.record_email_scan(mailbox_name, total_emails, alert_count)
    except Exception:
        return None


@contextmanager
def imap_connection(host: str, port: int, username: str, password: str, use_ssl: bool = True):
    """IMAP连接上下文管理器"""
    mail = None
    try:
        mail = _open_imap(host, port, username, password, use_ssl)
        logger.info(f"✅ 成功连接到邮箱 {username}@{host}")
        yield mail
    except Exception as e:
        logger.error(f"❌ 邮箱连接失败: {e}", exc_info=True)
        raise
    finally:
        if mail:
            try:
                mail.logout()
                logger.info(f"   已断开邮箱连接 {username}@{host}")
            except Exception as e:
                logger.warning(f"   断开连接时出错: {e}", exc_info=True)


class EmailScanner:
    """邮箱扫描器"""
    
    def __init__(self, config_path='config.json'):
        """
        初始化邮箱扫描器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.email_configs = self._parse_email_configs()
        self.results = []
        self._seen_ids = OrderedDict()  # 邮件去重集合（有界，FIFO 淘汰）

        # 关键词匹配规则（支持配置覆盖和追加）
        email_settings = self.config.get('email_settings', {})
        custom_keywords = email_settings.get('alert_keywords')
        extra_keywords = email_settings.get('extra_alert_keywords', [])

        if custom_keywords is not None:
            # 完全替换默认关键词
            self.alert_keywords = list(custom_keywords)
        else:
            self.alert_keywords = list(DEFAULT_ALERT_KEYWORDS)

        # 追加额外关键词
        if extra_keywords:
            self.alert_keywords.extend(extra_keywords)

        # 预编译关键词正则表达式（性能优化）
        escaped_keywords = [re.escape(kw.lower()) for kw in self.alert_keywords]
        self._keywords_pattern = re.compile('|'.join(escaped_keywords), re.IGNORECASE)
    
    def _load_config(self):
        """加载配置文件"""
        from services.config_service import load_config
        return load_config(self.config_path)
    
    def _parse_email_configs(self):
        """解析邮箱配置，支持单个或多个邮箱"""
        email_config = self.config.get('email', [])
        
        # 如果是列表，直接返回
        if isinstance(email_config, list):
            return [cfg for cfg in email_config if cfg.get('enabled', True)]
        
        # 如果是字典，转换为单元素列表
        if isinstance(email_config, dict):
            if email_config.get('enabled', True):
                return [email_config]
        
        return []
    
    def _decode_str(self, s):
        """解码邮件标题或内容"""
        if s is None:
            return ""
        
        if isinstance(s, bytes):
            s = s.decode('utf-8', errors='ignore')
        
        # 尝试解码 MIME 编码的标题
        try:
            decoded_parts = decode_header(s)
            result = []
            for content, encoding in decoded_parts:
                if isinstance(content, bytes):
                    if encoding:
                        result.append(content.decode(encoding, errors='ignore'))
                    else:
                        result.append(content.decode('utf-8', errors='ignore'))
                else:
                    result.append(str(content))
            return ''.join(result)
        except (UnicodeDecodeError, LookupError) as e:
            # 解码失败，返回原始字符串
            return str(s)
    
    def _mark_seen(self, email_uid: str) -> bool:
        if email_uid in self._seen_ids:
            return False
        self._seen_ids[email_uid] = None
        if len(self._seen_ids) > MAX_SEEN_IDS:
            self._seen_ids.popitem(last=False)
        return True

    def _extract_text_from_email(self, msg):
        """从邮件中提取文本内容"""
        text_content = []
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # 跳过附件
                if "attachment" in content_disposition:
                    continue
                
                # 提取文本内容
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            text_content.append(payload.decode(charset, errors='ignore'))
                    except (UnicodeDecodeError, LookupError, AttributeError) as e:
                        # 解码失败，跳过此部分
                        pass
                elif content_type == "text/html":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or 'utf-8'
                            html_text = payload.decode(charset, errors='ignore')
                            # 简单去除 HTML 标签
                            clean_text = re.sub(r'<[^>]+>', ' ', html_text)
                            text_content.append(clean_text)
                    except (UnicodeDecodeError, LookupError, AttributeError) as e:
                        # 解码失败，跳过此部分
                        pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or 'utf-8'
                    text_content.append(payload.decode(charset, errors='ignore'))
            except (UnicodeDecodeError, LookupError, AttributeError) as e:
                # 解码失败，跳过
                pass
        
        return '\n'.join(text_content)
    
    def _check_alert_keywords(self, subject, body):
        """检查是否包含告警关键词（不区分大小写，使用预编译正则）"""
        full_text = f"{subject}\n{body}"
        matches = self._keywords_pattern.findall(full_text)
        if not matches:
            return []
        # 将匹配结果映射回原始关键词（保持大小写）
        matched_lower = set(m.lower() for m in matches)
        return [kw for kw in self.alert_keywords if kw.lower() in matched_lower]
    
    def _get_email_id(self, msg) -> str:
        """获取邮件唯一标识，优先 Message-ID，回退 md5(date|subject|from)"""
        message_id = msg.get('Message-ID', '').strip()
        if message_id:
            return message_id
        # 回退方案：用 date+subject+from 的哈希
        date = msg.get('Date', '')
        subject = msg.get('Subject', '')
        sender = msg.get('From', '')
        raw = f"{date}|{subject}|{sender}"
        return hashlib.md5(raw.encode('utf-8', errors='ignore')).hexdigest()

    def _extract_service_info(self, subject, body):
        """尝试从邮件中提取服务名称和金额信息"""
        full_text = f"{subject}\n{body}"
        
        service_name = "未知服务"
        amount = None
        
        # 尝试提取服务名称（简单规则）
        service_patterns = [
            r'【(.+?)】',  # 【服务名】
            r'\[(.+?)\]',  # [服务名]
            r'（(.+?)）',  # （服务名）
            r'\((.+?)\)',  # (服务名)
        ]
        
        for pattern in service_patterns:
            matches = re.findall(pattern, subject)
            if matches:
                service_name = matches[0]
                break
        
        # 尝试提取金额
        amount_patterns = [
            r'余额[：:]\s*([0-9,]+\.?[0-9]*)\s*元',
            r'金额[：:]\s*([0-9,]+\.?[0-9]*)',
            r'([0-9,]+\.?[0-9]*)\s*元',
            r'CNY\s*([0-9,]+\.?[0-9]*)'
        ]
        
        for pattern in amount_patterns:
            matches = re.search(pattern, full_text)
            if matches:
                try:
                    amount_str = matches.group(1).replace(',', '')
                    amount = float(amount_str)
                    break
                except (ValueError, IndexError) as e:
                    # 金额解析失败，继续尝试其他模式
                    pass
        
        return service_name, amount

    def _get_webhook_adapter(self, default_source: str) -> Optional[WebhookAdapter]:
        webhook_config = self.config.get('webhook', {})
        webhook_url = webhook_config.get('url')
        if not webhook_url:
            return None

        webhook_type = webhook_config.get('type', 'custom')
        webhook_source = webhook_config.get('source', default_source)
        return WebhookAdapter(webhook_url, webhook_type, webhook_source)

    def _has_recent_email_alert(self, mailbox: str, sender: str, subject: str, date: str, days: int) -> bool:
        try:
            from database.repository import EmailRepository
            return EmailRepository.has_recent_email_alert(
                mailbox=mailbox,
                sender=sender,
                subject=subject,
                date=date,
                days=days
            )
        except Exception as e:
            logger.error(f"查询邮件告警去重失败: {e}", exc_info=True)
            return False

    def _parse_message(self, msg):
        subject = self._decode_str(msg.get('Subject', ''))
        sender = self._decode_str(msg.get('From', ''))
        date = self._decode_str(msg.get('Date', ''))
        body = self._extract_text_from_email(msg)
        return subject, sender, date, body

    def _is_valid_mailbox_config(self, email_config: Dict[str, Any]) -> bool:
        host = email_config.get('host')
        username = email_config.get('username')
        password = email_config.get('password')
        return bool(host and username and password)

    def _search_email_ids(self, mail, days: int):
        since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'SINCE {since_date}')
        if status != 'OK':
            return []
        return messages[0].split()

    def _apply_scan_limit(self, email_ids):
        max_scan_limit = _get_max_emails_to_scan()
        if len(email_ids) <= max_scan_limit:
            return email_ids, max_scan_limit, False
        return email_ids[-max_scan_limit:], max_scan_limit, True

    def _build_alert_result(self, mailbox_name: str, subject: str, sender: str, date: str, matched_keywords, service_name: str, amount):
        return {
            'mailbox': mailbox_name,
            'subject': subject,
            'sender': sender,
            'date': date,
            'keywords': matched_keywords,
            'service_name': service_name,
            'amount': amount,
            'alert_sent': False
        }

    def _maybe_skip_duplicate(self, result: Dict[str, Any], mailbox_name: str, sender: str, subject: str, date: str, days: int, dry_run: bool) -> bool:
        if dry_run:
            return False
        duplicate_sent = self._has_recent_email_alert(
            mailbox=mailbox_name,
            sender=sender,
            subject=subject,
            date=date,
            days=max(days, 1)
        )
        if not duplicate_sent:
            return False
        result['duplicate'] = True
        logger.info(f"邮件告警已发送过，跳过重复通知 | 邮箱: {mailbox_name} | 主题: {subject}")
        self.results.append(result)
        return True

    def _handle_scan_exception(self, mailbox_name: str, error: Exception, dry_run: bool) -> Tuple[int, int]:
        if isinstance(error, imaplib.IMAP4.error):
            logger.error(f"❌ 邮箱连接错误: {error}")
        else:
            logger.error(f"❌ 扫描失败: {error}", exc_info=True)
        if not dry_run:
            self._send_error_alert(mailbox_name, str(error))
        return 0, 0
    
    def scan_emails(self, days=1, dry_run=False):
        """
        扫描所有配置的邮箱中的告警邮件
        
        Args:
            days: 扫描最近几天的邮件（默认1天）
            dry_run: 测试模式，不发送告警
        """
        if not self.email_configs:
            logger.error("❌ 未配置邮箱信息或所有邮箱均已禁用")
            return
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📧 开始扫描 {len(self.email_configs)} 个邮箱")
        logger.info(f"   扫描范围: 最近 {days} 天")
        logger.info(f"{'='*60}\n")
        
        total_emails = 0
        total_alerts = 0

        from concurrent.futures import ThreadPoolExecutor, as_completed
        max_workers = min(len(self.email_configs), 5)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_config = {
                executor.submit(self._scan_single_mailbox, cfg, days, dry_run): cfg
                for cfg in self.email_configs
            }
            for future in as_completed(future_to_config):
                cfg = future_to_config[future]
                try:
                    emails, alerts = future.result()
                    total_emails += emails
                    total_alerts += alerts
                except Exception as e:
                    logger.error(f"❌ 扫描邮箱 {cfg.get('username', 'Unknown')} 失败: {e}", exc_info=True)
        
        # 打印总汇总
        self._print_total_summary(total_emails, total_alerts)
    
    def _scan_single_mailbox(self, email_config, days=7, dry_run=False):
        """扫描单个邮箱中的告警邮件
        
        Args:
            email_config: 邮箱配置字典
            days: 扫描最近几天的邮件
            dry_run: 测试模式，不发送告警
            
        Returns:
            tuple: (邮件总数, 告警邮件数)
        """
        host = email_config.get('host')
        port = email_config.get('port', 993)
        username = email_config.get('username')
        password = email_config.get('password')
        use_ssl = email_config.get('use_ssl', True)
        mailbox_name = email_config.get('name', username)
        
        if not self._is_valid_mailbox_config(email_config):
            logger.warning("❌ 邮箱配置不完整，跳过")
            return 0, 0
        
        logger.info(f"连接邮箱 | 服务器: {host}:{port} | 用户名: {username}")
        
        try:
            with imap_connection(host, port, username, password, use_ssl) as mail:
                email_ids = self._search_email_ids(mail, days)
                if not email_ids:
                    logger.info("ℹ️  没有需要检查的邮件")
                    return 0, 0

                raw_total = len(email_ids)
                email_ids, max_scan_limit, trimmed = self._apply_scan_limit(email_ids)
                total_emails = len(email_ids)
                if trimmed:
                    logger.warning(f"📬 邮件数量 {raw_total} 超过上限 {max_scan_limit}，仅扫描最新 {max_scan_limit} 封")

                logger.info(f"📬 找到 {total_emails} 封邮件（扫描范围: 最近{days}天）")
                
                # 分批处理邮件
                batch_size = DEFAULT_BATCH_SIZE
                alert_count = 0
                processed_count = 0

                for batch_ids in _iter_batches(email_ids, batch_size):
                    fetched_messages = self._batch_fetch_emails(mail, batch_ids)

                    for msg in fetched_messages:
                        email_uid = self._get_email_id(msg)
                        if not self._mark_seen(email_uid):
                            processed_count += 1
                            continue

                        subject, sender, date, body = self._parse_message(msg)

                        matched_keywords = self._check_alert_keywords(subject, body)

                        if not matched_keywords:
                            processed_count += 1
                            continue

                        alert_count += 1
                        service_name, amount = self._extract_service_info(subject, body)

                        amount_str = f" | 金额: {amount}" if amount else ""
                        logger.warning(
                            f"发现告警邮件 #{alert_count} | 邮箱: {mailbox_name} | 发件人: {sender} | "
                            f"主题: {subject} | 日期: {date} | 关键词: {', '.join(matched_keywords)} | "
                            f"服务: {service_name}{amount_str}"
                        )

                        result = self._build_alert_result(mailbox_name, subject, sender, date, matched_keywords, service_name, amount)
                        if self._maybe_skip_duplicate(result, mailbox_name, sender, subject, date, days, dry_run):
                            processed_count += 1
                            continue

                        if not dry_run:
                            result['alert_sent'] = self._send_alert(result)
                        else:
                            logger.info("[测试模式] 跳过发送告警")

                        self.results.append(result)

                        processed_count += 1

                    # 每批次打印进度
                    if processed_count > 0:
                        logger.info(f"扫描进度: {processed_count}/{total_emails} ({processed_count/total_emails*100:.1f}%)")
                
                # 打印单个邮箱汇总
                self._print_mailbox_summary(mailbox_name, total_emails, alert_count)
                
                # 更新 Prometheus 指标
                _record_email_scan_metrics(mailbox_name, total_emails, alert_count)
                
                return total_emails, alert_count
                
        except Exception as e:
            return self._handle_scan_exception(mailbox_name, e, dry_run)
    
    def _batch_fetch_emails(self, mail, batch_ids):
        """批量获取邮件，失败时降级为逐条获取

        Args:
            mail: IMAP 连接对象
            batch_ids: 邮件 ID 列表

        Returns:
            list: 解析后的邮件消息列表
        """
        # 尝试批量 fetch
        try:
            messages = []
            joined_ids = b','.join(batch_ids)
            status, msg_data = mail.fetch(joined_ids, '(RFC822)')
            if status == 'OK':
                for item in msg_data:
                    if isinstance(item, tuple):
                        messages.append(email.message_from_bytes(item[1]))
                return messages
        except Exception as e:
            logger.warning(f"批量 fetch 失败，降级为逐条获取: {e}")

        # 降级：逐条 fetch
        messages = []
        for email_id in batch_ids:
            try:
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                if status == 'OK':
                    messages.append(email.message_from_bytes(msg_data[0][1]))
            except Exception as e:
                logger.warning(f"获取邮件 {email_id} 失败: {e}")
        return messages

    def _send_error_alert(self, mailbox_name, error_msg):
        """发送邮箱扫描错误告警"""
        adapter = self._get_webhook_adapter(default_source='email-scanner')
        if adapter is None:
            return False

        title = "❌ 邮箱连接失败告警"
        content = f"**邮箱**: {mailbox_name}\n**错误信息**: {error_msg}\n**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return adapter.send_custom_alert(title, content)

    def _send_alert(self, email_info):
        """发送告警通知"""
        adapter = self._get_webhook_adapter(default_source='email-scanner')
        if adapter is None:
            logger.error("❌ 未配置 webhook 地址")
            return False
        
        # 构建告警消息
        title = f"📧 邮件告警: {email_info['subject']}"
        
        content_parts = [
            f"**邮箱**: {email_info.get('mailbox', '未知')}",
            f"**发件人**: {email_info['sender']}",
            f"**日期**: {email_info['date']}",
            f"**服务**: {email_info['service_name']}",
        ]
        
        if email_info['amount']:
            content_parts.append(f"**金额**: {email_info['amount']}")
        
        content_parts.append(f"**关键词**: {', '.join(email_info['keywords'])}")
        
        content = '\n'.join(content_parts)
        
        alert_sent = adapter.send_custom_alert(title, content)

        # 保存到数据库
        try:
            from database.repository import EmailRepository
            EmailRepository.save_email_alert(
                mailbox=email_info.get('mailbox', '未知'),
                sender=email_info['sender'],
                subject=email_info['subject'],
                date=email_info['date'],
                service_name=email_info['service_name'],
                amount=email_info['amount'],
                matched_keywords=email_info['keywords'],
                alert_sent=alert_sent
            )
        except Exception as e:
            logger.error(f"保存邮件告警记录失败: {e}", exc_info=True)

        return alert_sent
    
    def _print_mailbox_summary(self, mailbox_name, total_emails, alert_count):
        """打印单个邮箱扫描汇总"""
        logger.info(f"[{mailbox_name}] 扫描汇总: 总邮件={total_emails}, 告警邮件={alert_count}")
    
    def _print_total_summary(self, total_emails, total_alerts):
        """打印所有邮箱的总汇总"""
        alerts_sent = sum(1 for r in self.results if r.get('alert_sent', False))
        logger.info(
            f"邮箱扫描总汇总: 邮箱数={len(self.email_configs)}, 总邮件={total_emails}, "
            f"告警邮件={total_alerts}, 已发送告警={alerts_sent}"
        )


def main():
    """主函数"""
    import argparse
    from core.config_loader import get_default_config_path
    
    parser = argparse.ArgumentParser(description='邮箱告警扫描器')
    parser.add_argument('--days', type=int, default=1, help='扫描最近几天的邮件（默认1天）')
    parser.add_argument('--dry-run', action='store_true', help='测试模式，不发送告警')
    default_config = get_default_config_path()
    parser.add_argument('--config', default=default_config, help=f'配置文件路径 (默认: {default_config})')
    
    args = parser.parse_args()
    
    try:
        scanner = EmailScanner(args.config)
        scanner.scan_emails(days=args.days, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
