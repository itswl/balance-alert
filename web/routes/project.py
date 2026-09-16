#!/usr/bin/env python3
"""
项目配置 API 路由

读接口始终可用（密钥脱敏）；增删改需要 ENABLE_DYNAMIC_CONFIG，否则统一返回 503。
配好动态配置后，项目清单可以完全在页面上维护，不再需要 config.json。
"""
from flask import Blueprint, request

from core.config_loader import get_default_config_path
from core.logger import get_logger
from core.settings import get_settings
from services.monitor import run_credit_monitor
from services.prometheus_exporter import metrics_collector
from ..middleware import validate_request
from ..schemas import DeleteByNameRequest, ProjectConfigRequest
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
    runtime,
)

logger = get_logger('web.routes.project')

project_bp = Blueprint('project', __name__, url_prefix='/api')

SECTION = 'projects'


@project_bp.before_request
def _require_dynamic_config_for_writes():
    if request.method in ('GET', 'OPTIONS'):
        return None
    if not get_settings().enable_dynamic_config:
        return json_error('修改项目配置需要数据库动态配置，请设置 ENABLE_DYNAMIC_CONFIG=true', 503)
    return None


def _projects():
    return load_config_safe().get('projects', []) or []


def _find(name: str):
    return next((p for p in _projects() if p.get('name') == name), None)


def _refresh_one(name: str) -> None:
    """只重查这一个项目并合并进看板状态，避免把所有上游都打一遍"""
    try:
        result = run_credit_monitor(get_default_config_path(), name, dry_run=not get_settings().enable_web_alarm)
        if result.get('success'):
            state_manager = runtime().state_manager
            state_manager.merge_balance_state(result.get('results') or [])
            metrics_collector.update_balance_metrics(state_manager.get_balance_state()['projects'])
    except Exception as e:
        logger.warning(f"刷新项目 {name} 失败: {e}")


@project_bp.route('/providers', methods=['GET'])
@handle_errors('获取平台列表')
def get_providers():
    """支持的平台清单，供页面的下拉框使用"""
    from core.config_loader import PROVIDER_DEFAULT_TYPE
    from providers import PROVIDERS

    return make_etag_response({'status': 'success', 'providers': [
        {'value': key, 'label': cls.get_provider_name(), 'default_type': PROVIDER_DEFAULT_TYPE.get(key, 'balance')}
        for key, cls in sorted(PROVIDERS.items())
    ]})


@project_bp.route('/config/projects', methods=['GET'])
@handle_errors('获取项目配置')
def get_projects_config():
    """所有项目配置，密钥脱敏"""
    return make_etag_response({'status': 'success', 'projects': [mask_project_config(p) for p in _projects()]})


@project_bp.route('/config/project', methods=['POST'])
@validate_request(ProjectConfigRequest)
@handle_errors('保存项目配置')
def save_project(validated_data: ProjectConfigRequest):
    """添加或更新项目。新增时 provider 与 api_key 必填；更新时只改传了的字段。"""
    name = validated_data.name
    existing = _find(name)
    is_new = existing is None

    payload = {k: v for k, v in validated_data.model_dump().items() if v is not None}
    if not payload.get('api_key'):
        payload.pop('api_key', None)
    if is_new:
        missing = [f for f in ('provider', 'api_key') if not payload.get(f)]
        if missing:
            return json_error(f"新增项目缺少必要参数: {', '.join(missing)}", 400)
    elif existing.get('from_env'):
        # 环境变量自动发现的项目，在这里改动等于把它固化进数据库
        payload.setdefault('provider', existing.get('provider'))

    if not config_db_write(lambda repo: repo.upsert(SECTION, payload)):
        return json_error('保存失败', 500)

    audit_log('save_project', {'project': name, 'new': is_new, 'fields': sorted(payload)})
    _refresh_one(name)
    return json_success({'status': 'success', 'message': f"项目 [{name}] 已{'添加' if is_new else '更新'}"}, 200)


@project_bp.route('/config/project/delete', methods=['POST'])
@validate_request(DeleteByNameRequest)
@handle_errors('删除项目配置')
def delete_project(validated_data: DeleteByNameRequest):
    """删除项目；环境变量自动发现的项目删不掉，得先去掉对应的环境变量"""
    name = validated_data.name
    existing = _find(name)
    if existing is None:
        return json_error(f'未找到项目: {name}', 404)
    if existing.get('from_env'):
        return json_error(f'项目 [{name}] 来自环境变量自动发现，请移除对应的 {existing.get("provider", "").upper()}_API_KEY 后重启', 400)

    if not config_db_write(lambda repo: repo.delete(SECTION, name)):
        return json_error('删除失败', 500)

    runtime().state_manager.remove_balance_project(name)
    audit_log('delete_project', {'project': name})
    return json_success({'status': 'success', 'message': f'项目 [{name}] 已删除'}, 200)


@project_bp.route('/config/threshold', methods=['POST'])
@handle_errors('更新项目阈值')
def update_project_threshold():
    """只改阈值的快捷入口，保留给旧的调用方"""
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

    target = _find(project_name)
    if target is None:
        return json_error(f'未找到项目: {project_name}', 404)

    old_threshold = target.get('threshold')
    config_db_write(lambda repo: repo.upsert(SECTION, {
        'name': project_name, 'provider': target.get('provider'),
        'api_key': target.get('api_key'), 'threshold': new_threshold,
        'type': target.get('type'), 'owner_project': target.get('owner_project'),
        'enabled': target.get('enabled', True),
    }))

    audit_log('update_project_threshold', {
        'project': project_name, 'old_threshold': old_threshold, 'new_threshold': new_threshold,
    })
    _refresh_one(project_name)
    return json_success({'status': 'success', 'message': f'项目 [{project_name}] 阈值已更新为 {new_threshold}'}, 200)
