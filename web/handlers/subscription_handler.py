#!/usr/bin/env python3
"""
订阅业务逻辑处理器

处理订阅管理相关的业务逻辑
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from subscription_checker import SubscriptionChecker
from state_manager import StateManager
from logger import get_logger

logger = get_logger('web.handlers.subscription')


def update_subscription_cache(results: List[Dict[str, Any]], state_mgr: StateManager) -> None:
    """
    更新订阅状态缓存

    Args:
        results: 订阅检查结果列表
        state_mgr: 状态管理器实例
    """
    state_mgr.update_subscription(results)


def refresh_subscription_cache(config_path: str, state_mgr: StateManager) -> None:
    """
    刷新订阅缓存

    Args:
        config_path: 配置文件路径
        state_mgr: 状态管理器实例
    """
    try:
        checker = SubscriptionChecker(config_path)
        results = checker.check_all_subscriptions()
        update_subscription_cache(results, state_mgr)
    except Exception as e:
        logger.error(f"刷新订阅缓存失败: {e}", exc_info=True)


def calculate_next_renewal_date(cycle_type: str, renewal_day: int, from_date: datetime = None) -> datetime:
    """
    计算下次续费日期

    Args:
        cycle_type: 周期类型（weekly/monthly/yearly）
        renewal_day: 续费日期
        from_date: 起始日期（默认今天）

    Returns:
        下次续费日期
    """
    if from_date is None:
        from_date = datetime.now()

    if cycle_type == 'weekly':
        # renewal_day: 1-7 (周一到周日)
        days_ahead = renewal_day - from_date.isoweekday()
        if days_ahead <= 0:
            days_ahead += 7
        return from_date + timedelta(days=days_ahead)

    elif cycle_type == 'monthly':
        # renewal_day: 1-31
        next_month = from_date.month + 1
        next_year = from_date.year
        if next_month > 12:
            next_month = 1
            next_year += 1

        # 处理月份天数不足的情况（如 31 号在 2 月）
        import calendar
        max_day = calendar.monthrange(next_year, next_month)[1]
        actual_day = min(renewal_day, max_day)

        return datetime(next_year, next_month, actual_day)

    elif cycle_type == 'yearly':
        # renewal_day 格式: MMDD (如 315 表示 3月15日)
        renewal_month = renewal_day // 100
        renewal_day_of_month = renewal_day % 100

        next_year = from_date.year + 1
        return datetime(next_year, renewal_month, renewal_day_of_month)

    else:
        raise ValueError(f"不支持的周期类型: {cycle_type}")
