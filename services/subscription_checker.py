#!/usr/bin/env python3
"""
订阅续费提醒检查器
"""
import calendar
from datetime import datetime, timedelta
from services.webhook_adapter import WebhookAdapter
from services import alert_store
from core.logger import get_logger
from core.config_loader import filter_enabled, load_config, make_subscription_id, owner_project_of, split_mmdd

logger = get_logger('subscription_checker')


def calculate_next_renewal_date(cycle_type: str, renewal_day: int, from_date: datetime = None) -> datetime:
    """计算下次续费日期（Web 标记续费后展示用）"""
    if from_date is None:
        from_date = datetime.now()

    if cycle_type == 'weekly':
        # renewal_day: 1-7 (周一到周日)
        days_ahead = renewal_day - from_date.isoweekday()
        if days_ahead <= 0:
            days_ahead += 7
        return from_date + timedelta(days=days_ahead)

    if cycle_type == 'monthly':
        return SubscriptionChecker._shift_month(from_date, 1, renewal_day)

    if cycle_type == 'yearly':
        month_day = split_mmdd(renewal_day)
        if month_day is None:
            # 兼容旧格式：只写了 1-31 时按周年日计算
            return SubscriptionChecker._safe_replace_year(from_date, from_date.year + 1)
        return datetime(from_date.year + 1, *month_day)

    raise ValueError(f"不支持的周期类型: {cycle_type}")


