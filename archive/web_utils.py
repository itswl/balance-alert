#!/usr/bin/env python3
"""
Web 服务器工具函数

包含配置操作、缓存管理、审计日志等辅助功能
"""
import json
import fcntl
import tempfile
from pathlib import Path
from typing import Dict, Any, List
from logger import get_logger
from state_manager import StateManager

logger = get_logger('web_utils')


def load_config_safe(config_file: str = 'config.json') -> Dict[str, Any]:
    """安全地加载配置文件（不验证，用于Web接口）"""
    from config_loader import load_config_with_env_vars
    try:
        return load_config_with_env_vars(config_file, validate=False)
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}", exc_info=True)
        return {
            'projects': [],
            'subscriptions': [],
            'email': [],
            'webhook': {},
            'settings': {}
        }


def write_config_to_file(config: Dict[str, Any], config_file: str = 'config.json') -> None:
    """写入配置到文件（使用文件锁确保原子性）"""
    config_path = Path(config_file)

    # 确保父目录存在
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # 使用临时文件 + 原子重命名
    temp_fd, temp_path = tempfile.mkstemp(
        dir=config_path.parent,
        prefix=f'.{config_path.name}.',
        suffix='.tmp'
    )

    try:
        # 写入临时文件
        with open(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.flush()

        # 原子重命名
        Path(temp_path).replace(config_path)
        logger.debug(f"配置已保存到: {config_file}")

    except Exception as e:
        # 清理临时文件
        try:
            Path(temp_path).unlink(missing_ok=True)
        except Exception:
            pass
        raise e


def audit_log(action: str, details: Dict[str, Any], audit_file: str = 'logs/audit.log') -> None:
    """记录审计日志"""
    from datetime import datetime
    try:
        audit_path = Path(audit_file)
        audit_path.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'details': details
        }

        with open(audit_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

        logger.debug(f"审计日志: {action} - {details}")

    except Exception as e:
        logger.error(f"写入审计日志失败: {e}", exc_info=True)


def update_balance_cache(results: List[Dict[str, Any]], state_mgr: StateManager) -> None:
    """更新余额缓存（使用状态管理器）"""
    state_mgr.update_balance_state(results)


def update_subscription_cache(results: List[Dict[str, Any]], state_mgr: StateManager) -> None:
    """更新订阅缓存（使用状态管理器）"""
    state_mgr.update_subscription_state(results)


def save_cache_file(state_mgr: StateManager, cache_file: str = 'cache.json') -> None:
    """保存缓存到文件"""
    try:
        cache_data = {
            'balance': state_mgr.get_balance_state(),
            'subscription': state_mgr.get_subscription_state(),
        }

        cache_path = Path(cache_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # 使用临时文件 + 原子重命名
        temp_fd, temp_path = tempfile.mkstemp(
            dir=cache_path.parent,
            prefix=f'.{cache_path.name}.',
            suffix='.tmp'
        )

        try:
            with open(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
                f.flush()

            Path(temp_path).replace(cache_path)
            logger.debug(f"缓存已保存到: {cache_file}")

        except Exception as e:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass
            raise e

    except Exception as e:
        logger.error(f"保存缓存文件失败: {e}", exc_info=True)


def load_cache_file(state_mgr: StateManager, cache_file: str = 'cache.json') -> bool:
    """从文件加载缓存"""
    try:
        cache_path = Path(cache_file)
        if not cache_path.exists():
            logger.info(f"缓存文件不存在: {cache_file}")
            return False

        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)

        if 'balance' in cache_data:
            state_mgr._balance_state = cache_data['balance']
            logger.info(f"从缓存加载余额状态: {len(cache_data['balance'].get('projects', []))} 个项目")

        if 'subscription' in cache_data:
            state_mgr._subscription_state = cache_data['subscription']
            logger.info(f"从缓存加载订阅状态: {len(cache_data['subscription'].get('subscriptions', []))} 个订阅")

        return True

    except Exception as e:
        logger.error(f"加载缓存文件失败: {e}", exc_info=True)
        return False


def validate_renewal_day(renewal_day: int, cycle_type: str) -> str:
    """验证续费日期的有效性

    Args:
        renewal_day: 续费日
        cycle_type: 周期类型 (weekly/monthly/yearly)

    Returns:
        str: 错误信息，如果为空字符串则验证通过
    """
    if cycle_type == 'weekly':
        if not 1 <= renewal_day <= 7:
            return '周循环的续费日期应在 1-7 之间'
    elif cycle_type == 'monthly':
        if not 1 <= renewal_day <= 31:
            return '月循环的续费日期应在 1-31 之间'
    elif cycle_type == 'yearly':
        if not 1 <= renewal_day <= 31:
            return '年循环的续费日期应在 1-31 之间'
    else:
        return f'未知的周期类型: {cycle_type}'

    return ''


def calculate_yearly_renewed_date(renewal_month: int, renewal_day: int) -> tuple:
    """计算年周期的续费日期

    Args:
        renewal_month: 续费月份 (1-12)
        renewal_day: 续费日 (1-31)

    Returns:
        tuple: (date_str, error_msg)
            - date_str: YYYY-MM-DD 格式的日期字符串
            - error_msg: 错误信息（为空则成功）
    """
    from datetime import datetime, date
    import calendar

    if not 1 <= renewal_month <= 12:
        return ('', '续费月份应在 1-12 之间')

    # 获取当前年份
    current_year = datetime.now().year

    # 获取该月的最大天数
    max_day = calendar.monthrange(current_year, renewal_month)[1]

    if renewal_day > max_day:
        return ('', f'{renewal_month}月最多只有{max_day}天')

    try:
        date_obj = date(current_year, renewal_month, renewal_day)
        date_str = date_obj.isoformat()
        return (date_str, '')
    except ValueError as e:
        return ('', f'日期无效: {e}')


def refresh_subscription_cache(state_mgr: StateManager) -> None:
    """刷新订阅缓存"""
    from subscription_checker import SubscriptionChecker
    try:
        checker = SubscriptionChecker('config.json')
        checker.check_subscriptions(dry_run=True)  # 不发送告警
        update_subscription_cache(checker.results, state_mgr)
        logger.debug("订阅缓存已刷新")
    except Exception as e:
        logger.error(f"刷新订阅缓存失败: {e}", exc_info=True)
