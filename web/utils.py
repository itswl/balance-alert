#!/usr/bin/env python3
"""
Web 工具函数

提供配置读取、缓存管理等工具函数
"""
import os
import json
import fcntl
import tempfile
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from flask import jsonify, make_response
from logger import get_logger
from config_loader import load_config_with_env_vars

logger = get_logger('web.utils')

# 配置常量
DEFAULT_REFRESH_INTERVAL = 3600  # 默认刷新间隔（秒）
DEFAULT_MIN_REFRESH_INTERVAL = 60  # 默认最小刷新间隔（秒）


def get_enable_web_alarm() -> bool:
    """获取 Web 告警是否启用"""
    return os.environ.get('ENABLE_WEB_ALARM', 'false').lower() == 'true'


def get_refresh_interval() -> int:
    """
    获取刷新间隔配置

    优先级：
    1. 环境变量 BALANCE_REFRESH_INTERVAL_SECONDS
    2. config.json 中的 settings.balance_refresh_interval_seconds
    3. 默认值 3600 秒
    """
    # 优先读取环境变量
    env_interval = os.environ.get('BALANCE_REFRESH_INTERVAL_SECONDS')
    if env_interval:
        try:
            interval = int(env_interval)
            if interval > 0:
                return interval
        except ValueError:
            pass

    # 读取配置文件
    try:
        config = load_config_with_env_vars('config.json', validate=False)
        interval = config.get('settings', {}).get('balance_refresh_interval_seconds')
        if interval and interval > 0:
            return interval
    except Exception:
        pass

    return DEFAULT_REFRESH_INTERVAL


def get_min_refresh_interval() -> int:
    """获取最小刷新间隔"""
    env_min_interval = os.environ.get('MIN_REFRESH_INTERVAL_SECONDS')
    if env_min_interval:
        try:
            return max(int(env_min_interval), 60)
        except ValueError:
            pass

    try:
        config = load_config_with_env_vars('config.json', validate=False)
        min_interval = config.get('settings', {}).get('min_refresh_interval_seconds')
        if min_interval and min_interval > 0:
            return max(min_interval, 60)
    except Exception:
        pass

    return DEFAULT_MIN_REFRESH_INTERVAL


def get_smart_refresh_config() -> Dict[str, Any]:
    """
    获取智能刷新配置

    Returns:
        dict: {
            'enabled': bool,
            'threshold_percent': float,
            'min_interval': int
        }
    """
    enabled = os.environ.get('ENABLE_SMART_REFRESH', 'false').lower() == 'true'

    threshold = 5.0  # 默认 5% 变化率
    env_threshold = os.environ.get('SMART_REFRESH_THRESHOLD_PERCENT')
    if env_threshold:
        try:
            threshold = float(env_threshold)
        except ValueError:
            pass

    return {
        'enabled': enabled,
        'threshold_percent': threshold,
        'min_interval': get_min_refresh_interval()
    }


def load_config_safe(config_path: str = 'config.json') -> Optional[Dict[str, Any]]:
    """
    安全加载配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        配置字典，失败返回 None
    """
    try:
        return load_config_with_env_vars(config_path, validate=False)
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        return None


def write_config(config: Dict[str, Any], config_path: str = 'config.json') -> None:
    """
    写入配置文件（带文件锁）

    Args:
        config: 配置字典
        config_path: 配置文件路径
    """
    # 使用临时文件 + 原子替换，避免写入过程中损坏
    config_file = Path(config_path)
    temp_file = tempfile.NamedTemporaryFile(
        mode='w',
        delete=False,
        dir=config_file.parent,
        prefix='.config_',
        suffix='.json'
    )

    try:
        with open(config_path, 'r+') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            temp_file.write(json.dumps(config, indent=2, ensure_ascii=False))
            temp_file.flush()
            temp_file.close()

            # 原子替换
            Path(temp_file.name).replace(config_path)

            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        # 清理临时文件
        try:
            Path(temp_file.name).unlink()
        except Exception:
            pass
        raise e


def validate_renewal_day(renewal_day: int, cycle_type: str) -> Optional[str]:
    """
    验证续费日期的合法性

    Args:
        renewal_day: 续费日期
        cycle_type: 周期类型（weekly/monthly/yearly）

    Returns:
        错误信息，验证通过返回 None
    """
    if cycle_type == 'weekly':
        if not (1 <= renewal_day <= 7):
            return "周度订阅的 renewal_day 必须在 1-7 之间（1=周一，7=周日）"
    elif cycle_type == 'monthly':
        if not (1 <= renewal_day <= 31):
            return "月度订阅的 renewal_day 必须在 1-31 之间"
    elif cycle_type == 'yearly':
        # renewal_day 存储的是 MMDD 格式的整数，例如 315 表示 3月15日
        if not (101 <= renewal_day <= 1231):
            return "年度订阅的 renewal_day 格式错误，应为 MMDD（如 315 表示 3月15日）"
    else:
        return f"不支持的周期类型: {cycle_type}"

    return None


def calculate_yearly_renewed_date(renewal_month: int, renewal_day: int) -> Tuple[Optional[str], Optional[str]]:
    """
    计算年度订阅的续费日期

    Args:
        renewal_month: 续费月份（1-12）
        renewal_day: 续费日期（1-31）

    Returns:
        (error_message, renewed_date_str)
    """
    from datetime import date

    if not (1 <= renewal_month <= 12):
        return ("月份必须在 1-12 之间", None)
    if not (1 <= renewal_day <= 31):
        return ("日期必须在 1-31 之间", None)

    current_year = date.today().year
    try:
        renewed_date = date(current_year, renewal_month, renewal_day)
        return (None, renewed_date.isoformat())
    except ValueError:
        return (f"无效的日期: {current_year}-{renewal_month:02d}-{renewal_day:02d}", None)


def make_etag_response(data: Dict[str, Any]):
    """
    创建带 ETag 的响应（支持 304 Not Modified）

    Args:
        data: 响应数据字典

    Returns:
        Flask Response 对象
    """
    # 计算 ETag
    content = json.dumps(data, sort_keys=True, ensure_ascii=False)
    etag = hashlib.md5(content.encode()).hexdigest()

    # 检查客户端 ETag
    client_etag = request.headers.get('If-None-Match')
    if client_etag == etag:
        return make_response('', 304)

    # 返回带 ETag 的响应
    response = make_response(jsonify(data))
    response.headers['ETag'] = etag
    response.headers['Cache-Control'] = 'private, must-revalidate'
    return response


def audit_log(action: str, details: Dict[str, Any]) -> None:
    """
    记录审计日志

    Args:
        action: 操作类型（如 'add_subscription', 'update_threshold'）
        details: 操作详情
    """
    logger.info(f"[AUDIT] {action}: {json.dumps(details, ensure_ascii=False)}")
