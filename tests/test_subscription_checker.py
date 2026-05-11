"""
订阅续费检查器测试 — 周/月/年周期边界用例
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock
from services.subscription_checker import SubscriptionChecker


class TestSafeReplaceYear:
    """_safe_replace_year 闰年安全替换测试"""

    def test_normal_date(self):
        dt = datetime(2024, 6, 15)
        result = SubscriptionChecker._safe_replace_year(dt, 2025)
        assert result == datetime(2025, 6, 15)

    def test_leap_day_to_non_leap_year(self):
        """闰年 2/29 → 非闰年回退到 2/28"""
        dt = datetime(2024, 2, 29)
        result = SubscriptionChecker._safe_replace_year(dt, 2025)
        assert result == datetime(2025, 2, 28)

    def test_leap_day_to_leap_year(self):
        """闰年 2/29 → 闰年保持 2/29"""
        dt = datetime(2024, 2, 29)
        result = SubscriptionChecker._safe_replace_year(dt, 2028)
        assert result == datetime(2028, 2, 29)

    def test_dec_31_year_change(self):
        dt = datetime(2024, 12, 31)
        result = SubscriptionChecker._safe_replace_year(dt, 2025)
        assert result == datetime(2025, 12, 31)


class TestWeeklyCycle:
    """周周期 _calculate_days_until_renewal 测试"""

    def setup_method(self, method):
        self.checker = SubscriptionChecker.__new__(SubscriptionChecker)
        self.checker.config = {'subscriptions': []}
        self.checker.results = []

    def test_today_is_renewal_day(self):
        """续费日当天应返回 0 天"""
        # 2024-01-08 是周一 (weekday=0), renewal_day=1 表示周一
        today = datetime(2024, 1, 8)
        days, next_date = self.checker._calculate_days_until_renewal('weekly', 1, today)
        assert days == 0
        assert next_date == today

    def test_one_day_before_renewal(self):
        """续费日前一天"""
        # 2024-01-07 是周日, renewal_day=1 (周一) → 明天
        today = datetime(2024, 1, 7)
        days, next_date = self.checker._calculate_days_until_renewal('weekly', 1, today)
        assert days == 1

    def test_day_after_renewal(self):
        """续费日后一天 → 下周"""
        # 2024-01-09 是周二, renewal_day=1 (周一) → 6天后
        today = datetime(2024, 1, 9)
        days, next_date = self.checker._calculate_days_until_renewal('weekly', 1, today)
        assert days == 6

    def test_sunday_renewal(self):
        """周日续费（renewal_day=7）"""
        # 2024-01-08 是周一, renewal_day=7 (周日) → 6天后
        today = datetime(2024, 1, 8)
        days, next_date = self.checker._calculate_days_until_renewal('weekly', 7, today)
        assert days == 6

    def test_midweek(self):
        """周三续费，当前周一"""
        # 2024-01-08 是周一, renewal_day=3 (周三) → 2天后
        today = datetime(2024, 1, 8)
        days, next_date = self.checker._calculate_days_until_renewal('weekly', 3, today)
        assert days == 2


class TestMonthlyCycle:
    """月周期 _calculate_days_until_renewal 测试"""

    def setup_method(self, method):
        self.checker = SubscriptionChecker.__new__(SubscriptionChecker)
        self.checker.config = {'subscriptions': []}
        self.checker.results = []

    def test_today_is_renewal_day(self):
        """续费当天"""
        today = datetime(2024, 1, 15)
        days, next_date = self.checker._calculate_days_until_renewal('monthly', 15, today)
        assert days == 0

    def test_before_renewal_day(self):
        """续费日之前"""
        today = datetime(2024, 1, 10)
        days, next_date = self.checker._calculate_days_until_renewal('monthly', 15, today)
        assert days == 5

    def test_after_renewal_day(self):
        """续费日之后 → 下月"""
        today = datetime(2024, 1, 20)
        days, next_date = self.checker._calculate_days_until_renewal('monthly', 15, today)
        assert next_date == datetime(2024, 2, 15)

    def test_renewal_day_31_in_feb(self):
        """31号续费在2月 → 使用2月最后一天"""
        today = datetime(2024, 2, 1)
        days, next_date = self.checker._calculate_days_until_renewal('monthly', 31, today)
        # 2024 是闰年，2月有29天
        assert next_date == datetime(2024, 2, 29)

    def test_renewal_day_31_in_short_month(self):
        """31号续费在4月（30天）→ 使用4月30日"""
        today = datetime(2024, 4, 1)
        days, next_date = self.checker._calculate_days_until_renewal('monthly', 31, today)
        assert next_date == datetime(2024, 4, 30)

    def test_december_to_january(self):
        """12月过了续费日 → 下月是明年1月"""
        today = datetime(2024, 12, 20)
        days, next_date = self.checker._calculate_days_until_renewal('monthly', 15, today)
        assert next_date == datetime(2025, 1, 15)

    def test_last_day_of_month(self):
        """月末测试"""
        today = datetime(2024, 1, 31)
        days, next_date = self.checker._calculate_days_until_renewal('monthly', 15, today)
        assert next_date == datetime(2024, 2, 15)


class TestYearlyCycle:
    """年周期 _calculate_days_until_renewal 测试"""

    def setup_method(self, method):
        self.checker = SubscriptionChecker.__new__(SubscriptionChecker)
        self.checker.config = {'subscriptions': []}
        self.checker.results = []

    def test_with_last_renewed_date(self):
        """有上次续费日"""
        today = datetime(2024, 6, 1)
        days, next_date = self.checker._calculate_days_until_renewal(
            'yearly', 1, today, last_renewed_date='2024-01-15'
        )
        assert next_date == datetime(2025, 1, 15)

    def test_past_renewal_this_year(self):
        """今年续费日已过 → 下年"""
        today = datetime(2024, 3, 1)
        days, next_date = self.checker._calculate_days_until_renewal(
            'yearly', 1, today, last_renewed_date='2023-02-15'
        )
        assert next_date == datetime(2025, 2, 15)
        assert days > 0

    def test_leap_year_last_renewed_feb29(self):
        """上次续费日是闰年 2/29 → 下次非闰年回退到 2/28"""
        today = datetime(2025, 1, 1)
        days, next_date = self.checker._calculate_days_until_renewal(
            'yearly', 1, today, last_renewed_date='2024-02-29'
        )
        assert next_date == datetime(2025, 2, 28)

    def test_no_last_renewed_date(self):
        """无上次续费日 → 明年今天"""
        today = datetime(2024, 6, 15)
        days, next_date = self.checker._calculate_days_until_renewal(
            'yearly', 1, today, last_renewed_date=None
        )
        assert next_date == datetime(2025, 6, 15)

    def test_no_last_renewed_leap_day(self):
        """无上次续费日，今天是闰年 2/29 → 明年 2/28"""
        today = datetime(2024, 2, 29)
        days, next_date = self.checker._calculate_days_until_renewal(
            'yearly', 1, today, last_renewed_date=None
        )
        assert next_date == datetime(2025, 2, 28)

    def test_mmdd_before_renewal(self):
        """无上次续费日时，年付 renewal_day 支持 MMDD"""
        today = datetime(2024, 1, 1)
        days, next_date = self.checker._calculate_days_until_renewal(
            'yearly', 315, today, last_renewed_date=None
        )
        assert next_date == datetime(2024, 3, 15)
        assert days == 74

    def test_mmdd_after_renewal(self):
        """MMDD 日期已过时，续费日跳到下一年"""
        today = datetime(2024, 4, 1)
        days, next_date = self.checker._calculate_days_until_renewal(
            'yearly', 315, today, last_renewed_date=None
        )
        assert next_date == datetime(2025, 3, 15)
        assert days > 0


class TestCalculateCycleStart:
    """_calculate_cycle_start 测试"""

    def setup_method(self, method):
        self.checker = SubscriptionChecker.__new__(SubscriptionChecker)
        self.checker.config = {'subscriptions': []}
        self.checker.results = []

    def test_weekly_cycle_start(self):
        """周周期起始日 = 下次续费日 - 7天"""
        next_renewal = datetime(2024, 1, 15)
        start = self.checker._calculate_cycle_start('weekly', 1, datetime(2024, 1, 10), next_renewal)
        assert start == datetime(2024, 1, 8)

    def test_yearly_cycle_start(self):
        """年周期起始日 = 下次续费日 - 1年"""
        next_renewal = datetime(2025, 6, 15)
        start = self.checker._calculate_cycle_start('yearly', 1, datetime(2024, 12, 1), next_renewal)
        assert start == datetime(2024, 6, 15)

    def test_yearly_cycle_start_leap_year(self):
        """年周期闰年边界"""
        next_renewal = datetime(2025, 2, 28)
        start = self.checker._calculate_cycle_start('yearly', 1, datetime(2024, 12, 1), next_renewal)
        assert start == datetime(2024, 2, 28)

    def test_monthly_before_renewal_day(self):
        """月周期，当前日 < 续费日"""
        today = datetime(2024, 3, 10)
        next_renewal = datetime(2024, 3, 15)
        start = self.checker._calculate_cycle_start('monthly', 15, today, next_renewal)
        assert start == datetime(2024, 2, 15)

    def test_monthly_after_renewal_day(self):
        """月周期，当前日 >= 续费日"""
        today = datetime(2024, 3, 20)
        next_renewal = datetime(2024, 4, 15)
        start = self.checker._calculate_cycle_start('monthly', 15, today, next_renewal)
        assert start == datetime(2024, 3, 15)

    def test_monthly_january_before_renewal(self):
        """月周期，1月且当前日 < 续费日 → 上月是去年12月"""
        today = datetime(2024, 1, 5)
        next_renewal = datetime(2024, 1, 15)
        start = self.checker._calculate_cycle_start('monthly', 15, today, next_renewal)
        assert start == datetime(2023, 12, 15)

    def test_monthly_cycle_start_uses_month_end(self):
        """月周期 31 号在短月中回退到月末"""
        today = datetime(2024, 3, 20)
        next_renewal = datetime(2024, 3, 31)
        start = self.checker._calculate_cycle_start('monthly', 31, today, next_renewal)
        assert start == datetime(2024, 2, 29)


class TestGetCycleText:
    """_get_cycle_text 测试"""

    def setup_method(self, method):
        self.checker = SubscriptionChecker.__new__(SubscriptionChecker)
        self.checker.config = {'subscriptions': []}
        self.checker.results = []

    def test_weekly_text(self):
        assert self.checker._get_cycle_text('weekly', 1) == '每周 周一'
        assert self.checker._get_cycle_text('weekly', 7) == '每周 周日'

    def test_monthly_text(self):
        assert self.checker._get_cycle_text('monthly', 15) == '每月 15 号'

    def test_yearly_text(self):
        assert self.checker._get_cycle_text('yearly', 1) == '每年（固定日期）'
        assert self.checker._get_cycle_text('yearly', 315) == '每年 3月15日'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
