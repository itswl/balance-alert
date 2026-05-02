#!/usr/bin/env python3
"""
Web 中间件

提供认证、验证等装饰器
"""
import os
import base64
from functools import wraps
from flask import request, jsonify
from pydantic import ValidationError


# API 认证配置
def _get_api_key() -> str:
    return os.environ.get('API_KEY') or os.environ.get('WEB_API_KEY') or ''


def _get_allow_paths_raw() -> str:
    return os.environ.get('API_KEY_ALLOW_PATHS', '/health')


def _is_allowed_path(path: str) -> bool:
    if not path:
        return False
    raw = (_get_allow_paths_raw() or '').strip()
    if not raw:
        return False
    for item in raw.split(','):
        rule = (item or '').strip()
        if not rule:
            continue
        if rule.endswith('*'):
            prefix = rule[:-1]
            if prefix and path.startswith(prefix):
                return True
            continue
        if path == rule:
            return True
    return False


def _extract_api_key() -> str:
    token = (request.headers.get('X-API-Key', '') or '').strip()
    if token:
        return token
    token = (request.headers.get('X-Api-Key', '') or '').strip()
    if token:
        return token
    token = (request.headers.get('Api-Key', '') or '').strip()
    if token:
        return token
    auth = (request.headers.get('Authorization', '') or '').strip()
    lower = auth.lower()
    token = ''
    if lower.startswith('bearer '):
        token = auth[7:].strip()
    elif lower.startswith('basic '):
        b64 = auth[6:].strip()
        try:
            raw = base64.b64decode(b64).decode('utf-8', errors='ignore')
            if ':' in raw:
                token = raw.split(':', 1)[1].strip()
            else:
                token = raw.strip()
        except Exception:
            token = ''
    if not token:
        token = (request.args.get('api_key', '') or '').strip()
    return token


def _unauthorized():
    resp = jsonify({'status': 'error', 'message': '未授权访问'})
    resp.status_code = 401
    resp.headers['WWW-Authenticate'] = 'Basic realm="Protected", charset="UTF-8"'
    return resp


def validate_api_key_request() -> bool:
    if request.method == 'OPTIONS':
        return True
    path = request.path or ''
    if _is_allowed_path(path):
        return True
    api_key = _get_api_key()
    if not api_key:
        return True
    token = _extract_api_key()
    return token == api_key


def protect_api_endpoints(app) -> None:
    @app.before_request
    def _api_key_guard():
        path = request.path or ''
        if not path.startswith('/api/'):
            return None
        if validate_api_key_request():
            return None
        return _unauthorized()


def protect_all_endpoints(app) -> None:
    @app.before_request
    def _api_key_guard_all():
        if validate_api_key_request():
            return None
        return _unauthorized()


def require_api_key(f):
    """API 认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not validate_api_key_request():
            return _unauthorized()
        return f(*args, **kwargs)
    return decorated


def validate_request(model_class):
    """
    请求验证装饰器，使用 Pydantic 模型验证请求体

    用法：
        @validate_request(AddSubscriptionRequest)
        def my_endpoint(validated_data: AddSubscriptionRequest):
            # validated_data 是已验证的 Pydantic 模型实例
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            try:
                # 获取请求数据
                data = request.get_json()
                if data is None:
                    return jsonify({
                        'status': 'error',
                        'message': '请求体必须是有效的 JSON'
                    }), 400

                # 验证数据
                validated_data = model_class(**data)

                # 调用原函数，传入验证后的数据
                return f(validated_data=validated_data, *args, **kwargs)

            except ValidationError as e:
                # Pydantic 验证错误
                errors = [
                    f"{' -> '.join(str(loc) for loc in error['loc'])}: {error['msg']}"
                    for error in e.errors()
                ]
                return jsonify({
                    'status': 'error',
                    'errors': errors
                }), 400
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'验证失败: {str(e)}'
                }), 400
        return decorated
    return decorator
