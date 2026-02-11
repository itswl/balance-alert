#!/usr/bin/env python3
"""
邮箱扫描器 - 检测欠费、续费等提醒邮件
"""
import imaplib
import email
from email.header import decode_header
import re
from datetime import datetime, timedelta
import json
from webhook_adapter import WebhookAdapter
from prometheus_exporter import metrics_collector
from logger import get_logger

# 创建 logger
logger = get_logger('email_scanner')


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
        
        # 关键词匹配规则
        self.alert_keywords = [
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
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ 配置文件不存在: {self.config_path}")
            return {}
        except json.JSONDecodeError as e:
            print(f"❌ 配置文件格式错误: {e}")
            return {}
    
    def _parse_email_configs(self):
        """解析邮箱配置，支持单个或多个邮箱"""
        email_config = self.config.get('email', {})
        
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
        """检查是否包含告警关键词（不区分大小写）"""
        full_text = f"{subject}\n{body}".lower()  # 转换为小写进行匹配
        matched_keywords = []
        
        for keyword in self.alert_keywords:
            if keyword.lower() in full_text:
                matched_keywords.append(keyword)
        
        return matched_keywords
    
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
            r'([0-9,]+\.?[0-9]*)\s*元',
            r'¥\s*([0-9,]+\.?[0-9]*)',
            r'CNY\s*([0-9,]+\.?[0-9]*)',
            r'\$\s*([0-9,]+\.?[0-9]*)',
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
    
    def scan_emails(self, days=1, dry_run=False):
        """
        扫描所有配置的邮箱中的告警邮件
        
        Args:
            days: 扫描最近几天的邮件（默认1天）
            dry_run: 测试模式，不发送告警
        """
        if not self.email_configs:
            print("❌ 未配置邮箱信息或所有邮箱均已禁用")
            return
        
        print(f"\n{'='*60}")
        print(f"📧 开始扫描 {len(self.email_configs)} 个邮箱")
        print(f"   扫描范围: 最近 {days} 天")
        print(f"{'='*60}\n")
        
        # 扫描每个邮箱
        total_emails = 0
        total_alerts = 0
        
        for i, email_config in enumerate(self.email_configs, 1):
            print(f"\n{'='*60}")
            print(f"📬 邮箱 [{i}/{len(self.email_configs)}]: {email_config.get('username', 'Unknown')}")
            print(f"{'='*60}")
            
            emails, alerts = self._scan_single_mailbox(email_config, days, dry_run)
            total_emails += emails
            total_alerts += alerts
        
        # 打印总汇总
        self._print_total_summary(total_emails, total_alerts)
    
    def _scan_single_mailbox(self, email_config, days=1, dry_run=False):
        """
        扫描单个邮箱中的告警邮件
        
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
        
        if not all([host, username, password]):
            print("❌ 邮箱配置不完整，跳过")
            return 0, 0
        
        print(f"   服务器: {host}:{port}")
        print(f"   用户名: {username}")
        
        mail = None
        try:
            # 连接邮箱
            if use_ssl:
                mail = imaplib.IMAP4_SSL(host, port)
            else:
                mail = imaplib.IMAP4(host, port)
            
            mail.login(username, password)
            print("✅ 邮箱登录成功")
            
            # 选择收件箱
            mail.select('INBOX')
            
            # 计算日期范围
            since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
            
            # 搜索邮件
            status, messages = mail.search(None, f'SINCE {since_date}')
            
            if status != 'OK':
                print("❌ 搜索邮件失败")
                return 0, 0
            
            email_ids = messages[0].split()
            total_emails = len(email_ids)
            
            print(f"📬 找到 {total_emails} 封邮件\n")
            
            if total_emails == 0:
                print("ℹ️  没有需要检查的邮件")
                return 0, 0
            
            # 分批处理邮件，每批最多100封
            batch_size = 100
            alert_count = 0
            processed_count = 0
            
            for i, email_id in enumerate(email_ids):
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                
                if status != 'OK':
                    continue
                
                # 解析邮件
                msg = email.message_from_bytes(msg_data[0][1])
                
                # 获取邮件信息
                subject = self._decode_str(msg.get('Subject', ''))
                sender = self._decode_str(msg.get('From', ''))
                date = self._decode_str(msg.get('Date', ''))
                
                # 提取邮件正文
                body = self._extract_text_from_email(msg)
                
                # 检查是否包含告警关键词
                matched_keywords = self._check_alert_keywords(subject, body)
                
                if matched_keywords:
                    alert_count += 1
                    print(f"{'='*60}")
                    print(f"⚠️  发现告警邮件 #{alert_count}")
                    print(f"   邮箱: {mailbox_name}")
                    print(f"   发件人: {sender}")
                    print(f"   主题: {subject}")
                    print(f"   日期: {date}")
                    print(f"   匹配关键词: {', '.join(matched_keywords)}")
                    
                    # 尝试提取服务信息
                    service_name, amount = self._extract_service_info(subject, body)
                    print(f"   服务: {service_name}")
                    if amount:
                        print(f"   金额: ¥{amount}")
                    
                    print(f"{'='*60}\n")
                    
                    # 记录结果
                    result = {
                        'mailbox': mailbox_name,
                        'subject': subject,
                        'sender': sender,
                        'date': date,
                        'keywords': matched_keywords,
                        'service_name': service_name,
                        'amount': amount,
                        'alert_sent': False
                    }
                    
                    # 发送告警
                    if not dry_run:
                        alert_sent = self._send_alert(result)
                        result['alert_sent'] = alert_sent
                    else:
                        print("🔍 [测试模式] 跳过发送告警")
                    
                    self.results.append(result)
                
                processed_count += 1
                
                # 每处理100封邮件，打印进度
                if processed_count % batch_size == 0:
                    print(f"   进度: {processed_count}/{total_emails} ({processed_count/total_emails*100:.1f}%)")
            
            # 打印单个邮箱汇总
            self._print_mailbox_summary(mailbox_name, total_emails, alert_count)
            
            # 更新 Prometheus 指标
            metrics_collector.record_email_scan(mailbox_name, total_emails, alert_count)
            
            return total_emails, alert_count
            
        except imaplib.IMAP4.error as e:
            logger.error(f"❌ 邮箱连接错误: {e}")
            return 0, 0
        except Exception as e:
            logger.error(f"❌ 扫描失败: {e}", exc_info=True)
            return 0, 0
        finally:
            # 确保连接关闭
            if mail:
                try:
                    mail.logout()
                    print(f"   已断开邮箱连接")
                except Exception:
                    pass
    
    def _send_alert(self, email_info):
        """发送告警通知"""
        webhook_config = self.config.get('webhook', {})
        webhook_url = webhook_config.get('url')
        webhook_type = webhook_config.get('type', 'custom')
        webhook_source = webhook_config.get('source', 'email-scanner')
        
        if not webhook_url:
            print("❌ 未配置 webhook 地址")
            return False
        
        adapter = WebhookAdapter(webhook_url, webhook_type, webhook_source)
        
        # 构建告警消息
        title = f"📧 邮件告警: {email_info['subject']}"
        
        content_parts = [
            f"**邮箱**: {email_info.get('mailbox', '未知')}",
            f"**发件人**: {email_info['sender']}",
            f"**日期**: {email_info['date']}",
            f"**服务**: {email_info['service_name']}",
        ]
        
        if email_info['amount']:
            content_parts.append(f"**金额**: ¥{email_info['amount']}")
        
        content_parts.append(f"**关键词**: {', '.join(email_info['keywords'])}")
        
        content = '\n'.join(content_parts)
        
        return adapter.send_custom_alert(title, content)
    
    def _print_mailbox_summary(self, mailbox_name, total_emails, alert_count):
        """打印单个邮箱扫描汇总"""
        print(f"\n{'='*60}")
        print(f"📊 [{mailbox_name}] 扫描汇总")
        print(f"{'='*60}")
        print(f"总邮件数: {total_emails}")
        print(f"告警邮件数: {alert_count}")
        print(f"{'='*60}\n")
    
    def _print_total_summary(self, total_emails, total_alerts):
        """打印所有邮箱的总汇总"""
        print(f"\n{'='*60}")
        print("📊 总汇总")
        print(f"{'='*60}")
        print(f"扫描邮箱数: {len(self.email_configs)}")
        print(f"总邮件数: {total_emails}")
        print(f"总告警邮件数: {total_alerts}")
        print(f"已发送告警: {sum(1 for r in self.results if r.get('alert_sent', False))}")
        print(f"{'='*60}\n")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='邮箱告警扫描器')
    parser.add_argument('--days', type=int, default=1, help='扫描最近几天的邮件（默认1天）')
    parser.add_argument('--dry-run', action='store_true', help='测试模式，不发送告警')
    parser.add_argument('--config', default='config.json', help='配置文件路径')
    
    args = parser.parse_args()
    
    try:
        scanner = EmailScanner(args.config)
        scanner.scan_emails(days=args.days, dry_run=args.dry_run)
    except Exception as e:
        print(f"❌ 错误: {e}")
        exit(1)


if __name__ == '__main__':
    main()
