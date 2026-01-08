#!/usr/bin/env python3
"""
订阅续费提醒检查器
"""
import json
from datetime import datetime, timedelta
from webhook_adapter import WebhookAdapter


class SubscriptionChecker:
    """订阅续费检查器"""
    
    def __init__(self, config_path='config.json'):
        """初始化"""
        self.config_path = config_path
        self.config = self._load_config()
        self.results = []
    
    def _load_config(self):
        """加载配置文件"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def check_subscriptions(self, dry_run=False):
        """
        检查所有订阅
        
        Args:
            dry_run: 测试模式，不发送告警
        """
        subscriptions = self.config.get('subscriptions', [])
        
        if not subscriptions:
            print("📋 没有配置订阅项目")
            return
        
        # 过滤启用的订阅
        enabled_subs = [s for s in subscriptions if s.get('enabled', True)]
        
        print(f"\n📅 开始检查 {len(enabled_subs)} 个订阅...")
        if dry_run:
            print("🔍 [测试模式] 不会发送实际告警\n")
        
        today = datetime.now()
        current_day = today.day
        
        for sub in enabled_subs:
            result = self._check_subscription(sub, today, current_day, dry_run)
            self.results.append(result)
        
        self._print_summary()
    
    def _check_subscription(self, sub, today, current_day, dry_run):
        """检查单个订阅"""
        name = sub.get('name', '未知订阅')
        renewal_day = sub.get('renewal_day', 1)
        alert_days_before = sub.get('alert_days_before', 3)
        amount = sub.get('amount', 0)
        currency = sub.get('currency', 'CNY')
        
        print(f"{'='*60}")
        print(f"📦 订阅: {name}")
        print(f"   续费日: 每月 {renewal_day} 号")
        print(f"   金额: {currency} {amount}")
        print(f"{'='*60}")
        
        # 计算距离续费日的天数
        days_until_renewal = self._calculate_days_until_renewal(
            current_day, renewal_day, today
        )
        
        print(f"📍 距离续费还有: {days_until_renewal} 天")
        
        # 判断是否需要告警
        need_alert = days_until_renewal <= alert_days_before and days_until_renewal >= 0
        alert_sent = False
        
        if need_alert:
            print(f"⚠️  需要提醒续费! (提前 {alert_days_before} 天)")
            
            if not dry_run:
                alert_sent = self._send_alert(sub, days_until_renewal)
            else:
                print("🔍 [测试模式] 跳过发送告警")
        else:
            print(f"✅ 无需提醒")
        
        return {
            'name': name,
            'renewal_day': renewal_day,
            'days_until_renewal': days_until_renewal,
            'need_alert': need_alert,
            'alert_sent': alert_sent,
            'amount': amount,
            'currency': currency
        }
    
    def _calculate_days_until_renewal(self, current_day, renewal_day, today):
        """计算距离续费日的天数"""
        if current_day <= renewal_day:
            # 本月还没到续费日
            renewal_date = datetime(today.year, today.month, renewal_day)
        else:
            # 已经过了本月续费日，计算下个月
            if today.month == 12:
                renewal_date = datetime(today.year + 1, 1, renewal_day)
            else:
                renewal_date = datetime(today.year, today.month + 1, renewal_day)
        
        delta = renewal_date - today
        return delta.days
    
    def _send_alert(self, sub, days_until_renewal):
        """发送续费提醒告警"""
        webhook_config = self.config.get('webhook', {})
        webhook_url = webhook_config.get('url')
        webhook_type = webhook_config.get('type', 'custom')
        webhook_source = webhook_config.get('source', 'credit-monitor')
        
        if not webhook_url:
            print("❌ 未配置 webhook 地址")
            return False
        
        # 创建 webhook 适配器
        adapter = WebhookAdapter(webhook_url, webhook_type, webhook_source)
        
        # 获取订阅信息
        name = sub.get('name')
        renewal_day = sub.get('renewal_day')
        amount = sub.get('amount')
        currency = sub.get('currency', 'CNY')
        
        # 发送提醒
        return adapter.send_subscription_alert(
            subscription_name=name,
            renewal_day=renewal_day,
            days_until_renewal=days_until_renewal,
            amount=amount,
            currency=currency
        )
    
    def _print_summary(self):
        """打印检查汇总"""
        print(f"\n\n{'='*60}")
        print("📊 订阅检查汇总")
        print(f"{'='*60}")
        
        total = len(self.results)
        need_alert = sum(1 for r in self.results if r.get('need_alert', False))
        alert_sent = sum(1 for r in self.results if r.get('alert_sent', False))
        
        print(f"总订阅数: {total}")
        print(f"需要提醒: {need_alert}")
        print(f"已发送提醒: {alert_sent}")
        
        if self.results:
            print(f"\n详细结果:")
            for r in self.results:
                status = "⚠️需提醒" if r.get('need_alert') else "✅正常"
                days = r['days_until_renewal']
                print(f"  {status} {r['name']}: 还有 {days} 天续费")
        
        print(f"{'='*60}\n")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='订阅续费提醒检查')
    parser.add_argument('--dry-run', action='store_true', help='测试模式，不发送告警')
    parser.add_argument('--config', default='config.json', help='配置文件路径')
    
    args = parser.parse_args()
    
    try:
        checker = SubscriptionChecker(args.config)
        checker.check_subscriptions(dry_run=args.dry_run)
    except Exception as e:
        print(f"❌ 错误: {e}")
        exit(1)


if __name__ == '__main__':
    main()
