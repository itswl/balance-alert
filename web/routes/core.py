#!/usr/bin/env python3
"""
核心 API 路由

包含健康检查、余额查询、刷新等核心功能
"""
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, jsonify, request, render_template

from core.config_loader import get_default_config_path, get_refresh_interval
from core.settings import get_settings
from core.state_manager import StateManager
from core.logger import get_logger
from services.monitor import run_credit_monitor
from ..utils import make_etag_response, json_error, json_success

logger = get_logger('web.routes.core')

# 健康检查常量
CRON_FAILURE_LOG = '/app/logs/cron_failures.log'
STALENESS_MULTIPLIER = 3


def create_core_bp(state_manager: StateManager) -> Blueprint:
    core_bp = Blueprint('core', __name__)
    refresh_lock = threading.Lock()
    last_refresh_time = {'value': 0.0}
    refresh_cooldown_seconds = 30

    @core_bp.route('/')
    def index():
        """首页 - Dashboard"""
        return render_template('index.html')

    @core_bp.route('/health')
    def health():
        """
        就绪检查端点

        返回：
        - 200: 服务健康且数据可用
        - 503: 服务启动中或数据过期
        """
        balance_state = state_manager.get_balance_state()
        last_update = balance_state.get('last_update')
        has_data = bool(balance_state.get('projects'))

        is_stale = False
        if last_update:
            try:
                last_update_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00')) if isinstance(last_update, str) else last_update
                stale_threshold = timedelta(seconds=get_refresh_interval() * STALENESS_MULTIPLIER)
                now = datetime.now(last_update_dt.tzinfo) if last_update_dt.tzinfo else datetime.now()
                is_stale = (now - last_update_dt) > stale_threshold
            except Exception:
                is_stale = False

        cron_healthy = True
        cron_failure_path = Path(CRON_FAILURE_LOG)
        if cron_failure_path.exists():
            try:
                cron_healthy = cron_failure_path.stat().st_size == 0
            except Exception:
                pass

        response_data = {
            'status': 'healthy' if (has_data and not is_stale and cron_healthy) else 'degraded',
            'has_data': has_data,
            'is_stale': is_stale,
            'cron_healthy': cron_healthy,
            'last_update': last_update if isinstance(last_update, str) else (last_update.isoformat() if last_update else None),
            'uptime_seconds': int(state_manager.uptime_seconds()),
            'version': get_settings().app_version
        }

        status_code = 200 if response_data['status'] == 'healthy' else 503
        return jsonify(response_data), status_code

    @core_bp.route('/live')
    def live():
        """存活检查端点：只验证进程能正常响应。"""
        return json_success({
            'status': 'alive',
            'uptime_seconds': int(state_manager.uptime_seconds()),
            'version': get_settings().app_version
        }, 200)

    @core_bp.route('/api/features')
    def get_features():
        """返回当前启用的可选能力，前端据此隐藏高级入口。"""
        settings = get_settings()
        return jsonify({
            'status': 'success',
            'features': {
                'subscriptions': settings.enable_subscriptions,
                'dynamic_config': settings.enable_dynamic_config,
                'history': settings.enable_history_api,
            }
        })

    @core_bp.route('/api/credits')
    def get_credits():
        """获取所有项目的余额信息"""
        balance_state = state_manager.get_balance_state()

        if not balance_state or not balance_state.get('projects'):
            return json_error('余额数据未初始化，请稍后重试', 503)

        return make_etag_response(balance_state)

    @core_bp.route('/api/subscriptions')
    def get_subscriptions():
        """获取订阅状态数据（订阅功能未启用时返回空状态）"""
        return make_etag_response(state_manager.get_subscription_state())

    @core_bp.route('/api/refresh', methods=['GET', 'POST'])
    def refresh_credits_route():
        with refresh_lock:
            current_time = time.time()
            time_since_last = current_time - last_refresh_time['value']

            if time_since_last < refresh_cooldown_seconds:
                wait_time = int(refresh_cooldown_seconds - time_since_last)
                return json_error(f'刷新过于频繁，请{wait_time}秒后重试', 429)

            last_refresh_time['value'] = current_time

        project_name = None
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            project_name = data.get('project_name')
            if project_name is not None and not isinstance(project_name, str):
                return json_error('project_name 必须是字符串', 400)
            if isinstance(project_name, str):
                project_name = project_name.strip() or None

        try:
            start_time = time.time()
            dry_run = not get_settings().enable_web_alarm

            result = run_credit_monitor(get_default_config_path(), project_name, dry_run)

            if not result['success']:
                return json_error(f"刷新失败: {result.get('error', 'Unknown error')}", 500)

            if project_name is not None:
                state_manager.merge_balance_state(result['results'])
            else:
                state_manager.update_balance_state(result['results'])

            execution_time = time.time() - start_time

            return json_success({
                'status': 'success',
                'message': f"刷新完成{'（项目: ' + project_name + '）' if project_name else ''}",
                'refreshed_count': result['count'],
                'execution_time_seconds': round(execution_time, 2),
                'dry_run': dry_run
            }, 200)

        except Exception as e:
            logger.error(f"刷新失败: {e}", exc_info=True)
            return json_error(f'刷新失败: {str(e)}', 500)

    return core_bp
