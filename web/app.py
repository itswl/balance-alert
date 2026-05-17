#!/usr/bin/env python3
"""
Flask 应用工厂

创建和配置 Flask 应用实例
"""
import os
from flask import Flask
from pathlib import Path
from core.state_manager import StateManager
from core.logger import get_logger

logger = get_logger('web.app')

# 请求体大小限制 (1MB)
MAX_CONTENT_LENGTH = 1 * 1024 * 1024


def create_app(state_manager: StateManager = None) -> Flask:
    """
    创建 Flask 应用实例

    Args:
        state_manager: 状态管理器实例（可选，默认创建新实例）

    Returns:
        配置好的 Flask 应用
    """
    # 确定静态文件和模板目录
    base_dir = Path(__file__).parent.parent
    static_folder = base_dir / 'static'
    template_folder = base_dir / 'templates'

    # 创建 Flask 应用
    app = Flask(
        __name__,
        static_folder=str(static_folder),
        template_folder=str(template_folder)
    )

    # 配置
    app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
    app.config['JSON_AS_ASCII'] = False  # 支持中文JSON
    app.config['JSON_SORT_KEYS'] = False  # 保持JSON键顺序

    # 按需启用 CORS；同源前端无需开启，生产环境建议通过 CORS_ORIGINS 白名单控制。
    if os.environ.get('WEB_ENABLE_CORS', 'false').lower() == 'true':
        try:
            from flask_cors import CORS
        except ImportError:
            logger.warning("WEB_ENABLE_CORS=true 但未安装 flask-cors，已跳过 CORS 开启")
            CORS = None

        raw_origins = os.environ.get('CORS_ORIGINS', '')
        origins = [origin.strip() for origin in raw_origins.split(',') if origin.strip()]
        if CORS and origins:
            CORS(app, origins=origins)
        elif CORS:
            logger.warning("WEB_ENABLE_CORS=true 但未设置 CORS_ORIGINS，已跳过 CORS 开启")

    from .middleware import protect_api_endpoints
    protect_api_endpoints(app)

    # 初始化状态管理器
    if state_manager is None:
        state_manager = StateManager()

    # 注册蓝图
    _register_blueprints(app, state_manager)
    _register_error_handlers(app)

    logger.info("Flask 应用创建完成")

    return app


def _register_blueprints(app: Flask, state_manager: StateManager):
    """
    注册所有蓝图

    Args:
        app: Flask 应用实例
        state_manager: 状态管理器实例
    """
    if os.environ.get('ENABLE_SUBSCRIPTIONS', 'false').lower() == 'true':
        from .routes import create_subscription_bp
        app.register_blueprint(create_subscription_bp(state_manager))

    if os.environ.get('ENABLE_DYNAMIC_CONFIG', 'false').lower() == 'true':
        from .routes import project_bp, email_bp
        app.register_blueprint(project_bp)
        app.register_blueprint(email_bp)

    if os.environ.get('ENABLE_HISTORY_API', 'false').lower() == 'true':
        from .routes import history_bp
        app.register_blueprint(history_bp)

    from .routes import create_core_bp
    app.register_blueprint(create_core_bp(state_manager))

    logger.info("蓝图注册完成")


def _register_error_handlers(app: Flask):
    """注册错误处理器"""
    from flask import jsonify

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'status': 'error', 'message': '未找到资源'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'status': 'error', 'message': '服务器内部错误'}), 500

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({'status': 'error', 'message': '请求体过大'}), 413
