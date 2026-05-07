#!/usr/bin/env python3
"""
Web 中间件

提供认证、请求验证等装饰器
"""
import hmac
import os
from functools import wraps
from flask import request, jsonify
from pydantic import ValidationError


def _get_api_key() -> str:
    return (os.environ.get('API_KEY') or os.environ.get('WEB_API_KEY') or '').strip()


def _extract_api_key() -> str:
    token = (request.headers.get('X-API-Key', '') or '').strip()
    if token:
        return token

    auth = (request.headers.get('Authorization', '') or '').strip()
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()

    return ''


def _auth_not_configured():
    return jsonify({
        'status': 'error',
        'message': 'API Key 未配置，请设置 API_KEY 或 WEB_API_KEY'
    }), 503


def _unauthorized():
    return jsonify({
        'status': 'error',
        'message': 'API Key 无效或未提供'
    }), 401


def validate_api_key_request() -> bool:
    if request.method == 'OPTIONS':
        return True

    api_key = _get_api_key()
    if not api_key:
        return False

    token = _extract_api_key()
    return bool(token) and hmac.compare_digest(token, api_key)


def require_api_key(f):
    """API Key 认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _get_api_key():
            return _auth_not_configured()
        if not validate_api_key_request():
            return _unauthorized()
        return f(*args, **kwargs)
    return decorated


def protect_api_endpoints(app) -> None:
    @app.before_request
    def _api_key_guard():
        path = request.path or ''
        if not path.startswith('/api/'):
            return None
        if not _get_api_key():
            return _auth_not_configured()
        if validate_api_key_request():
            return None
        return _unauthorized()


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
