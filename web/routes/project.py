#!/usr/bin/env python3
"""
项目配置管理 API 路由

包含项目的配置更新功能
"""
from flask import Blueprint

from core.config_loader import clear_config_cache
from ..utils import (
    audit_log,
    config_db_write,
    handle_errors,
    json_error,
    json_success,
    load_config_safe,
    make_etag_response,
    mask_project_config,
    require_json_fields,
)

project_bp = Blueprint('project', __name__, url_prefix='/api')


@project_bp.route('/config/projects', methods=['GET'])
@handle_errors('获取项目配置')
def get_projects_config():
    """获取所有项目配置"""
    projects = [mask_project_config(p) for p in load_config_safe().get('projects', [])]
    return make_etag_response({'status': 'success', 'projects': projects})


@project_bp.route('/config/threshold', methods=['POST'])
@handle_errors('更新项目阈值')
def update_project_threshold():
    """更新项目阈值"""
    data, error_resp = require_json_fields('project_name', 'new_threshold')
    if error_resp:
        return error_resp

    project_name = data['project_name']
    try:
        new_threshold = float(data['new_threshold'])
    except (TypeError, ValueError):
        return json_error('阈值必须是有效的数字', 400)

    if new_threshold < 0:
        return json_error('阈值不能为负数', 400)

    target_project = next(
        (p.copy() for p in load_config_safe().get('projects', []) if p.get('name') == project_name),
        None,
    )
    if target_project is None:
        return json_error(f'未找到项目: {project_name}', 404)

    old_threshold = target_project.get('threshold', 0)
    target_project['threshold'] = new_threshold

    if config_db_write(lambda repo: repo.upsert_project(target_project)):
        clear_config_cache()

    audit_log('update_project_threshold', {
        'project': project_name,
        'old_threshold': old_threshold,
        'new_threshold': new_threshold,
    })

    return json_success({
        'status': 'success',
        'message': f'项目 [{project_name}] 阈值已更新为 {new_threshold}'
    }, 200)
