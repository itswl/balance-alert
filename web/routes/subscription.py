#!/usr/bin/env python3
"""
订阅管理 API 路由

包含订阅的增删改查、标记续费等功能
"""
from flask import Blueprint, jsonify, request
from datetime import date, datetime
from ..middleware import validate_request
from ..utils import load_config_safe, audit_log
from core.config_loader import clear_config_cache
from services.config_service import delete_subscription, upsert_subscription
from ..handlers import refresh_subscription_cache
from core.state_manager import StateManager
from core.config_loader import get_default_config_path
from models.api_models import (
    AddSubscriptionRequest,
    UpdateSubscriptionRequest,
    DeleteSubscriptionRequest
)
from core.logger import get_logger

logger = get_logger('web.routes.subscription')

def create_subscription_bp(state_manager: StateManager) -> Blueprint:
    subscription_bp = Blueprint('subscription', __name__, url_prefix='/api')

    def _error(message: str, status_code: int = 500):
        return jsonify({'status': 'error', 'message': message}), status_code

    def _success(payload: dict, status_code: int = 200):
        return jsonify(payload), status_code

    def _refresh_cache() -> None:
        refresh_subscription_cache(get_default_config_path(), state_manager)

    def _clear_config_cache_if(success: bool) -> None:
        if success:
            clear_config_cache()

    def _get_name_from_json():
        data = request.get_json()
        if not data or 'name' not in data:
            return None, _error('缺少订阅名称', 400)
        return data['name'], None

    @subscription_bp.route('/subscriptions')
    def get_subscriptions():
        """获取订阅状态数据"""
        from ..utils import make_etag_response
        return make_etag_response(state_manager.get_subscription_state())

    @subscription_bp.route('/config/subscriptions', methods=['GET'])
    def get_subscriptions_config():
        """获取所有订阅配置（不含状态）"""
        try:
            config = load_config_safe()
            subscriptions = config.get('subscriptions', [])
            return jsonify({'status': 'success', 'subscriptions': subscriptions})
        except Exception as e:
            logger.error(f"获取订阅配置失败: {e}", exc_info=True)
            return _error(str(e), 500)

    @subscription_bp.route('/config/subscription', methods=['POST'])
    @validate_request(UpdateSubscriptionRequest)
    def update_subscription(validated_data: UpdateSubscriptionRequest):
        """更新订阅配置"""
        try:
            config = load_config_safe()

            subscription_found = False
            updated_fields = []

            for sub in config.get('subscriptions', []):
                if sub.get('name') == validated_data.name:
                    subscription_found = True
                    dyn_sub = sub.copy()

                    if validated_data.new_name:
                        dyn_sub['name'] = validated_data.new_name
                        updated_fields.append('name')
                        delete_subscription(validated_data.name)

                    if validated_data.cycle_type is not None:
                        dyn_sub['cycle_type'] = validated_data.cycle_type
                        updated_fields.append('cycle_type')

                    if 'owner_project' in validated_data.model_fields_set:
                        dyn_sub['owner_project'] = validated_data.owner_project
                        updated_fields.append('owner_project')

                    if validated_data.renewal_day is not None:
                        dyn_sub['renewal_day'] = validated_data.renewal_day
                        updated_fields.append('renewal_day')

                    if validated_data.alert_days_before is not None:
                        dyn_sub['alert_days_before'] = validated_data.alert_days_before
                        updated_fields.append('alert_days_before')

                    if validated_data.amount is not None:
                        dyn_sub['amount'] = validated_data.amount
                        updated_fields.append('amount')

                    if validated_data.enabled is not None:
                        dyn_sub['enabled'] = validated_data.enabled
                        updated_fields.append('enabled')

                    if validated_data.last_renewed_date is not None:
                        dyn_sub['last_renewed_date'] = validated_data.last_renewed_date
                        updated_fields.append('last_renewed_date')

                    success = upsert_subscription(dyn_sub)
                    _clear_config_cache_if(success)
                    break

            if not subscription_found:
                return _error(f'未找到订阅: {validated_data.name}', 404)

            audit_log('update_subscription', {
                'subscription': validated_data.name,
                'fields': updated_fields
            })

            _refresh_cache()

            return _success({
                'status': 'success',
                'message': f'订阅 [{validated_data.name}] 配置已更新',
                'updated_fields': updated_fields
            }, 200)

        except Exception as e:
            return _error(str(e), 500)

    @subscription_bp.route('/subscription/add', methods=['POST'])
    @validate_request(AddSubscriptionRequest)
    def add_subscription(validated_data: AddSubscriptionRequest):
        """添加新订阅"""
        try:
            config = load_config_safe()

            subscriptions = config.get('subscriptions', [])
            for sub in subscriptions:
                if sub.get('name') == validated_data.name:
                    return _error(f'订阅名称 [{validated_data.name}] 已存在', 400)

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

            success = upsert_subscription(new_subscription)
            _clear_config_cache_if(success)

            audit_log('add_subscription', {
                'subscription': validated_data.name,
                'cycle_type': validated_data.cycle_type,
                'amount': validated_data.amount
            })

            _refresh_cache()

            return _success({
                'status': 'success',
                'message': f'订阅 [{validated_data.name}] 已成功添加'
            }, 200)

        except Exception as e:
            return _error(str(e), 500)

    @subscription_bp.route('/subscription/delete', methods=['POST', 'DELETE'])
    @validate_request(DeleteSubscriptionRequest)
    def delete_subscription_route(validated_data: DeleteSubscriptionRequest):
        """删除订阅"""
        try:
            config = load_config_safe()
            subscriptions = config.get('subscriptions', [])
            if not any(sub.get('name') == validated_data.name for sub in subscriptions):
                return _error(f'未找到订阅: {validated_data.name}', 404)

            success = delete_subscription(validated_data.name)
            _clear_config_cache_if(success)

            audit_log('delete_subscription', {'subscription': validated_data.name})
            _refresh_cache()

            return _success({
                'status': 'success',
                'message': f'订阅 [{validated_data.name}] 已删除'
            }, 200)

        except Exception as e:
            return _error(str(e), 500)

    @subscription_bp.route('/subscription/mark_renewed', methods=['POST'])
    def mark_subscription_renewed():
        """标记订阅已续费"""
        try:
            subscription_name, error_response = _get_name_from_json()
            if error_response:
                return error_response

            data = request.get_json() or {}
            renewed_date = data.get('renewed_date')

            success = upsert_subscription({
                'name': subscription_name,
                'last_renewed_date': renewed_date or date.today().isoformat()
            })

            if not success:
                return _error('更新订阅失败', 500)

            clear_config_cache()
            audit_log('mark_renewed', {'subscription': subscription_name})
            _refresh_cache()

            config = load_config_safe()

            from ..handlers import calculate_next_renewal_date
            sub_data = next(s for s in config['subscriptions'] if s['name'] == subscription_name)
            next_renewal = calculate_next_renewal_date(
                sub_data['cycle_type'],
                sub_data['renewal_day'],
                datetime.fromisoformat(sub_data['last_renewed_date'])
            )

            return _success({
                'status': 'success',
                'message': f'订阅 [{subscription_name}] 已标记为已续费',
                'next_renewal_date': next_renewal.isoformat()
            }, 200)

        except Exception as e:
            logger.error(f"标记续费失败: {e}", exc_info=True)
            return _error(str(e), 500)

    @subscription_bp.route('/subscription/clear_renewed', methods=['POST'])
    def clear_subscription_renewed():
        """清除订阅的续费标记"""
        try:
            subscription_name, error_response = _get_name_from_json()
            if error_response:
                return error_response

            success = upsert_subscription({
                'name': subscription_name,
                'last_renewed_date': None
            })

            if not success:
                return _error('更新订阅失败', 500)

            clear_config_cache()
            audit_log('unmark_renewed', {'subscription': subscription_name})
            _refresh_cache()

            return _success({
                'status': 'success',
                'message': f'订阅 [{subscription_name}] 的续费标记已清除'
            }, 200)

        except Exception as e:
            logger.error(f"清除续费标记失败: {e}", exc_info=True)
            return _error(str(e), 500)

    return subscription_bp
