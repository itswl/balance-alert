#!/usr/bin/env python3
"""
Flask 应用工厂

创建和配置 Flask 应用实例
"""
import os
from flask import Flask
from flask_cors import CORS
from pathlib import Path
from state_manager import StateManager
from logger import get_logger

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

    # 启用 CORS
    CORS(app)

    # 初始化状态管理器
    if state_manager is None:
        state_manager = StateManager()

    # 注册蓝图
    _register_blueprints(app, state_manager)

    # 注册剩余路由（历史数据、配置等）
    _register_additional_routes(app, state_manager)

    logger.info("Flask 应用创建完成")

    return app


def _register_blueprints(app: Flask, state_manager: StateManager):
    """
    注册所有蓝图

    Args:
        app: Flask 应用实例
        state_manager: 状态管理器实例
    """
    from .routes import core_bp, subscription_bp, init_core_routes, init_subscription_routes

    # 初始化路由（注入依赖）
    init_core_routes(state_manager)
    init_subscription_routes(state_manager)

    # 注册蓝图
    app.register_blueprint(core_bp)
    app.register_blueprint(subscription_bp)

    logger.info("蓝图注册完成")


def _register_additional_routes(app: Flask, state_manager: StateManager):
    """
    注册额外的路由（历史数据、配置等）

    这些路由暂时保留为函数形式，未来可以重构为蓝图

    Args:
        app: Flask 应用实例
        state_manager: 状态管理器实例
    """
    from flask import jsonify, request
    from .middleware import require_api_key
    from .utils import load_config_safe, write_config, audit_log
    from .handlers import update_balance_cache, refresh_credits

    # ==========推历史数据 API ==========
    try:
        from database import init_database
        from database.repository import BalanceRepository, AlertRepository
        DB_AVAILABLE = True
        logger.info("数据库模块可用")
    except (ImportError, Exception) as e:
        DB_AVAILABLE = False
        logger.warning(f"数据库模块不可用: {e}")

    @app.route('/api/history/balance', methods=['GET'])
    @require_api_key
    def get_balance_history():
        """查询余额历史"""
        if not DB_AVAILABLE:
            return jsonify({'status': 'error', 'message': '数据库功能未启用'}), 503

        try:
            project_id = request.args.get('project_id')
            provider = request.args.get('provider')
            days = int(request.args.get('days', 7))
            limit = int(request.args.get('limit', 100))

            if days < 1 or days > 365:
                return jsonify({'status': 'error', 'message': 'days 必须在 1-365 之间'}), 400
            if limit < 1 or limit > 1000:
                return jsonify({'status': 'error', 'message': 'limit 必须在 1-1000 之间'}), 400

            history = BalanceRepository.get_balance_history(
                project_id=project_id,
                provider=provider,
                days=days,
                limit=limit
            )

            return jsonify({'status': 'success', 'count': len(history), 'data': history})

        except ValueError as e:
            return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
        except Exception as e:
            logger.error(f"查询余额历史失败: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/history/trend/<project_id>', methods=['GET'])
    @require_api_key
    def get_balance_trend(project_id: str):
        """获取余额趋势分析"""
        if not DB_AVAILABLE:
            return jsonify({'status': 'error', 'message': '数据库功能未启用'}), 503

        try:
            days = int(request.args.get('days', 30))
            if days < 1 or days > 365:
                return jsonify({'status': 'error', 'message': 'days 必须在 1-365 之间'}), 400

            trend = BalanceRepository.get_balance_trend(project_id, days)
            if 'error' in trend:
                return jsonify({'status': 'error', 'message': trend['error']}), 404

            return jsonify({'status': 'success', 'data': trend})

        except ValueError as e:
            return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
        except Exception as e:
            logger.error(f"获取余额趋势失败: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/history/alerts', methods=['GET'])
    @require_api_key
    def get_alert_history():
        """查询告警历史"""
        if not DB_AVAILABLE:
            return jsonify({'status': 'error', 'message': '数据库功能未启用'}), 503

        try:
            project_id = request.args.get('project_id')
            alert_type = request.args.get('alert_type')
            days = int(request.args.get('days', 7))
            limit = int(request.args.get('limit', 50))

            if days < 1 or days > 365:
                return jsonify({'status': 'error', 'message': 'days 必须在 1-365 之间'}), 400
            if limit < 1 or limit > 1000:
                return jsonify({'status': 'error', 'message': 'limit 必须在 1-1000 之间'}), 400

            alerts = AlertRepository.get_recent_alerts(
                project_id=project_id,
                alert_type=alert_type,
                days=days,
                limit=limit
            )

            return jsonify({'status': 'success', 'count': len(alerts), 'data': alerts})

        except ValueError as e:
            return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
        except Exception as e:
            logger.error(f"查询告警历史失败: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/history/stats', methods=['GET'])
    @require_api_key
    def get_alert_statistics():
        """获取告警统计"""
        if not DB_AVAILABLE:
            return jsonify({'status': 'error', 'message': '数据库功能未启用'}), 503

        try:
            days = int(request.args.get('days', 30))
            if days < 1 or days > 365:
                return jsonify({'status': 'error', 'message': 'days 必须在 1-365 之间'}), 400

            stats = AlertRepository.get_alert_statistics(days)
            if 'error' in stats:
                return jsonify({'status': 'error', 'message': stats['error']}), 500

            return jsonify({'status': 'success', 'data': stats})

        except ValueError as e:
            return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
        except Exception as e:
            logger.error(f"获取告警统计失败: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/history/projects', methods=['GET'])
    @require_api_key
    def get_all_projects_summary():
        """获取所有项目摘要"""
        if not DB_AVAILABLE:
            return jsonify({'status': 'error', 'message': '数据库功能未启用'}), 503

        try:
            summary = BalanceRepository.get_all_projects_summary()
            return jsonify({'status': 'success', 'count': len(summary), 'data': summary})

        except Exception as e:
            logger.error(f"获取项目摘要失败: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # ========== 配置 API ==========

    @app.route('/api/config/projects', methods=['GET'])
    def get_projects_config():
        """获取所有项目配置（不含API Key）"""
        try:
            config = load_config_safe()
            projects = []

            for proj in config.get('projects', []):
                # 移除敏感信息
                safe_proj = {
                    'name': proj.get('name'),
                    'provider': proj.get('provider'),
                    'threshold': proj.get('threshold'),
                    'type': proj.get('type', 'credits'),
                    'enabled': proj.get('enabled', True)
                }
                projects.append(safe_proj)

            return jsonify({'status': 'success', 'projects': projects})

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/api/config/threshold', methods=['POST'])
    @require_api_key
    def update_threshold():
        """更新项目告警阈值"""
        try:
            data = request.get_json()
            if not data or 'project_name' not in data or 'new_threshold' not in data:
                return jsonify({
                    'status': 'error',
                    'message': '缺少必要参数: project_name, new_threshold'
                }), 400

            project_name = data['project_name']
            new_threshold = float(data['new_threshold'])

            if new_threshold < 0:
                return jsonify({'status': 'error', 'message': '阈值必须大于等于 0'}), 400

            # 读取配置
            config = load_config_safe()
            project_found = False
            old_threshold = None

            for proj in config.get('projects', []):
                if proj.get('name') == project_name:
                    old_threshold = proj.get('threshold')
                    proj['threshold'] = new_threshold
                    project_found = True
                    break

            if not project_found:
                return jsonify({'status': 'error', 'message': f'未找到项目: {project_name}'}), 404

            # 保存配置
            write_config(config)
            audit_log('update_threshold', {
                'project': project_name,
                'old': old_threshold,
                'new': new_threshold
            })

            # 刷新缓存
            result = refresh_credits('config.json', project_name, dry_run=True)
            if result['success']:
                update_balance_cache(result['results'], state_manager)

            return jsonify({
                'status': 'success',
                'message': f'项目 [{project_name}] 阈值已更新: {old_threshold} -> {new_threshold}',
                'data': {
                    'project_name': project_name,
                    'old_threshold': old_threshold,
                    'new_threshold': new_threshold
                }
            })

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    logger.info("额外路由注册完成")


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
