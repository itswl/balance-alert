#!/usr/bin/env python3
"""
项目配置管理 API 路由

包含项目的配置更新功能
"""
from flask import Blueprint, jsonify, request
from ..utils import load_config_safe, audit_log, mask_project_config
from core.config_loader import clear_config_cache
from services.config_service import upsert_project
from core.logger import get_logger

logger = get_logger('web.routes.project')

# 创建蓝图
project_bp = Blueprint('project', __name__, url_prefix='/api')

def _error(message: str, status_code: int = 500):
    return jsonify({'status': 'error', 'message': message}), status_code


def _success(payload: dict, status_code: int = 200):
    return jsonify(payload), status_code


def _require_json_fields(*fields: str):
    data = request.get_json()
    if not data:
        return None, _error(f"缺少必要参数: {', '.join(fields)}", 400)
    missing = [f for f in fields if f not in data]
    if missing:
        return None, _error(f"缺少必要参数: {', '.join(missing)}", 400)
    return data, None



@project_bp.route('/config/projects', methods=['GET'])
def get_projects_config():
    """获取所有项目配置"""
    try:
        config = load_config_safe()
        projects = [mask_project_config(project) for project in config.get('projects', [])]
        return _success({'status': 'success', 'projects': projects}, 200)
    except Exception as e:
        logger.error(f"获取项目配置失败: {e}", exc_info=True)
        return _error(str(e), 500)


@project_bp.route('/config/threshold', methods=['POST'])
def update_project_threshold():
    """更新项目阈值"""
    try:
        data, error_resp = _require_json_fields('project_name', 'new_threshold')
        if error_resp:
            return error_resp

        project_name = data['project_name']
        new_threshold = float(data['new_threshold'])

        if new_threshold < 0:
            return _error('阈值不能为负数', 400)

        # 读取配置文件
        config = load_config_safe()

        # 查找项目
        project_found = False
        target_project = None
        for project in config.get('projects', []):
            if project.get('name') == project_name:
                old_threshold = project.get('threshold', 0)
                target_project = project.copy()
                target_project['threshold'] = new_threshold
                project_found = True
                break

        if not project_found:
            return _error(f'未找到项目: {project_name}', 404)

        # 保存到数据库
        success = upsert_project(target_project)
        
        if success:
            clear_config_cache()
            
        audit_log('update_project_threshold', {
            'project': project_name,
            'old_threshold': old_threshold,
            'new_threshold': new_threshold
        })

        return _success({
            'status': 'success',
            'message': f'项目 [{project_name}] 阈值已更新为 {new_threshold}'
        }, 200)

    except ValueError as e:
        return _error('阈值必须是有效的数字', 400)
    except Exception as e:
        logger.error(f"更新项目阈值失败: {e}", exc_info=True)
        return _error(str(e), 500)
