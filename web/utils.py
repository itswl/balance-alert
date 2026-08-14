#!/usr/bin/env python3
"""
Web 工具函数

提供配置读取、响应封装、审计日志等工具函数
"""
import hashlib
import json
from functools import wraps
from typing import Any, Dict

from flask import jsonify, make_response, request

from core.config_loader import get_default_config_path, load_config
from core.logger import get_logger

logger = get_logger('web.utils')


def handle_errors(action: str, *, bad_request_on_value_error: bool = False):
    """统一端点的异常出口：记录日志并返回 500。

    Args:
        action: 日志里的动作名，如「查询余额历史」
        bad_request_on_value_error: 查询参数由 parse_int_arg 校验的端点开启，
            让 ValueError 返回 400 而不是 500

    用法（放在 @route 之下、@validate_request 之上）：

        @bp.route('/x')
        @handle_errors('查询 X')
        def x(): ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if bad_request_on_value_error and isinstance(e, ValueError):
                    return json_error(f'参数错误: {e}', 400)
                logger.error(f"{action}失败: {e}", exc_info=True)
                return json_error(str(e), 500)
        return wrapper
    return decorator


def json_error(message: str, status_code: int = 500):
    return jsonify({'status': 'error', 'message': message}), status_code


def json_success(payload: Dict[str, Any], status_code: int = 200):
    return jsonify(payload), status_code


def parse_int_arg(name: str, default: int, min_value: int, max_value: int) -> int:
    value = int(request.args.get(name, default))
    if value < min_value or value > max_value:
        raise ValueError(f'{name} 必须在 {min_value}-{max_value} 之间')
    return value


def require_json_fields(*fields: str):
    data = request.get_json()
    if not data:
        return None, json_error(f"缺少必要参数: {', '.join(fields)}", 400)
    missing = [f for f in fields if f not in data]
    if missing:
        return None, json_error(f"缺少必要参数: {', '.join(missing)}", 400)
    return data, None


def load_config_safe(config_path: str = None) -> Dict[str, Any]:
    """安全加载配置，失败返回空 dict"""
    try:
        return load_config(config_path or get_default_config_path()) or {}
    except Exception as e:
        logger.error(f"加载配置失败: {e}", exc_info=True)
        return {}


def config_db_write(action) -> bool:
    """执行一次数据库配置写操作。

    Args:
        action: 接收 ConfigRepository 类的回调，如 ``lambda repo: repo.upsert_project(data)``

    Returns:
        bool: 数据库不可用或写入失败时返回 False
    """
    try:
        from database.repository import ConfigRepository
    except Exception:
        return False
    try:
        return bool(action(ConfigRepository))
    except Exception as e:
        logger.error(f"数据库配置写入失败: {e}", exc_info=True)
        return False


def make_etag_response(data: Dict[str, Any]):
    """创建带 ETag 的响应（支持 304 Not Modified）"""
    content = json.dumps(data, sort_keys=True, ensure_ascii=False)
    etag = hashlib.md5(content.encode()).hexdigest()

    client_etag = request.headers.get('If-None-Match')
    if client_etag == etag:
        return make_response('', 304)

    response = make_response(jsonify(data))
    response.headers['ETag'] = etag
    response.headers['Cache-Control'] = 'private, must-revalidate'
    return response


def audit_log(action: str, details: Dict[str, Any]) -> None:
    """记录审计日志"""
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
