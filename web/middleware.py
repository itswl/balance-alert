#!/usr/bin/env python3
"""
Web 中间件

提供 API Key 认证与请求体验证
"""
import hmac
from functools import wraps

from flask import request, jsonify
from pydantic import ValidationError

from core.settings import get_settings


def _extract_api_key() -> str:
    token = (request.headers.get('X-API-Key', '') or '').strip()
    if token:
        return token

    auth = (request.headers.get('Authorization', '') or '').strip()
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()

    return ''


def protect_api_endpoints(app) -> None:
    """为所有 /api/ 路径启用 API Key 认证"""

    @app.before_request
    def _api_key_guard():
        if not (request.path or '').startswith('/api/'):
            return None
        if request.method == 'OPTIONS':
            return None

        api_key = get_settings().resolved_web_api_key()
        if not api_key:
            return jsonify({
                'status': 'error',
                'message': 'API Key 未配置，请设置 WEB_API_KEY'
            }), 503

        token = _extract_api_key()
        if token and hmac.compare_digest(token, api_key):
            return None
        return jsonify({
            'status': 'error',
            'message': 'API Key 无效或未提供'
        }), 401


def validate_request(model_class):
    """
    请求验证装饰器，使用 Pydantic 模型验证请求体

    用法：
        @validate_request(AddSubscriptionRequest)
        def my_endpoint(validated_data: AddSubscriptionRequest):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            data = request.get_json(silent=True)
            if data is None:
                return jsonify({
                    'status': 'error',
                    'message': '请求体必须是有效的 JSON'
                }), 400

            try:
                validated_data = model_class(**data)
            except ValidationError as e:
                errors = [
                    f"{' -> '.join(str(loc) for loc in error['loc'])}: {error['msg']}"
                    for error in e.errors()
                ]
                return jsonify({'status': 'error', 'errors': errors}), 400
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'验证失败: {str(e)}'}), 400

            return f(validated_data=validated_data, *args, **kwargs)
        return decorated
    return decorator