def _coerce_int(value, default: int) -> int:
    if value in (None, ''):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value, default: float = 0.0) -> float:
    if value in (None, ''):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class SubscriptionChecker:
    """订阅续费检查器"""
    
    def __init__(self):
        self.config = load_config()
        self.results = []

    def check_subscriptions(self, dry_run=False):
        """
        检查所有订阅

        Args:
            dry_run: 测试模式，不发送告警

        Returns:
            订阅检查结果列表（即使为空也返回空列表而非 None）
        """
        subscriptions = self.config.get('subscriptions', [])

        if not subscriptions:
            logger.info("没有订阅项目，可在页面上添加（需要数据库动态配置）")
            return []
        
        # 过滤启用的订阅
        enabled_subs = filter_enabled(subscriptions)
        
        logger.info(f"开始检查 {len(enabled_subs)} 个订阅" + ("（测试模式，不发送告警）" if dry_run else ""))
        
        today = datetime.now()
        
        for sub in enabled_subs:
            result = self._check_subscription(sub, today, dry_run)
            self.results.append(result)

        self._print_summary()
        return self.results
    
    def _check_subscription(self, sub, today, dry_run):
        """检查单个订阅：算出距续费天数，判断是否已续费、是否该提醒"""
        name = sub.get('name', '未知订阅')
        owner_project = owner_project_of(sub)
        renewal_day = _coerce_int(sub.get('renewal_day'), 1)
        alert_days_before = max(0, _coerce_int(sub.get('alert_days_before'), 3))
        amount = _coerce_float(sub.get('amount'), 0.0)
        last_renewed_date = sub.get('last_renewed_date')
        cycle_type = sub.get('cycle_type') or 'monthly'

        days_until_renewal, next_renewal_date = self._calculate_days_until_renewal(
            cycle_type, renewal_day, today, last_renewed_date
        )
        logger.info(
            f"订阅 {name}" + (f"（{owner_project}）" if owner_project else "")
            + f" | {WebhookAdapter._format_subscription_cycle(cycle_type, renewal_day)} | 金额 {amount}"
            f" | 距续费 {days_until_renewal} 天 (下次 {next_renewal_date.strftime('%Y-%m-%d')})"
        )

        already_renewed = self._already_renewed(cycle_type, renewal_day, today, next_renewal_date, last_renewed_date)
        need_alert = 0 <= days_until_renewal <= alert_days_before and not already_renewed
        alert_sent = False

        if already_renewed:
            logger.info(f"[{name}] 本周期已续费，无需提醒")
        elif not need_alert:
            logger.info(f"[{name}] 无需提醒")
        elif dry_run:
            logger.warning(f"[{name}] 需要提醒续费 (提前 {alert_days_before} 天)，测试模式不发送")
        else:
            logger.warning(f"[{name}] 需要提醒续费 (提前 {alert_days_before} 天)")
            alert_sent = self._send_unless_cooling(sub, name, amount, alert_days_before, days_until_renewal)

        return {
            'name': name,
            'owner_project': owner_project,
            'renewal_day': renewal_day,
            'cycle_type': cycle_type,
            'days_until_renewal': days_until_renewal,
            'next_renewal_date': next_renewal_date.strftime('%Y-%m-%d'),
            'need_alert': need_alert,
            'alert_sent': alert_sent,
            'amount': amount,
            'already_renewed': already_renewed,
            'last_renewed_date': last_renewed_date
        }

    def _already_renewed(self, cycle_type, renewal_day, today, next_renewal_date, last_renewed_date) -> bool:
        """上次续费日期落在当前周期内就算已续费"""
        if not last_renewed_date:
            return False
        try:
            last_renewed = datetime.strptime(last_renewed_date, '%Y-%m-%d')
        except ValueError:
            logger.warning(f"续费日期格式错误: {last_renewed_date}")
            return False
        cycle_start = self._calculate_cycle_start(cycle_type, renewal_day, today, next_renewal_date)
        return last_renewed >= cycle_start

    def _send_unless_cooling(self, sub, name, amount, alert_days_before, days_until_renewal) -> bool:
        """发送续费提醒并留痕；冷却窗口内跳过。返回是否真的发出。"""
        subscription_id = make_subscription_id(name)
        cooldown = alert_store.cooldown_seconds('subscription')
        if alert_store.in_cooldown(subscription_id, 'subscription_renewal', cooldown):
            logger.info(f"[{name}] 订阅提醒仍在冷却窗口内 ({cooldown}s)，跳过重复通知")
            return False
        sent = self._send_alert(sub, days_until_renewal)
        if sent:
            alert_store.record_alert(
                subscription_id, name, 'subscription_renewal',
                f"订阅续费提醒: {name} 将在 {days_until_renewal} 天后续费",
                amount, alert_days_before,
            )
        return sent

    @staticmethod
    def _safe_replace_year(dt, new_year):
        """安全地替换日期的年份，处理闰年2/29的情况"""
        try:
            return dt.replace(year=new_year)
        except ValueError:
            # 闰年2/29 → 非闰年回退到2/28
            return datetime(new_year, dt.month, 28)

    @staticmethod
    def _safe_month_date(year, month, day):
        """安全构造月内日期，目标日超出当月天数时回退到月末。"""
        max_day = calendar.monthrange(year, month)[1]
        return datetime(year, month, min(day, max_day))

    @classmethod
    def _shift_month(cls, date_value, months, day):
        """在 date_value 的月份上偏移 months 个月，取该月的 day（超出则回退月末）"""
        total = date_value.month - 1 + months
        return cls._safe_month_date(date_value.year + total // 12, total % 12 + 1, int(day))

    def _calculate_cycle_start(self, cycle_type, renewal_day, today, next_renewal_date):
        """计算当前续费周期的起始日期"""
        if cycle_type == 'weekly':
            # 周周期：从上周的续费日开始
            return next_renewal_date - timedelta(days=7)
        elif cycle_type == 'yearly':
            # 年周期：从去年的同日期开始
            return self._safe_replace_year(next_renewal_date, next_renewal_date.year - 1)
        else:  # monthly：本月续费日还没到就算上个月的周期
            months = -1 if today.day < renewal_day else 0
            return self._shift_month(today, months, renewal_day)
    
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
        # 续费日一律是 00:00，这里把"现在"截到当天零点，否则续费当天会算成 -1 天而漏提醒
        today = today.replace(hour=0, minute=0, second=0, microsecond=0)

        if cycle_type == 'weekly':
            # renewal_day: 1=周一 … 7=周日
            days_ahead = renewal_day - (today.weekday() + 1)
            if days_ahead < 0:  # 本周已过，看下周
                days_ahead += 7
            next_renewal_date = today + timedelta(days=days_ahead)
        elif cycle_type == 'yearly':
            next_renewal_date = self._next_yearly_date(renewal_day, today, last_renewed_date)
        else:
            # 本月的续费日还没过就用本月，否则下个月
            months = 0 if today.day <= renewal_day else 1
            next_renewal_date = self._shift_month(today, months, renewal_day)

        return (next_renewal_date - today).days, next_renewal_date

    def _next_yearly_date(self, renewal_day, today, last_renewed_date=None):
        """年付的下次续费日：优先按上次续费日推年，否则按 MMDD 取今年或明年"""
        if last_renewed_date:
            try:
                last_renewed = datetime.strptime(last_renewed_date, '%Y-%m-%d')
            except ValueError:
                last_renewed = None
            if last_renewed is not None:
                # 从上次续费日逐年推进到今天之后（上限 20 年，防脏数据死循环）
                candidate = self._safe_replace_year(last_renewed, last_renewed.year + 1)
                for _ in range(20):
                    if candidate > today:
                        return candidate
                    candidate = self._safe_replace_year(candidate, candidate.year + 1)

        month_day = split_mmdd(renewal_day)
        if month_day is None:
            # 兼容旧配置：年付但只写了 1-31（或非法值）时，用明年今天
            return self._safe_replace_year(today, today.year + 1)

        # 用 _safe_month_date 而非 datetime()：2月29日的订阅在平年要落到 2月28日
        candidate = self._safe_month_date(today.year, *month_day)
        if candidate >= today:
            return candidate
        return self._safe_month_date(today.year + 1, *month_day)
    
    def _send_alert(self, sub, days_until_renewal):
        """发送续费提醒告警"""
        adapter = WebhookAdapter.from_settings('credit-monitor')
        if adapter is None:
            logger.error("未配置 webhook 地址")
            return False

        # 获取订阅信息
        name = sub.get('name')
        owner_project = owner_project_of(sub)
        renewal_day = sub.get('renewal_day')
        amount = sub.get('amount', 0)
        
        # 发送提醒
        return adapter.send_subscription_alert(
            subscription_name=name,
            owner_project=owner_project,
            renewal_day=renewal_day,
            days_until_renewal=days_until_renewal,
            amount=amount,
            cycle_type=sub.get('cycle_type', 'monthly')
        )
    
    def _print_summary(self):
        need_alert = sum(1 for r in self.results if r.get('need_alert'))
        alert_sent = sum(1 for r in self.results if r.get('alert_sent'))
        logger.info(f"订阅检查汇总: 总订阅数={len(self.results)}, 需要提醒={need_alert}, 已发送提醒={alert_sent}")
        for r in self.results:
            owner = f" ({r['owner_project']})" if r.get('owner_project') else ""
            state = '需提醒' if r.get('need_alert') else '正常'
            logger.info(f"  {state} {r['name']}{owner}: 还有 {r['days_until_renewal']} 天续费")
