#!/usr/bin/env python3
"""
订阅管理 API 路由

包含订阅的增删改查、标记续费等功能
"""
from flask import Blueprint, jsonify, request
from ..middleware import validate_request
from ..utils import load_config_safe, audit_log
from core.config_loader import clear_config_cache
from services.config_service import delete_subscription, upsert_subscription
from ..handlers import refresh_subscription_cache
from core.state_manager import StateManager
from models.api_models import (
    AddSubscriptionRequest,
    UpdateSubscriptionRequest,
    DeleteSubscriptionRequest
)
from core.logger import get_logger

logger = get_logger('web.routes.subscription')

def create_subscription_bp(state_manager: StateManager) -> Blueprint:
    subscription_bp = Blueprint('subscription', __name__, url_prefix='/api')

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
            return jsonify({'status': 'error', 'message': str(e)}), 500

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
                    if success:
                        clear_config_cache()
                    break

            if not subscription_found:
                return jsonify({
                    'status': 'error',
                    'message': f'未找到订阅: {validated_data.name}'
                }), 404

            audit_log('update_subscription', {
                'subscription': validated_data.name,
                'fields': updated_fields
            })

            refresh_subscription_cache('config.json', state_manager)

            return jsonify({
                'status': 'success',
                'message': f'订阅 [{validated_data.name}] 配置已更新',
                'updated_fields': updated_fields
            })

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @subscription_bp.route('/subscription/add', methods=['POST'])
    @validate_request(AddSubscriptionRequest)
    def add_subscription(validated_data: AddSubscriptionRequest):
        """添加新订阅"""
        try:
            config = load_config_safe()

            subscriptions = config.get('subscriptions', [])
            for sub in subscriptions:
                if sub.get('name') == validated_data.name:
                    return jsonify({
                        'status': 'error',
                        'message': f'订阅名称 [{validated_data.name}] 已存在'
                    }), 400

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
            if success:
                clear_config_cache()

            audit_log('add_subscription', {
                'subscription': validated_data.name,
                'cycle_type': validated_data.cycle_type,
                'amount': validated_data.amount
            })

            refresh_subscription_cache('config.json', state_manager)

            return jsonify({
                'status': 'success',
                'message': f'订阅 [{validated_data.name}] 已成功添加'
            })

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @subscription_bp.route('/subscription/delete', methods=['POST', 'DELETE'])
    @validate_request(DeleteSubscriptionRequest)
    def delete_subscription_route(validated_data: DeleteSubscriptionRequest):
        """删除订阅"""
        try:
            config = load_config_safe()
            subscriptions = config.get('subscriptions', [])
            if not any(sub.get('name') == validated_data.name for sub in subscriptions):
                return jsonify({
                    'status': 'error',
                    'message': f'未找到订阅: {validated_data.name}'
                }), 404

            success = delete_subscription(validated_data.name)
            if success:
                clear_config_cache()

            audit_log('delete_subscription', {'subscription': validated_data.name})
            refresh_subscription_cache('config.json', state_manager)

            return jsonify({
                'status': 'success',
                'message': f'订阅 [{validated_data.name}] 已删除'
            })

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @subscription_bp.route('/subscription/mark_renewed', methods=['POST'])
    def mark_subscription_renewed():
        """标记订阅已续费"""
        try:
            data = request.get_json()
            if not data or 'name' not in data:
                return jsonify({
                    'status': 'error',
                    'message': '缺少订阅名称'
                }), 400

            subscription_name = data['name']
            renewed_date = data.get('renewed_date')

            success = upsert_subscription({
                'name': subscription_name,
                'last_renewed_date': renewed_date or __import__('datetime').date.today().isoformat()
            })

            if not success:
                return jsonify({
                    'status': 'error',
                    'message': '更新订阅失败'
                }), 500

            clear_config_cache()
            audit_log('mark_renewed', {'subscription': subscription_name})
            refresh_subscription_cache('config.json', state_manager)

            config = load_config_safe()

            from ..handlers import calculate_next_renewal_date
            from datetime import datetime
            sub_data = next(s for s in config['subscriptions'] if s['name'] == subscription_name)
            next_renewal = calculate_next_renewal_date(
                sub_data['cycle_type'],
                sub_data['renewal_day'],
                datetime.fromisoformat(sub_data['last_renewed_date'])
            )

            return jsonify({
                'status': 'success',
                'message': f'订阅 [{subscription_name}] 已标记为已续费',
                'next_renewal_date': next_renewal.isoformat()
            })

        except Exception as e:
            logger.error(f"标记续费失败: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @subscription_bp.route('/subscription/clear_renewed', methods=['POST'])
    def clear_subscription_renewed():
        """清除订阅的续费标记"""
        try:
            data = request.get_json()
            if not data or 'name' not in data:
                return jsonify({
                    'status': 'error',
                    'message': '缺少订阅名称'
                }), 400

            subscription_name = data['name']

            success = upsert_subscription({
                'name': subscription_name,
                'last_renewed_date': None
            })

            if not success:
                return jsonify({
                    'status': 'error',
                    'message': '更新订阅失败'
                }), 500

            clear_config_cache()
            audit_log('unmark_renewed', {'subscription': subscription_name})
            refresh_subscription_cache('config.json', state_manager)

            return jsonify({
                'status': 'success',
                'message': f'订阅 [{subscription_name}] 的续费标记已清除'
            })

        except Exception as e:
            logger.error(f"清除续费标记失败: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': str(e)}), 500

    return subscription_bp
