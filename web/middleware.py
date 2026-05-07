#!/usr/bin/env python3
"""
Web 中间件

提供请求验证等装饰器
"""
from functools import wraps
from flask import request, jsonify
from pydantic import ValidationError


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
