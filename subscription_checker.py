#!/usr/bin/env python3
"""
订阅续费提醒检查器
"""
import json
import sys
from datetime import datetime, timedelta
from webhook_adapter import WebhookAdapter
from logger import get_logger

# 创建 logger
logger = get_logger('subscription_checker')


class SubscriptionChecker:
    """订阅续费检查器"""
    
    def __init__(self, config_path='config.json'):
        """初始化"""
        self.config_path = config_path
        self.config = self._load_config()
        self.results = []
    
    def _load_config(self):
        """加载配置文件"""
        from config_loader import load_config_with_env_vars
        return load_config_with_env_vars(self.config_path)
    
    def check_subscriptions(self, dry_run=False):
        """
        检查所有订阅
        
        Args:
            dry_run: 测试模式，不发送告警
        """
        subscriptions = self.config.get('subscriptions', [])
        
        if not subscriptions:
            logger.info("📋 没有配置订阅项目")
            return
        
        # 过滤启用的订阅
        enabled_subs = [s for s in subscriptions if s.get('enabled', True)]
        
        logger.info(f"📅 开始检查 {len(enabled_subs)} 个订阅...")
        if dry_run:
            logger.info("🔍 [测试模式] 不会发送实际告警")
        
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
        last_renewed_date = sub.get('last_renewed_date')  # 上次续费日期
        cycle_type = sub.get('cycle_type', 'monthly')  # 续费周期类型: weekly, monthly, yearly
        
        logger.info(f"{'='*60}")
        logger.info(f"📦 订阅: {name}")

        # 根据周期类型显示不同的续费信息
        cycle_text = self._get_cycle_text(cycle_type, renewal_day)
        logger.info(f"   续费周期: {cycle_text}")
        logger.info(f"   金额: {currency} {amount}")
        logger.info(f"{'='*60}")
        
        # 计算距离续费日的天数
        days_until_renewal, next_renewal_date = self._calculate_days_until_renewal(
            cycle_type, renewal_day, today, last_renewed_date
        )
        
        logger.info(f"📍 距离续费还有: {days_until_renewal} 天 (下次续费: {next_renewal_date.strftime('%Y-%m-%d')})")
        
        # 检查是否在本续费周期内已经续费
        already_renewed = False
        if last_renewed_date:
            try:
                last_renewed = datetime.strptime(last_renewed_date, '%Y-%m-%d')
                # 计算当前续费周期的起始日期
                cycle_start = self._calculate_cycle_start(cycle_type, renewal_day, today, next_renewal_date)
                
                # 如果上次续费日期在当前周期之后，说明已经续费了
                if last_renewed >= cycle_start:
                    already_renewed = True
                    logger.info(f"✅ 本周期已续费 (续费日期: {last_renewed_date})")
            except ValueError:
                logger.warning(f"⚠️  续费日期格式错误: {last_renewed_date}")
        
        # 判断是否需要告警（如果已续费则不告警）
        need_alert = (days_until_renewal <= alert_days_before and 
                     days_until_renewal >= 0 and 
                     not already_renewed)
        alert_sent = False
        
        if already_renewed:
            logger.info(f"✅ 本周期已续费，无需提醒")
        elif need_alert:
            logger.warning(f"⚠️  需要提醒续费! (提前 {alert_days_before} 天)")

            if not dry_run:
                alert_sent = self._send_alert(sub, days_until_renewal)
            else:
                logger.info("🔍 [测试模式] 跳过发送告警")
        else:
            logger.info(f"✅ 无需提醒")
        
        return {
            'name': name,
            'renewal_day': renewal_day,
            'cycle_type': cycle_type,
            'days_until_renewal': days_until_renewal,
            'next_renewal_date': next_renewal_date.strftime('%Y-%m-%d'),
            'need_alert': need_alert,
            'alert_sent': alert_sent,
            'amount': amount,
            'currency': currency,
            'already_renewed': already_renewed,
            'last_renewed_date': last_renewed_date
        }
    
    def _get_cycle_text(self, cycle_type, renewal_day):
        """获取周期描述文本"""
        if cycle_type == 'weekly':
            weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
            if 1 <= renewal_day <= 7:
                return f"每周 {weekdays[renewal_day - 1]}"
            return f"每周第 {renewal_day} 天"
        elif cycle_type == 'yearly':
            return f"每年（固定日期）"
        else:  # monthly
            return f"每月 {renewal_day} 号"
    
    @staticmethod
    def _safe_replace_year(dt, new_year):
        """安全地替换日期的年份，处理闰年2/29的情况"""
        try:
            return dt.replace(year=new_year)
        except ValueError:
            # 闰年2/29 → 非闰年回退到2/28
            return datetime(new_year, dt.month, 28)

    def _calculate_cycle_start(self, cycle_type, renewal_day, today, next_renewal_date):
        """计算当前续费周期的起始日期"""
        if cycle_type == 'weekly':
            # 周周期：从上周的续费日开始
            return next_renewal_date - timedelta(days=7)
        elif cycle_type == 'yearly':
            # 年周期：从去年的同日期开始
            return self._safe_replace_year(next_renewal_date, next_renewal_date.year - 1)
        else:  # monthly
            # 月周期：从上个月的续费日开始
            if today.day < renewal_day:
                if today.month == 1:
                    return datetime(today.year - 1, 12, renewal_day)
                else:
                    return datetime(today.year, today.month - 1, renewal_day)
            else:
                return datetime(today.year, today.month, renewal_day)
    
    def _calculate_days_until_renewal(self, cycle_type, renewal_day, today, last_renewed_date=None):
        """
        计算距离续费日的天数

        Args:
            cycle_type: 周期类型 (weekly, monthly, yearly)
            renewal_day: 续费日 (weekly: 1-7表示周一到周日, monthly: 1-31, yearly: 使用上次续费的月日)
            today: 当前日期
            last_renewed_date: 上次续费日期字符串

        Returns:
            (days, next_renewal_date): 距离续费的天数和下次续费日期
        """
        if cycle_type == 'weekly':
            return self._calculate_weekly_renewal(renewal_day, today)
        elif cycle_type == 'yearly':
            return self._calculate_yearly_renewal(renewal_day, today, last_renewed_date)
        else:
            return self._calculate_monthly_renewal(renewal_day, today)

    def _calculate_weekly_renewal(self, renewal_day, today):
        """计算周周期的下次续费日期

        Args:
            renewal_day: 1=周一, 2=周二, ..., 7=周日
            today: 当前日期

        Returns:
            (days, next_renewal_date)
        """
        current_weekday = today.weekday() + 1  # Python的weekday: 0=周一, 6=周日
        days_ahead = renewal_day - current_weekday

        if days_ahead < 0:  # 本周已过
            days_ahead += 7

        next_renewal_date = today + timedelta(days=days_ahead)
        return days_ahead, next_renewal_date

    def _calculate_yearly_renewal(self, renewal_day, today, last_renewed_date=None):
        """计算年周期的下次续费日期

        Args:
            renewal_day: 续费日
            today: 当前日期
            last_renewed_date: 上次续费日期字符串

        Returns:
            (days, next_renewal_date)
        """
        if last_renewed_date:
            try:
                last_renewed = datetime.strptime(last_renewed_date, '%Y-%m-%d')
                next_renewal_date = self._safe_replace_year(last_renewed, last_renewed.year + 1)

                while next_renewal_date <= today:
                    next_renewal_date = self._safe_replace_year(next_renewal_date, next_renewal_date.year + 1)

                delta = next_renewal_date - today
                return delta.days, next_renewal_date
            except ValueError:
                pass

        # 如果没有上次续费日期，使用今年的今天作为续费日
        next_renewal_date = self._safe_replace_year(today, today.year + 1)
        delta = next_renewal_date - today
        return delta.days, next_renewal_date

    def _calculate_monthly_renewal(self, renewal_day, today):
        """计算月周期的下次续费日期

        Args:
            renewal_day: 续费日 (1-31)
            today: 当前日期

        Returns:
            (days, next_renewal_date)
        """
        current_day = today.day

        if current_day <= renewal_day:
            # 本月还没到续费日
            try:
                next_renewal_date = datetime(today.year, today.month, renewal_day)
            except ValueError:
                # 如果续费日超过本月天数，使用本月最后一天
                next_month = today.month + 1 if today.month < 12 else 1
                next_year = today.year if today.month < 12 else today.year + 1
                next_renewal_date = datetime(next_year, next_month, 1) - timedelta(days=1)
        else:
            # 已经过了本月续费日，计算下个月
            if today.month == 12:
                next_year = today.year + 1
                next_month = 1
            else:
                next_year = today.year
                next_month = today.month + 1

            try:
                next_renewal_date = datetime(next_year, next_month, renewal_day)
            except ValueError:
                # 如果续费日超过下月天数，使用下月最后一天
                if next_month == 12:
                    next_renewal_date = datetime(next_year, 12, 31)
                else:
                    next_renewal_date = datetime(next_year, next_month + 1, 1) - timedelta(days=1)

        delta = next_renewal_date - today
        return delta.days, next_renewal_date
    
    def _send_alert(self, sub, days_until_renewal):
        """发送续费提醒告警"""
        webhook_config = self.config.get('webhook', {})
        webhook_url = webhook_config.get('url')
        webhook_type = webhook_config.get('type', 'custom')
        webhook_source = webhook_config.get('source', 'credit-monitor')
        
        if not webhook_url:
            logger.error("❌ 未配置 webhook 地址")
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
        logger.info(f"{'='*60}")
        logger.info("📊 订阅检查汇总")
        logger.info(f"{'='*60}")

        total = len(self.results)
        need_alert = sum(1 for r in self.results if r.get('need_alert', False))
        alert_sent = sum(1 for r in self.results if r.get('alert_sent', False))

        logger.info(f"总订阅数: {total}")
        logger.info(f"需要提醒: {need_alert}")
        logger.info(f"已发送提醒: {alert_sent}")

        if self.results:
            logger.info(f"详细结果:")
            for r in self.results:
                status = "⚠️需提醒" if r.get('need_alert') else "✅正常"
                days = r['days_until_renewal']
                logger.info(f"  {status} {r['name']}: 还有 {days} 天续费")

        logger.info(f"{'='*60}")


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
        logger.error(f"❌ 错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
