#!/usr/bin/env python3
"""
核心 API 路由

包含健康检查、余额查询、刷新等核心功能
"""
import os
import time
import threading
from flask import Blueprint, jsonify, request, render_template, send_from_directory
from pathlib import Path
from ..utils import get_enable_web_alarm, make_etag_response
from ..handlers import update_balance_cache, refresh_credits
from core.state_manager import StateManager
from core.logger import get_logger

logger = get_logger('web.routes.core')

# 创建蓝图
core_bp = Blueprint('core', __name__)

# 刷新接口速率限制
_refresh_lock = threading.Lock()
_last_refresh_time = 0.0
REFRESH_COOLDOWN = 30  # 最少间隔30秒

# 健康检查常量
CRON_FAILURE_LOG = '/app/logs/cron_failures.log'
STALENESS_MULTIPLIER = 3

# 全局状态管理器（需要从外部注入）
_state_manager: StateManager = None


def init_core_routes(state_mgr: StateManager):
    """
    初始化核心路由（注入依赖）

    Args:
        state_mgr: 状态管理器实例
    """
    global _state_manager
    _state_manager = state_mgr


@core_bp.route('/')
def index():
    """首页 - Dashboard"""
    return render_template('index.html')


@core_bp.route('/health')
@core_bp.route('/ready')
def health():
    """
    就绪检查端点

    返回：
    - 200: 服务健康且数据可用
    - 503: 服务启动中或数据过期
    """
    from datetime import datetime, timedelta
    from ..utils import get_refresh_interval

    # 获取状态
    balance_state = _state_manager.get_balance_state()
    last_update = balance_state.get('last_update')

    # 检查是否有数据
    has_data = bool(balance_state.get('projects'))

    # 检查数据是否过期
    is_stale = False
    if last_update:
        try:
            last_update_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00')) if isinstance(last_update, str) else last_update
            refresh_interval = get_refresh_interval()
            stale_threshold = timedelta(seconds=refresh_interval * STALENESS_MULTIPLIER)
            now = datetime.now(last_update_dt.tzinfo) if last_update_dt.tzinfo else datetime.now()
            time_since_update = now - last_update_dt
            is_stale = time_since_update > stale_threshold
        except Exception:
            is_stale = False

    # 检查 cron 是否失败
    cron_healthy = True
    if Path(CRON_FAILURE_LOG).exists():
        try:
            with open(CRON_FAILURE_LOG, 'r') as f:
                lines = f.readlines()
                if lines:
                    cron_healthy = False
        except Exception:
            pass

    # 计算运行时间
    uptime_seconds = int(time.time() - _state_manager._start_time) if hasattr(_state_manager, '_start_time') else 0

    response_data = {
        'status': 'healthy' if (has_data and not is_stale and cron_healthy) else 'degraded',
        'has_data': has_data,
        'is_stale': is_stale,
        'cron_healthy': cron_healthy,
        'last_update': last_update if isinstance(last_update, str) else (last_update.isoformat() if last_update else None),
        'uptime_seconds': uptime_seconds,
        'version': os.environ.get('APP_VERSION', '1.0.0')
    }

    status_code = 200 if response_data['status'] == 'healthy' else 503
    return jsonify(response_data), status_code


@core_bp.route('/live')
def live():
    """存活检查端点：只验证进程能正常响应。"""
    uptime_seconds = int(time.time() - _state_manager._start_time) if hasattr(_state_manager, '_start_time') else 0
    return jsonify({
        'status': 'alive',
        'uptime_seconds': uptime_seconds,
        'version': os.environ.get('APP_VERSION', '1.0.0')
    })


@core_bp.route('/api/features')
def get_features():
    """返回当前启用的可选能力，前端据此隐藏高级入口。"""
    return jsonify({
        'status': 'success',
        'features': {
            'subscriptions': os.environ.get('ENABLE_SUBSCRIPTIONS', 'false').lower() == 'true',
            'dynamic_config': os.environ.get('ENABLE_DYNAMIC_CONFIG', 'false').lower() == 'true',
            'history': os.environ.get('ENABLE_HISTORY_API', 'false').lower() == 'true',
        }
    })


@core_bp.route('/api/credits')
def get_credits():
    """获取所有项目的余额信息"""
    balance_state = _state_manager.get_balance_state()

    if not balance_state or not balance_state.get('projects'):
        return jsonify({
            'status': 'error',
            'message': '余额数据未初始化，请稍后重试'
        }), 503

    # 使用 ETag 支持缓存
    return make_etag_response(balance_state)


@core_bp.route('/api/subscriptions')
def get_subscriptions_disabled():
    """核心版保留空响应，避免前端在未启用订阅功能时失败。"""
    return make_etag_response(_state_manager.get_subscription_state())


@core_bp.route('/api/subscription/add', methods=['POST'])
def add_subscription_disabled():
    """订阅功能关闭时的兼容响应。"""
    data = request.get_json(silent=True) or {}
    required_fields = ['name', 'cycle_type', 'renewal_day', 'alert_days_before', 'amount']
    missing = [field for field in required_fields if data.get(field) in (None, '')]
    if missing:
        return jsonify({
            'status': 'error',
            'message': f"缺少必要参数: {', '.join(missing)}"
        }), 400

    return jsonify({
        'status': 'error',
        'message': '订阅功能未启用，请设置 ENABLE_SUBSCRIPTIONS=true'
    }), 503


@core_bp.route('/api/refresh', methods=['GET', 'POST'])
def refresh_credits_route():
    """
    手动刷新余额

    请求体（可选）:
        {
            "project_name": "项目名称"  // 可选：仅刷新指定项目
        }

    返回:
        {
            "status": "success",
            "message": "刷新完成",
            "refreshed_count": 5
        }
    """
    global _last_refresh_time

    # 速率限制检查
    with _refresh_lock:
        current_time = time.time()
        time_since_last = current_time - _last_refresh_time

        if time_since_last < REFRESH_COOLDOWN:
            wait_time = int(REFRESH_COOLDOWN - time_since_last)
            return jsonify({
                'status': 'error',
                'message': f'刷新过于频繁，请{wait_time}秒后重试'
            }), 429

        _last_refresh_time = current_time

    # 解析请求参数
    project_name = None
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        project_name = data.get('project_name')
        if project_name is not None and not isinstance(project_name, str):
            return jsonify({
                'status': 'error',
                'message': 'project_name 必须是字符串'
            }), 400
        if isinstance(project_name, str):
            project_name = project_name.strip() or None

    # 执行刷新
    try:
        start_time = time.time()
        dry_run = not get_enable_web_alarm()  # Web 是否发送告警

        result = refresh_credits('config.json', project_name, dry_run)

        if not result['success']:
            return jsonify({
                'status': 'error',
                'message': f"刷新失败: {result.get('error', 'Unknown error')}"
            }), 500

        # 更新缓存
        is_partial = project_name is not None
        update_balance_cache(result['results'], _state_manager, is_partial=is_partial)

        execution_time = time.time() - start_time

        return jsonify({
            'status': 'success',
            'message': f"刷新完成{'（项目: ' + project_name + '）' if project_name else ''}",
            'refreshed_count': result['count'],
            'execution_time_seconds': round(execution_time, 2),
            'dry_run': dry_run
        })

    except Exception as e:
        logger.error(f"刷新失败: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'刷新失败: {str(e)}'
        }), 500


# 静态文件服务（如果需要）
@core_bp.route('/static/<path:filename>')
def serve_static(filename):
    """提供静态文件"""
    static_folder = Path(__file__).parent.parent.parent / 'static'
    return send_from_directory(static_folder, filename)
