#!/usr/bin/env python3
"""
订阅管理 API 路由

包含订阅的增删改查、标记续费等功能
"""
from flask import Blueprint, jsonify, request
from ..middleware import require_api_key, validate_request
from ..utils import load_config_safe, write_config, audit_log
from ..handlers import update_subscription_cache, refresh_subscription_cache
from state_manager import StateManager
from models.api_models import (
    AddSubscriptionRequest,
    UpdateSubscriptionRequest,
    DeleteSubscriptionRequest
)
from logger import get_logger

logger = get_logger('web.routes.subscription')

# 创建蓝图
subscription_bp = Blueprint('subscription', __name__, url_prefix='/api')

# 全局状态管理器（需要从外部注入）
_state_manager: StateManager = None


def init_subscription_routes(state_mgr: StateManager):
    """
    初始化订阅路由（注入依赖）

    Args:
        state_mgr: 状态管理器实例
    """
    global _state_manager
    _state_manager = state_mgr


@subscription_bp.route('/subscriptions')
def get_subscriptions():
    """获取订阅状态数据"""
    from ..utils import make_etag_response
    return make_etag_response(_state_manager.get_subscription_state())


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
@require_api_key
@validate_request(UpdateSubscriptionRequest)
def update_subscription(validated_data: UpdateSubscriptionRequest):
    """更新订阅配置"""
    try:
        # 读取配置文件
        config = load_config_safe()

        # 查找订阅
        subscription_found = False
        updated_fields = []

        for sub in config.get('subscriptions', []):
            if sub.get('name') == validated_data.name:
                # 更新各字段
                if validated_data.new_name is not None:
                    sub['name'] = validated_data.new_name
                    updated_fields.append('name')

                if validated_data.cycle_type is not None:
                    sub['cycle_type'] = validated_data.cycle_type
                    updated_fields.append('cycle_type')

                if validated_data.renewal_day is not None:
                    sub['renewal_day'] = validated_data.renewal_day
                    updated_fields.append('renewal_day')

                if validated_data.alert_days_before is not None:
                    sub['alert_days_before'] = validated_data.alert_days_before
                    updated_fields.append('alert_days_before')

                if validated_data.amount is not None:
                    sub['amount'] = validated_data.amount
                    updated_fields.append('amount')

                if validated_data.currency is not None:
                    sub['currency'] = validated_data.currency
                    updated_fields.append('currency')

                if validated_data.enabled is not None:
                    sub['enabled'] = validated_data.enabled
                    updated_fields.append('enabled')

                if validated_data.last_renewed_date is not None:
                    sub['last_renewed_date'] = validated_data.last_renewed_date
                    updated_fields.append('last_renewed_date')

                subscription_found = True
                break

        if not subscription_found:
            return jsonify({
                'status': 'error',
                'message': f'未找到订阅: {validated_data.name}'
            }), 404

        # 保存配置文件
        write_config(config)
        audit_log('update_subscription', {
            'subscription': validated_data.name,
            'fields': updated_fields
        })

        # 立即刷新缓存
        refresh_subscription_cache('config.json', _state_manager)

        return jsonify({
            'status': 'success',
            'message': f'订阅 [{validated_data.name}] 配置已更新',
            'updated_fields': updated_fields
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@subscription_bp.route('/subscription/add', methods=['POST'])
@require_api_key
@validate_request(AddSubscriptionRequest)
def add_subscription(validated_data: AddSubscriptionRequest):
    """添加新订阅"""
    try:
        # 读取配置文件
        config = load_config_safe()

        # 检查订阅名称是否已存在
        subscriptions = config.get('subscriptions', [])
        for sub in subscriptions:
            if sub.get('name') == validated_data.name:
                return jsonify({
                    'status': 'error',
                    'message': f'订阅名称 [{validated_data.name}] 已存在'
                }), 400

        # 创建新订阅
        new_subscription = {
            'name': validated_data.name,
            'cycle_type': validated_data.cycle_type,
            'renewal_day': validated_data.renewal_day,
            'alert_days_before': validated_data.alert_days_before,
            'amount': validated_data.amount,
            'currency': validated_data.currency,
            'enabled': validated_data.enabled
        }

        # 可选字段
        if validated_data.last_renewed_date:
            new_subscription['last_renewed_date'] = validated_data.last_renewed_date

        # 添加到配置
        subscriptions.append(new_subscription)
        config['subscriptions'] = subscriptions

        # 保存配置文件
        write_config(config)
        audit_log('add_subscription', {
            'subscription': validated_data.name,
            'cycle_type': validated_data.cycle_type,
            'amount': validated_data.amount
        })

        # 立即刷新缓存
        refresh_subscription_cache('config.json', _state_manager)

        return jsonify({
            'status': 'success',
            'message': f'订阅 [{validated_data.name}] 已成功添加'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@subscription_bp.route('/subscription/delete', methods=['POST', 'DELETE'])
@require_api_key
@validate_request(DeleteSubscriptionRequest)
def delete_subscription(validated_data: DeleteSubscriptionRequest):
    """删除订阅"""
    try:
        # 读取配置文件
        config = load_config_safe()

        # 查找并删除订阅
        subscriptions = config.get('subscriptions', [])
        subscription_found = False
        new_subscriptions = []

        for sub in subscriptions:
            if sub.get('name') == validated_data.name:
                subscription_found = True
                # 跳过该订阅，不添加到新列表中
                continue
            new_subscriptions.append(sub)

        if not subscription_found:
            return jsonify({
                'status': 'error',
                'message': f'未找到订阅: {validated_data.name}'
            }), 404

        # 更新配置
        config['subscriptions'] = new_subscriptions

        # 保存配置文件
        write_config(config)
        audit_log('delete_subscription', {'subscription': validated_data.name})

        # 立即刷新缓存
        refresh_subscription_cache('config.json', _state_manager)

        return jsonify({
            'status': 'success',
            'message': f'订阅 [{validated_data.name}] 已删除'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@subscription_bp.route('/subscription/mark_renewed', methods=['POST'])
@require_api_key
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
        renewed_date = data.get('renewed_date')  # 可选，默认今天

        # 读取配置
        config = load_config_safe()
        subscription_found = False

        for sub in config.get('subscriptions', []):
            if sub.get('name') == subscription_name:
                # 更新最后续费日期
                from datetime import date
                sub['last_renewed_date'] = renewed_date or date.today().isoformat()

                subscription_found = True
                break

        if not subscription_found:
            return jsonify({
                'status': 'error',
                'message': f'未找到订阅: {subscription_name}'
            }), 404

        # 保存配置
        write_config(config)
        audit_log('mark_renewed', {'subscription': subscription_name})

        # 刷新缓存
        refresh_subscription_cache('config.json', _state_manager)

        # 计算下次续费日期
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
@require_api_key
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

        # 读取配置
        config = load_config_safe()
        subscription_found = False

        for sub in config.get('subscriptions', []):
            if sub.get('name') == subscription_name:
                # 删除最后续费日期字段
                if 'last_renewed_date' in sub:
                    del sub['last_renewed_date']
                subscription_found = True
                break

        if not subscription_found:
            return jsonify({
                'status': 'error',
                'message': f'未找到订阅: {subscription_name}'
            }), 404

        # 保存配置
        write_config(config)
        audit_log('clear_renewed', {'subscription': subscription_name})

       # 刷新缓存
        refresh_subscription_cache('config.json', _state_manager)

        return jsonify({
            'status': 'success',
            'message': f'订阅 [{subscription_name}] 的续费标记已清除'
        })

    except Exception as e:
        logger.error(f"清除续费标记失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500
