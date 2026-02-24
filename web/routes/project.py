#!/usr/bin/env python3
"""
项目配置管理 API 路由

包含项目的配置更新功能
"""
from flask import Blueprint, jsonify, request
from ..middleware import require_api_key
from ..utils import load_config_safe, write_config, audit_log
from ..handlers import refresh_subscription_cache
from state_manager import StateManager
from logger import get_logger

logger = get_logger('web.routes.project')

# 创建蓝图
project_bp = Blueprint('project', __name__, url_prefix='/api')

# 全局状态管理器（需要从外部注入）
_state_manager: StateManager = None


def init_project_routes(state_mgr: StateManager):
    """
    初始化项目路由（注入依赖）

    Args:
        state_mgr: 状态管理器实例
    """
    global _state_manager
    _state_manager = state_mgr


@project_bp.route('/config/projects', methods=['GET'])
def get_projects_config():
    """获取所有项目配置"""
    try:
        config = load_config_safe()
        projects = config.get('projects', [])
        return jsonify({'status': 'success', 'projects': projects})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@project_bp.route('/project/update_threshold', methods=['POST'])
@require_api_key
def update_project_threshold():
    """更新项目阈值"""
    try:
        data = request.get_json()
        if not data or 'name' not in data or 'threshold' not in data:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: name 和 threshold'
            }), 400

        project_name = data['name']
        new_threshold = float(data['threshold'])

        if new_threshold < 0:
            return jsonify({
                'status': 'error',
                'message': '阈值不能为负数'
            }), 400

        # 读取配置文件
        config = load_config_safe()

        # 查找项目
        project_found = False
        for project in config.get('projects', []):
            if project.get('name') == project_name:
                old_threshold = project.get('threshold', 0)
                project['threshold'] = new_threshold
                project_found = True
                break

        if not project_found:
            return jsonify({
                'status': 'error',
                'message': f'未找到项目: {project_name}'
            }), 404

        # 保存配置文件
        write_config(config)
        audit_log('update_project_threshold', {
            'project': project_name,
            'old_threshold': old_threshold,
            'new_threshold': new_threshold
        })

        return jsonify({
            'status': 'success',
            'message': f'项目 [{project_name}] 阈值已更新为 {new_threshold}'
        })

    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': '阈值必须是有效的数字'
        }), 400
    except Exception as e:
        logger.error(f"更新项目阈值失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500
