#!/usr/bin/env python3
"""
订阅管理 API 路由：增删改查、标记 / 取消续费。
订阅功能未启用时，本蓝图所有端点统一返回 503。
"""
from datetime import date, datetime

from flask import Blueprint, request

from core.logger import get_logger
from core.settings import get_settings
from services.prometheus_exporter import metrics_collector
from services.subscription_checker import SubscriptionChecker, calculate_next_renewal_date
from ..middleware import validate_request
from ..schemas import AddSubscriptionRequest, DeleteSubscriptionRequest, UpdateSubscriptionRequest
from ..utils import (
    audit_log,
    config_db_write,
    handle_errors,
    json_error,
    json_success,
    load_config_safe,
    make_etag_response,
    require_json_fields,
    runtime,
)

logger = get_logger('web.routes.subscription')

subscription_bp = Blueprint('subscription', __name__, url_prefix='/api')

SECTION = 'subscriptions'
UPDATABLE_FIELDS = ('cycle_type', 'renewal_day', 'alert_days_before', 'amount', 'enabled', 'last_renewed_date')


@subscription_bp.before_request
def _require_enabled():
    if request.method == 'OPTIONS':
        return None
    if not get_settings().enable_subscriptions:
        return json_error('订阅功能未启用，请设置 ENABLE_SUBSCRIPTIONS=true', 503)
    return None


def _refresh_state() -> None:
    """配置变化后重新检查订阅，更新看板状态与指标；是否真发告警与看板刷新同一开关"""
    try:
        checker = SubscriptionChecker()
        results = checker.check_subscriptions(dry_run=not get_settings().enable_web_alarm) or []
        runtime().state_manager.update_subscription_state(results)
        metrics_collector.update_subscription_metrics(results)
    except Exception as e:
        logger.error(f"刷新订阅状态失败: {e}", exc_info=True)


def _find_subscription(name: str):
    return next((s for s in load_config_safe().get('subscriptions', []) if s.get('name') == name), None)


@subscription_bp.route('/config/subscriptions', methods=['GET'])
@handle_errors('获取订阅配置')
def get_subscriptions_config():
    """所有订阅配置（不含运行状态）"""
    return make_etag_response({'status': 'success', 'subscriptions': load_config_safe().get('subscriptions', [])})


@subscription_bp.route('/config/subscription', methods=['POST'])
@validate_request(UpdateSubscriptionRequest)
@handle_errors('更新订阅配置')
def update_subscription(validated_data: UpdateSubscriptionRequest):
    """更新订阅：只改传了的字段；改名时先删旧名再按新名写入"""
    current = _find_subscription(validated_data.name)
    if current is None:
        return json_error(f'未找到订阅: {validated_data.name}', 404)

    updated = dict(current)
    changed = []
    if validated_data.new_name:
        updated['name'] = validated_data.new_name
        changed.append('name')
        config_db_write(lambda repo: repo.delete(SECTION, validated_data.name))
    for field in UPDATABLE_FIELDS:
        value = getattr(validated_data, field)
        if value is not None:
            updated[field] = value
            changed.append(field)
    if 'owner_project' in validated_data.model_fields_set:
        updated['owner_project'] = validated_data.owner_project
        changed.append('owner_project')

    config_db_write(lambda repo: repo.upsert(SECTION, updated))
    audit_log('update_subscription', {'subscription': validated_data.name, 'fields': changed})
    _refresh_state()
    return json_success({
        'status': 'success',
        'message': f'订阅 [{validated_data.name}] 配置已更新',
        'updated_fields': changed,
    }, 200)


@subscription_bp.route('/subscription/add', methods=['POST'])
@validate_request(AddSubscriptionRequest)
@handle_errors('添加订阅')
def add_subscription(validated_data: AddSubscriptionRequest):
    """添加新订阅"""
    if _find_subscription(validated_data.name) is not None:
        return json_error(f'订阅名称 [{validated_data.name}] 已存在', 400)

    new_subscription = {
        'name': validated_data.name,
        'owner_project': validated_data.owner_project,
        'cycle_type': validated_data.cycle_type,
        'renewal_day': validated_data.renewal_day,
        'alert_days_before': validated_data.alert_days_before,
        'amount': validated_data.amount,
        'enabled': validated_data.enabled,
    }
    if validated_data.last_renewed_date:
        new_subscription['last_renewed_date'] = validated_data.last_renewed_date

    config_db_write(lambda repo: repo.upsert(SECTION, new_subscription))
    audit_log('add_subscription', {
        'subscription': validated_data.name,
        'cycle_type': validated_data.cycle_type,
        'amount': validated_data.amount,
    })
    _refresh_state()
    return json_success({'status': 'success', 'message': f'订阅 [{validated_data.name}] 已成功添加'}, 200)


@subscription_bp.route('/subscription/delete', methods=['POST', 'DELETE'])
@validate_request(DeleteSubscriptionRequest)
@handle_errors('删除订阅')
def delete_subscription_route(validated_data: DeleteSubscriptionRequest):
    """删除订阅"""
    if _find_subscription(validated_data.name) is None:
        return json_error(f'未找到订阅: {validated_data.name}', 404)

    config_db_write(lambda repo: repo.delete(SECTION, validated_data.name))
    audit_log('delete_subscription', {'subscription': validated_data.name})
    _refresh_state()
    return json_success({'status': 'success', 'message': f'订阅 [{validated_data.name}] 已删除'}, 200)


@subscription_bp.route('/subscription/mark_renewed', methods=['POST'])
@handle_errors('标记续费')
def mark_subscription_renewed():
    """标记订阅已续费（默认今天），返回下次续费日期"""
    data, error_response = require_json_fields('name')
    if error_response:
        return error_response
    name = data['name']
    renewed_date = data.get('renewed_date') or date.today().isoformat()

    if not config_db_write(lambda repo: repo.upsert(SECTION, {'name': name, 'last_renewed_date': renewed_date})):
        return json_error('更新订阅失败', 500)
    audit_log('mark_renewed', {'subscription': name})
    _refresh_state()

    sub = _find_subscription(name)
    if not sub:
        return json_error('未找到订阅配置', 404)
    next_renewal = calculate_next_renewal_date(
        sub['cycle_type'], sub['renewal_day'], datetime.fromisoformat(sub['last_renewed_date'])
    )
    return json_success({
        'status': 'success',
        'message': f'订阅 [{name}] 已标记为已续费',
        'next_renewal_date': next_renewal.isoformat(),
    }, 200)


@subscription_bp.route('/subscription/clear_renewed', methods=['POST'])
@handle_errors('清除续费标记')
def clear_subscription_renewed():
    """清除订阅的续费标记"""
    data, error_response = require_json_fields('name')
    if error_response:
        return error_response
    name = data['name']

    if not config_db_write(lambda repo: repo.upsert(SECTION, {'name': name, 'last_renewed_date': None})):
        return json_error('更新订阅失败', 500)
    audit_log('unmark_renewed', {'subscription': name})
    _refresh_state()
    return json_success({'status': 'success', 'message': f'订阅 [{name}] 的续费标记已清除'}, 200)
