#!/usr/bin/env python3
"""
Webhook 适配器
支持多种 webhook 类型：飞书、自定义等
"""
import json
import os
import time
import requests
import requests.adapters
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from core.logger import get_logger

# 创建 logger
logger = get_logger('webhook_adapter')

# HTTP 连接默认常量
DEFAULT_POOL_CONNECTIONS = 10
DEFAULT_POOL_MAXSIZE = 100
DEFAULT_MAX_RETRIES = 3

# 从环境变量读取超时时间，默认 10 秒
REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', '10'))


def _mask_webhook_url(url: str) -> str:
    """Mask webhook secrets before writing URLs to logs."""
    if not url:
        return ''

    for marker in ('hook/', 'access_token=', 'key='):
        if marker in url:
            prefix, _, secret = url.partition(marker)
            return f"{prefix}{marker}{secret[:4]}***" if secret else f"{prefix}{marker}***"

    if len(url) <= 16:
        return '***'
    return f"{url[:12]}***{url[-4:]}"


class WebhookAdapter:
    """Webhook 发送适配器"""

    SUPPORTED_TYPES = ['feishu', 'custom', 'dingtalk', 'wecom']

    def __init__(self, webhook_url, webhook_type='custom', source='credit-monitor'):
        """
        初始化 Webhook 适配器

        Args:
            webhook_url: Webhook URL
            webhook_type: Webhook 类型 (feishu/custom/dingtalk/wecom)
            source: 消息来源标识
        """
        self.webhook_url = webhook_url
        self.webhook_type = webhook_type.lower()
        self.source = source
        self._session = None

        if self.webhook_type not in self.SUPPORTED_TYPES:
            logger.warning(f"⚠️  未知的 webhook 类型: {webhook_type}，使用默认类型 'custom'")
            self.webhook_type = 'custom'

    def _get_session(self):
        """获取或创建复用的 HTTP Session"""
        if self._session is None:
            self._session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=DEFAULT_POOL_CONNECTIONS,
                pool_maxsize=DEFAULT_POOL_MAXSIZE,
                max_retries=DEFAULT_MAX_RETRIES
            )
            self._session.mount('http://', adapter)
            self._session.mount('https://', adapter)
        return self._session

    def close(self):
        """关闭 HTTP Session"""
        if self._session:
            self._session.close()
            self._session = None
    
    @staticmethod
    def _payload_preview(payload: Any, limit: int = 500) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False)[:limit]
        except Exception:
            return str(payload)[:limit]

    @staticmethod
    def _format_days_text(days: int) -> str:
        """格式化天数文本"""
        return {0: "今天", 1: "明天"}.get(days, f"{days} 天后")

    @staticmethod
    def _format_dingtalk_markdown(text: str) -> str:
        lines = []
        for line in text.split('\n'):
            if ': ' in line:
                key, value = line.split(': ', 1)
                lines.append(f"- **{key}**: {value}")
            else:
                lines.append(f"- {line}")
        return "\n".join(lines)

    @staticmethod
    def _format_subscription_cycle(cycle_type: str, renewal_day: int) -> str:
        """格式化订阅续费周期，年付支持 MMDD 表达。"""
        try:
            renewal_day = int(renewal_day)
        except (TypeError, ValueError):
            return "未知周期"

        if cycle_type == 'weekly':
            weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            if 1 <= renewal_day <= 7:
                return f"每周 {weekdays[renewal_day - 1]}"
            return f"每周第 {renewal_day} 天"

        if cycle_type == 'yearly':
            if renewal_day > 31:
                month = renewal_day // 100
                day = renewal_day % 100
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return f"每年 {month}月{day}日"
            return "每年固定日期"

        return f"每月 {renewal_day} 号"

    def _build_balance_text(self, project_name: str, provider: str, balance_type: str,
                            current_value: float, threshold: float, unit: str,
                            owner_project: str = None) -> str:
        """生成余额告警通用文本"""
        owner_text = f"所属项目: {owner_project}\n" if owner_project else ""
        return (
            f"API 调用: {project_name}\n"
            f"{owner_text}"
            f"服务商: {provider}\n"
            f"当前{balance_type}: {unit}{current_value:,.2f}\n"
            f"告警阈值: {unit}{threshold:,.2f}\n"
            f"状态: ⚠️ {balance_type}不足"
        )

    def _build_subscription_text(self, subscription_name: str, renewal_day: int,
                                 days_until_renewal: int, amount: float,
                                 owner_project: str = None,
                                 cycle_type: str = 'monthly') -> str:
        """生成订阅提醒通用文本"""
        days_text = self._format_days_text(days_until_renewal)
        project_text = f"所属项目: {owner_project}\n" if owner_project else ""
        cycle_text = self._format_subscription_cycle(cycle_type, renewal_day)
        return (
            f"订阅: {subscription_name}\n"
            f"{project_text}"
            f"续费周期: {cycle_text}\n"
            f"距离续费: {days_text}\n"
            f"续费金额: {amount}"
        )

    def _wrap_payload(self, title: str, text: str) -> Dict[str, Any]:
        """按平台包装消息 payload"""
        if self.webhook_type == 'feishu':
            return {
                "msg_type": "text",
                "content": {"text": f"【{title}】\n\n{text}\n来源: {self.source}"}
            }
        if self.webhook_type == 'dingtalk':
            md_text = self._format_dingtalk_markdown(text)
            return {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": f"## {title}\n\n{md_text}"}
            }
        return {
            "msgtype": "text",
            "text": {"content": f"【{title}】\n{text}"}
        }

    def send_balance_alert(self, project_name: str, provider: str, balance_type: str, current_value: float,
                          threshold: float, unit: str = '', owner_project: str = None) -> bool:
        """
        发送余额告警

        Args:
            project_name: 项目名称
            owner_project: 所属项目名称
            provider: 服务商
            balance_type: 类型 (余额)
            current_value: 当前值
            threshold: 阈值
            unit: 单位

        Returns:
            bool: 是否发送成功
        """
        if self.webhook_type == 'custom':
            return self._send_custom_balance_alert(
                project_name, provider, balance_type, current_value, threshold, unit, owner_project
            )
        text = self._build_balance_text(project_name, provider, balance_type, current_value, threshold, unit, owner_project)
        payload = self._wrap_payload("余额告警", text)
        return self._send_request(payload)
    
    def send_subscription_alert(self, subscription_name: str, renewal_day: int, days_until_renewal: int,
                               amount: float, owner_project: str = None,
                               cycle_type: str = 'monthly') -> bool:
        """
        发送订阅续费提醒

        Args:
            subscription_name: 订阅名称
            owner_project: 所属项目名称
            renewal_day: 续费日期
            days_until_renewal: 距离续费天数
            amount: 续费金额

        Returns:
            bool: 是否发送成功
        """
        if self.webhook_type == 'custom':
            return self._send_custom_subscription_alert(
                subscription_name, renewal_day, days_until_renewal, amount, owner_project, cycle_type
            )
        text = self._build_subscription_text(
                subscription_name, renewal_day, days_until_renewal, amount, owner_project, cycle_type
            )
        payload = self._wrap_payload("订阅续费提醒", text)
        return self._send_request(payload)
    
    # ==================== 自定义格式 ====================
    
    def _send_custom_balance_alert(self, project_name, provider, balance_type,
                                   current_value, threshold, unit, owner_project=None):
        """发送自定义格式余额告警"""
        payload = {
            "Type": "AlarmNotification",
            "RuleName": f"{project_name}{balance_type}告警",
            "Level": "critical",
            "Resources": [{
                "ProjectName": project_name,
                "OwnerProject": owner_project,
                "Provider": provider,
                "BalanceType": balance_type,
                "CurrentValue": current_value,
                "Threshold": threshold,
                "Unit": unit,
                "Message": f"项目 [{project_name}] {balance_type}不足，当前: {unit}{current_value:,.2f}，阈值: {unit}{threshold:,.2f}"
            }]
        }
        
        return self._send_request(payload)
    
    def _send_custom_subscription_alert(self, subscription_name, renewal_day,
                                       days_until_renewal, amount, owner_project=None,
                                       cycle_type='monthly'):
        """发送自定义格式订阅提醒"""
        cycle_text = self._format_subscription_cycle(cycle_type, renewal_day)
        payload = {
            "Type": "SubscriptionReminder",
            "RuleName": f"{subscription_name}续费提醒",
            "Level": "warning" if days_until_renewal > 0 else "critical",
            "Resources": [{
                "SubscriptionName": subscription_name,
                "OwnerProject": owner_project,
                "RenewalDay": renewal_day,
                "CycleType": cycle_type,
                "DaysUntilRenewal": days_until_renewal,
                "Amount": amount,
                "Message": f"订阅 [{subscription_name}] 将在 {days_until_renewal} 天后（{cycle_text}）续费，金额: {amount}"
            }]
        }
        
        return self._send_request(payload)
    
    # ==================== 通用发送 ====================
    
    def _send_request(self, payload):
        """
        发送 HTTP 请求（带自动重试）

        Args:
            payload: 请求体

        Returns:
            bool: 是否发送成功
        """
        logger.info(f"准备发送 Webhook | URL: {_mask_webhook_url(self.webhook_url)} | 类型: {self.webhook_type}")
        logger.debug(f"请求体: {self._payload_preview(payload)}")

        try:
            return self._send_request_with_retry(payload)
        except requests.exceptions.Timeout as e:
            logger.error(f"请求超时（重试耗尽）: {e}")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"连接错误（重试耗尽）: {e} | 请检查网络连接、Webhook URL 和防火墙设置")
            return False
        except Exception as e:
            logger.error(f"发送失败: {type(e).__name__}: {e}", exc_info=True)
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
        reraise=True
    )
    def _send_request_with_retry(self, payload):
        """发送 HTTP 请求的内层方法（可重试）"""
        start_time = time.time()

        session = self._get_session()
        response = session.post(
            self.webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT
        )

        elapsed_time = time.time() - start_time
        logger.debug(f"响应状态码: {response.status_code} | 耗时: {elapsed_time:.2f}s")

        if 200 <= response.status_code < 300:
            logger.info(f"告警发送成功 | 类型: {self.webhook_type} | 状态码: {response.status_code} | 耗时: {elapsed_time:.2f}s")
            return True
        elif 500 <= response.status_code < 600:
            # 5xx 服务端错误，抛出异常以触发重试
            logger.warning(f"服务端错误 HTTP {response.status_code}，将重试")
            raise requests.exceptions.ConnectionError(
                f"Server error: HTTP {response.status_code}"
            )
        else:
            # 4xx 等客户端错误，不重试
            logger.error(f"告警发送失败: HTTP {response.status_code} | 响应: {response.text[:500]}")
            return False
    
    def send_custom_alert(self, title, content):
        """
        发送自定义告警
        
        Args:
            title: 告警标题
            content: 告警内容
            
        Returns:
            bool: 是否发送成功
        """
        try:
            handlers = {
                'feishu': self._send_feishu_custom,
                'dingtalk': self._send_dingtalk_custom,
                'wecom': self._send_wecom_custom,
            }
            handler = handlers.get(self.webhook_type, self._send_custom_webhook_custom)
            return handler(title, content)
        except Exception as e:
            logger.error(f"发送自定义告警失败: {e}", exc_info=True)
            return False
    
    def _send_feishu_custom(self, title, content):
        """发送飞书自定义告警"""
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": "orange"
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content
                    }
                ]
            }
        }
        return self._send_request(payload)

    def _send_dingtalk_custom(self, title, content):
        """发送钉钉自定义告警"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"### {title}\n\n{content}"
            }
        }
        return self._send_request(payload)

    def _send_wecom_custom(self, title, content):
        """发送企业微信自定义告警"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"### {title}\n\n{content}"
            }
        }
        return self._send_request(payload)

    def _send_custom_webhook_custom(self, title, content):
        """发送自定义 Webhook 告警"""
        payload = {
            "title": title,
            "content": content,
            "source": self.source,
            "timestamp": datetime.now().isoformat()
        }
        return self._send_request(payload)
