#!/usr/bin/env python3
"""
Webhook 适配器
支持多种 webhook 类型：飞书、自定义等
"""
import json
import requests


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
        
        if self.webhook_type not in self.SUPPORTED_TYPES:
            print(f"⚠️  未知的 webhook 类型: {webhook_type}，使用默认类型 'custom'")
            self.webhook_type = 'custom'
    
    def send_balance_alert(self, project_name, provider, balance_type, current_value, 
                          threshold, unit=''):
        """
        发送余额/积分告警
        
        Args:
            project_name: 项目名称
            provider: 服务商
            balance_type: 类型 (余额/积分)
            current_value: 当前值
            threshold: 阈值
            unit: 单位
        
        Returns:
            bool: 是否发送成功
        """
        if self.webhook_type == 'feishu':
            return self._send_feishu_balance_alert(
                project_name, provider, balance_type, current_value, threshold, unit
            )
        elif self.webhook_type == 'dingtalk':
            return self._send_dingtalk_balance_alert(
                project_name, provider, balance_type, current_value, threshold, unit
            )
        elif self.webhook_type == 'wecom':
            return self._send_wecom_balance_alert(
                project_name, provider, balance_type, current_value, threshold, unit
            )
        else:
            return self._send_custom_balance_alert(
                project_name, provider, balance_type, current_value, threshold, unit
            )
    
    def send_subscription_alert(self, subscription_name, renewal_day, days_until_renewal,
                               amount, currency):
        """
        发送订阅续费提醒
        
        Args:
            subscription_name: 订阅名称
            renewal_day: 续费日期
            days_until_renewal: 距离续费天数
            amount: 金额
            currency: 货币
        
        Returns:
            bool: 是否发送成功
        """
        if self.webhook_type == 'feishu':
            return self._send_feishu_subscription_alert(
                subscription_name, renewal_day, days_until_renewal, amount, currency
            )
        elif self.webhook_type == 'dingtalk':
            return self._send_dingtalk_subscription_alert(
                subscription_name, renewal_day, days_until_renewal, amount, currency
            )
        elif self.webhook_type == 'wecom':
            return self._send_wecom_subscription_alert(
                subscription_name, renewal_day, days_until_renewal, amount, currency
            )
        else:
            return self._send_custom_subscription_alert(
                subscription_name, renewal_day, days_until_renewal, amount, currency
            )
    
    # ==================== 飞书 ====================
    
    def _send_feishu_balance_alert(self, project_name, provider, balance_type, 
                                   current_value, threshold, unit):
        """发送飞书余额告警"""
        text = f"【余额告警】\n\n" \
               f"项目: {project_name}\n" \
               f"服务商: {provider}\n" \
               f"当前{balance_type}: {unit}{current_value:,.2f}\n" \
               f"告警阈值: {unit}{threshold:,.2f}\n" \
               f"状态: ⚠️ {balance_type}不足\n" \
               f"来源: {self.source}"
        
        payload = {
            "msg_type": "text",
            "content": {
                "text": text
            }
        }
        
        return self._send_request(payload)
    
    def _send_feishu_subscription_alert(self, subscription_name, renewal_day, 
                                       days_until_renewal, amount, currency):
        """发送飞书订阅提醒"""
        days_text = "今天" if days_until_renewal == 0 else \
                   "明天" if days_until_renewal == 1 else \
                   f"{days_until_renewal} 天后"
        
        text = f"【订阅续费提醒】\n\n" \
               f"订阅: {subscription_name}\n" \
               f"续费日期: 每月 {renewal_day} 号\n" \
               f"距离续费: {days_text}\n" \
               f"续费金额: {currency} {amount}\n" \
               f"来源: {self.source}"
        
        payload = {
            "msg_type": "text",
            "content": {
                "text": text
            }
        }
        
        return self._send_request(payload)
    
    # ==================== 钉钉 ====================
    
    def _send_dingtalk_balance_alert(self, project_name, provider, balance_type,
                                     current_value, threshold, unit):
        """发送钉钉余额告警"""
        text = f"## 余额告警\n\n" \
               f"- **项目**: {project_name}\n" \
               f"- **服务商**: {provider}\n" \
               f"- **当前{balance_type}**: {unit}{current_value:,.2f}\n" \
               f"- **告警阈值**: {unit}{threshold:,.2f}\n" \
               f"- **状态**: ⚠️ {balance_type}不足"
        
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "余额告警",
                "text": text
            }
        }
        
        return self._send_request(payload)
    
    def _send_dingtalk_subscription_alert(self, subscription_name, renewal_day,
                                         days_until_renewal, amount, currency):
        """发送钉钉订阅提醒"""
        days_text = "今天" if days_until_renewal == 0 else \
                   "明天" if days_until_renewal == 1 else \
                   f"{days_until_renewal} 天后"
        
        text = f"## 订阅续费提醒\n\n" \
               f"- **订阅**: {subscription_name}\n" \
               f"- **续费日期**: 每月 {renewal_day} 号\n" \
               f"- **距离续费**: {days_text}\n" \
               f"- **续费金额**: {currency} {amount}"
        
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "订阅续费提醒",
                "text": text
            }
        }
        
        return self._send_request(payload)
    
    # ==================== 企业微信 ====================
    
    def _send_wecom_balance_alert(self, project_name, provider, balance_type,
                                  current_value, threshold, unit):
        """发送企业微信余额告警"""
        text = f"【余额告警】\n" \
               f"项目: {project_name}\n" \
               f"服务商: {provider}\n" \
               f"当前{balance_type}: {unit}{current_value:,.2f}\n" \
               f"告警阈值: {unit}{threshold:,.2f}\n" \
               f"状态: ⚠️ {balance_type}不足"
        
        payload = {
            "msgtype": "text",
            "text": {
                "content": text
            }
        }
        
        return self._send_request(payload)
    
    def _send_wecom_subscription_alert(self, subscription_name, renewal_day,
                                      days_until_renewal, amount, currency):
        """发送企业微信订阅提醒"""
        days_text = "今天" if days_until_renewal == 0 else \
                   "明天" if days_until_renewal == 1 else \
                   f"{days_until_renewal} 天后"
        
        text = f"【订阅续费提醒】\n" \
               f"订阅: {subscription_name}\n" \
               f"续费日期: 每月 {renewal_day} 号\n" \
               f"距离续费: {days_text}\n" \
               f"续费金额: {currency} {amount}"
        
        payload = {
            "msgtype": "text",
            "text": {
                "content": text
            }
        }
        
        return self._send_request(payload)
    
    # ==================== 自定义格式 ====================
    
    def _send_custom_balance_alert(self, project_name, provider, balance_type,
                                   current_value, threshold, unit):
        """发送自定义格式余额告警"""
        payload = {
            "Type": "AlarmNotification",
            "RuleName": f"{project_name}{balance_type}告警",
            "Level": "critical",
            "Resources": [{
                "ProjectName": project_name,
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
                                       days_until_renewal, amount, currency):
        """发送自定义格式订阅提醒"""
        payload = {
            "Type": "SubscriptionReminder",
            "RuleName": f"{subscription_name}续费提醒",
            "Level": "warning" if days_until_renewal > 0 else "critical",
            "Resources": [{
                "SubscriptionName": subscription_name,
                "RenewalDay": renewal_day,
                "DaysUntilRenewal": days_until_renewal,
                "Amount": amount,
                "Currency": currency,
                "Message": f"订阅 [{subscription_name}] 将在 {days_until_renewal} 天后（每月{renewal_day}号）续费，金额: {currency} {amount}"
            }]
        }
        
        return self._send_request(payload)
    
    # ==================== 通用发送 ====================
    
    def _send_request(self, payload):
        """
        发送 HTTP 请求
        
        Args:
            payload: 请求体
        
        Returns:
            bool: 是否发送成功
        """
        print(f"\n{'='*60}")
        print(f"📤 准备发送 Webhook")
        print(f"{'='*60}")
        print(f"🎯 目标 URL: {self.webhook_url}")
        print(f"🔖 Webhook 类型: {self.webhook_type}")
        print(f"📝 请求体:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"{'='*60}")
        
        try:
            import time
            start_time = time.time()
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            elapsed_time = time.time() - start_time
            
            print(f"\n📥 响应信息:")
            print(f"   状态码: {response.status_code}")
            print(f"   耗时: {elapsed_time:.2f} 秒")
            print(f"   响应头:")
            for key, value in response.headers.items():
                if key.lower() in ['content-type', 'content-length', 'date', 'server']:
                    print(f"      {key}: {value}")
            
            print(f"\n   响应内容:")
            try:
                response_json = response.json()
                print(json.dumps(response_json, ensure_ascii=False, indent=2))
            except:
                response_text = response.text[:500]  # 只显示前500字符
                print(f"      {response_text}")
                if len(response.text) > 500:
                    print(f"      ... (共 {len(response.text)} 字符)")
            
            if response.status_code == 200:
                print(f"\n✅ 告警发送成功 ({self.webhook_type})")
                print(f"{'='*60}\n")
                return True
            else:
                print(f"\n❌ 告警发送失败: HTTP {response.status_code}")
                print(f"{'='*60}\n")
                return False
                
        except requests.exceptions.Timeout as e:
            print(f"\n❌ 请求超时: {e}")
            print(f"{'='*60}\n")
            return False
        except requests.exceptions.ConnectionError as e:
            print(f"\n❌ 连接错误: {e}")
            print(f"   请检查:")
            print(f"   1. 网络连接是否正常")
            print(f"   2. Webhook URL 是否正确")
            print(f"   3. 防火墙设置是否允许访问")
            print(f"{'='*60}\n")
            return False
        except Exception as e:
            print(f"\n❌ 发送失败: {type(e).__name__}: {e}")
            import traceback
            print(f"\n详细错误信息:")
            print(traceback.format_exc())
            print(f"{'='*60}\n")
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
            if self.webhook_type == 'feishu':
                return self._send_feishu_custom(title, content)
            elif self.webhook_type == 'dingtalk':
                return self._send_dingtalk_custom(title, content)
            elif self.webhook_type == 'wecom':
                return self._send_wecom_custom(title, content)
            else:
                return self._send_custom_webhook_custom(title, content)
        except Exception as e:
            print(f"❌ 发送自定义告警失败: {e}")
            return False
    
    def _send_feishu_custom(self, title, content):
        """发送飞书自定义告警"""
        data = {
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
        
        response = requests.post(
            self.webhook_url,
            json=data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ 飞书告警发送成功")
            return True
        else:
            print(f"❌ 飞书告警发送失败: {response.text}")
            return False
    
    def _send_dingtalk_custom(self, title, content):
        """发送钉钉自定义告警"""
        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"### {title}\n\n{content}"
            }
        }
        
        response = requests.post(
            self.webhook_url,
            json=data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ 钉钉告警发送成功")
            return True
        else:
            print(f"❌ 钉钉告警发送失败: {response.text}")
            return False
    
    def _send_wecom_custom(self, title, content):
        """发送企业微信自定义告警"""
        data = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"### {title}\n\n{content}"
            }
        }
        
        response = requests.post(
            self.webhook_url,
            json=data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ 企业微信告警发送成功")
            return True
        else:
            print(f"❌ 企业微信告警发送失败: {response.text}")
            return False
    
    def _send_custom_webhook_custom(self, title, content):
        """发送自定义 Webhook 告警"""
        data = {
            "title": title,
            "content": content,
            "source": self.source,
            "timestamp": datetime.now().isoformat()
        }
        
        response = requests.post(
            self.webhook_url,
            json=data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ 自定义告警发送成功")
            return True
        else:
            print(f"❌ 自定义告警发送失败: {response.text}")
            return False
