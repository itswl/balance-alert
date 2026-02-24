#!/usr/bin/env python3
"""
认证和速率限制中间件

提供 JWT 认证和 API 速率限制功能
"""
import os
from datetime import timedelta
from functools import wraps
from flask import request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from logger import get_logger

logger = get_logger('auth_middleware')

# JWT 配置
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.environ.get('JWT_ACCESS_TOKEN_EXPIRES_HOURS', '24')))

# 是否启用 JWT 认证（默认使用简单 API Key）
ENABLE_JWT = os.environ.get('ENABLE_JWT', 'false').lower() == 'true'

# API Key 认证（向后兼容）
API_KEY = os.environ.get('API_KEY', '')

# 速率限制配置
ENABLE_RATE_LIMIT = os.environ.get('ENABLE_RATE_LIMIT', 'true').lower() == 'true'
RATE_LIMIT_STORAGE = os.environ.get('RATE_LIMIT_STORAGE', 'memory://') # memory:// 或 redis://localhost:6379


def init_jwt(app):
    """初始化 JWT"""
    app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = JWT_ACCESS_TOKEN_EXPIRES
    
    jwt = JWTManager(app)
    
    @jwt.unauthorized_loader
    def unauthorized_callback(callback):
        return jsonify({
            'status': 'error',
            'message': '缺少或无效的访问令牌'
        }), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(callback):
        return jsonify({
            'status': 'error',
            'message': '令牌无效或已过期'
        }), 401
    
    logger.info(f"JWT 认证已初始化 (启用: {ENABLE_JWT}, 令牌有效期: {JWT_ACCESS_TOKEN_EXPIRES})")
    return jwt


def init_rate_limiter(app):
    """初始化速率限制器"""
    if not ENABLE_RATE_LIMIT:
        logger.info("速率限制已禁用")
        return None
    
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        storage_uri=RATE_LIMIT_STORAGE,
        default_limits=["500 per day", "100 per hour"],  # 全局默认限制
        headers_enabled=True  # 在响应头中包含限制信息
    )
    
    logger.info(f"速率限制已初始化 (存储: {RATE_LIMIT_STORAGE})")
    return limiter


def require_api_key(f):
    """
    API Key 认证装饰器（向后兼容）
    
    用法：
        @require_api_key
        def my_endpoint():
            return {...}
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # 如果启用了 JWT，使用 JWT 认证
        if ENABLE_JWT:
            # JWT 认证由 @jwt_required() 处理，这里直接放行
            return f(*args, **kwargs)
        
        # 使用简单 API Key 认证
        if not API_KEY:
            # 未配置 API Key，直接放行
            return f(*args, **kwargs)
        
        # 从 Header 或 Query 参数获取 token
        token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
        if not token:
            token = request.args.get('api_key', '')
        
        if token != API_KEY:
            return jsonify({
                'status': 'error',
                'message': '未授权访问'
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated


def require_auth(f):
    """
    统一认证装饰器（支持 JWT 和 API Key）
    
    优先级：
    1. 如果启用 JWT，使用 JWT 认证
    2. 否则使用 API Key 认证
    
    用法：
        @require_auth
        def my_endpoint():
            # 可以使用 get_current_user() 获取当前用户
            return {...}
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if ENABLE_JWT:
            # 使用 JWT 认证
            return jwt_required()(f)(*args, **kwargs)
        else:
            # 使用 API Key 认证
            return require_api_key(f)(*args, **kwargs)
    
    return decorated


def get_current_user():
    """
    获取当前认证用户
    
    Returns:
        str: 用户标识（JWT identity 或 'api_key_user'）
    """
    if ENABLE_JWT:
        try:
            return get_jwt_identity()
        except Exception:
            return None
    else:
        return 'api_key_user'


def generate_token(username, password):
    """
    生成访问令牌（用于登录接口）
    
    Args:
        username: 用户名
        password: 密码
    
    Returns:
        tuple: (access_token, expires_in_seconds) 或 (None, None) 如果认证失败
    """
    # 从环境变量验证用户凭证
    valid_username = os.environ.get('AUTH_USERNAME', 'admin')
    valid_password = os.environ.get('AUTH_PASSWORD', 'admin')
    
    if username == valid_username and password == valid_password:
        access_token = create_access_token(identity=username)
        expires_in = int(JWT_ACCESS_TOKEN_EXPIRES.total_seconds())
        return access_token, expires_in
    
    return None, None


# 导出
__all__ = [
    'init_jwt',
    'init_rate_limiter',
    'require_api_key',
    'require_auth',
    'get_current_user',
    'generate_token',
    'ENABLE_JWT',
    'ENABLE_RATE_LIMIT',
]
