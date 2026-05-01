#!/usr/bin/env python3
"""
Web 中间件

提供认证、验证等装饰器
"""
import os
from functools import wraps
from flask import request, jsonify
from pydantic import ValidationError


# API 认证配置
API_KEY = os.environ.get('API_KEY', '')


def _extract_api_key() -> str:
    token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    if not token:
        token = request.args.get('api_key', '')
    return token.strip()


def _unauthorized():
    return jsonify({'status': 'error', 'message': '未授权访问'}), 401


def validate_api_key_request() -> bool:
    if request.method == 'OPTIONS':
        return True
    token = _extract_api_key()
    return bool(API_KEY) and token == API_KEY


def protect_api_endpoints(app) -> None:
    @app.before_request
    def _api_key_guard():
        path = request.path or ''
        if not path.startswith('/api/'):
            return None
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
