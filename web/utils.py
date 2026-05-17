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
from flask import jsonify, make_response, request
from core.logger import get_logger
from core.config_loader import get_default_config_path, get_enable_web_alarm as _get_enable_web_alarm, get_refresh_interval as _get_refresh_interval
from services.config_service import load_config as _load_config

logger = get_logger('web.utils')

def get_enable_web_alarm() -> bool:
    return _get_enable_web_alarm()


def get_refresh_interval() -> int:
    """
    获取刷新间隔配置

    优先级：
    1. 环境变量 BALANCE_REFRESH_INTERVAL_SECONDS
    2. config.json 中的 settings.balance_refresh_interval_seconds
    3. 默认值 3600 秒
    """
    return _get_refresh_interval(get_default_config_path())


def load_config_safe(config_path: str = None) -> Optional[Dict[str, Any]]:
    """
    安全加载配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        配置字典，失败返回 None
    """
    try:
        return _load_config(config_path or get_default_config_path(), validate=False)
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        return None




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
        if renewal_day <= 31:
            return None
        if not (101 <= renewal_day <= 1231):
            return "年度订阅的 renewal_day 格式错误，应为 MMDD（如 315 表示 3月15日）"
        month = renewal_day // 100
        day = renewal_day % 100
        try:
            from datetime import date
            date(2024, month, day)
        except ValueError:
            return "年度订阅的 renewal_day 日期无效，应为有效 MMDD（如 315 表示 3月15日）"
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


def mask_secret(value: Any, visible_prefix: int = 4, visible_suffix: int = 4) -> str:
    """对 API Key、密码等敏感字段做展示用脱敏。"""
    if value is None:
        return ''
    text = str(value)
    if not text:
        return ''
    if len(text) <= visible_prefix + visible_suffix:
        return '***'
    return f"{text[:visible_prefix]}***{text[-visible_suffix:]}"


def mask_project_config(project: Dict[str, Any]) -> Dict[str, Any]:
    masked = dict(project)
    if 'api_key' in masked:
        masked['api_key'] = mask_secret(masked.get('api_key'))
    return masked


def mask_email_config(email_config: Dict[str, Any]) -> Dict[str, Any]:
    masked = dict(email_config)
    if 'password' in masked:
        masked['password'] = '***' if masked.get('password') else ''
    return masked
