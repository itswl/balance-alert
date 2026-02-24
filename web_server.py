#!/usr/bin/env python3
"""
余额监控 Web 服务器
提供实时余额查询的 HTTP API
"""
from flask import Flask, jsonify, render_template, send_from_directory, request
from flask_cors import CORS
from functools import wraps
import json
import os
import fcntl
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import hashlib
from monitor import CreditMonitor
from subscription_checker import SubscriptionChecker
from prometheus_exporter import metrics_endpoint, metrics_collector
from logger import get_logger
from config_loader import get_config, start_config_watcher, stop_config_watcher
from state_manager import StateManager

# 数据库持久化（可选）
try:
    from database import init_database
    from database.repository import BalanceRepository, AlertRepository, SubscriptionRepository
    DB_AVAILABLE = True
    # 初始化数据库
    if init_database():
        logger.info("✅ 数据库已初始化")
except (ImportError, Exception) as e:
    DB_AVAILABLE = False
    logger.warning(f"数据库模块不可用: {e}")
import signal
import threading
from datetime import datetime
import time
from pydantic import ValidationError
from models.api_models import (
    AddSubscriptionRequest,
    UpdateSubscriptionRequest,
    DeleteSubscriptionRequest,
    RefreshRequest,
    AddEmailRequest,
    UpdateEmailRequest,
    DeleteEmailRequest,
)

# 创建 logger
logger = get_logger('web_server')

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# API 认证
API_KEY = os.environ.get('API_KEY', '')

# 请求体大小限制 (1MB)
MAX_CONTENT_LENGTH = 1 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# 默认刷新间隔常量
DEFAULT_REFRESH_INTERVAL = 3600  # 默认刷新间隔（秒）
DEFAULT_MIN_REFRESH_INTERVAL = 60  # 默认最小刷新间隔（秒）

# 刷新接口速率限制
_refresh_lock = threading.Lock()
_last_refresh_time = 0.0
REFRESH_COOLDOWN = 30  # 最少间隔30秒

# 优雅关闭事件
_stop_event = threading.Event()

# 健康检查常量
CRON_FAILURE_LOG = '/app/logs/cron_failures.log'
STALENESS_MULTIPLIER = 3  # last_update 超过 refresh_interval * 此倍数视为过期


def require_api_key(f):
    """API 认证装饰器，仅在设置了 API_KEY 时启用"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_KEY:
            return f(*args, **kwargs)
        token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
        if not token:
            token = request.args.get('api_key', '')
        if token != API_KEY:
            return jsonify({'status': 'error', 'message': '未授权访问'}), 401
        return f(*args, **kwargs)
    return decorated


def validate_request(model_class):
    """
    请求验证装饰器，使用 Pydantic 模型验证请求体

    用法：
        @validate_request(AddSubscriptionRequest)
        def my_endpoint(validated_data: AddSubscriptionRequest):
            # validated_data 是已验证的 Pydantic 模型实例
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            try:
                # 获取请求数据
                data = request.get_json()
                if data is None:
                    return jsonify({
                        'status': 'error',
                        'message': '请求体为空或格式不正确'
                    }), 400

                # 使用 Pydantic 验证
                validated_data = model_class(**data)

                # 将验证后的数据传递给路由函数
                return f(validated_data=validated_data, *args, **kwargs)

            except ValidationError as e:
                # Pydantic 验证错误
                errors = []
                for error in e.errors():
                    field = ' -> '.join(str(loc) for loc in error['loc'])
                    message = error['msg']
                    errors.append(f"{field}: {message}")

                return jsonify({
                    'status': 'error',
                    'message': '请求参数验证失败',
                    'errors': errors
                }), 400

            except Exception as e:
                logger.error(f"请求验证异常: {e}", exc_info=True)
                return jsonify({
                    'status': 'error',
                    'message': f'请求处理失败: {str(e)}'
                }), 500

        return decorated
    return decorator


# 配置：是否在 Web 模式下发送真实告警（默认不发送，避免重复告警）
# 如果需要 Web 也发送告警，设置环境变量 ENABLE_WEB_ALARM=true
def get_enable_web_alarm() -> bool:
    """动态读取 ENABLE_WEB_ALARM 环境变量"""
    return os.environ.get('ENABLE_WEB_ALARM', 'false').lower() == 'true'

def get_refresh_interval() -> int:
    """从配置文件读取刷新间隔"""
    try:
        config = get_config('config.json')
        settings = config.get('settings', {})
        
        # 获取配置值
        interval = settings.get('balance_refresh_interval_seconds', DEFAULT_REFRESH_INTERVAL)
        min_interval = settings.get('min_refresh_interval_seconds', DEFAULT_MIN_REFRESH_INTERVAL)

        # 验证配置合理性
        if not isinstance(interval, (int, float)) or interval <= 0:
            logger.warning(f"刷新间隔配置无效 ({interval})，使用默认值{DEFAULT_REFRESH_INTERVAL}秒")
            interval = DEFAULT_REFRESH_INTERVAL

        if not isinstance(min_interval, (int, float)) or min_interval <= 0:
            logger.warning(f"最小刷新间隔配置无效 ({min_interval})，使用默认值{DEFAULT_MIN_REFRESH_INTERVAL}秒")
            min_interval = DEFAULT_MIN_REFRESH_INTERVAL
        
        # 确保刷新间隔不小于最小值
        final_interval = max(min_interval, int(interval))
        
        logger.info(f"刷新间隔配置: 设置值={interval}s, 最小值={min_interval}s, 实际值={final_interval}s")
        return final_interval
        
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"读取刷新间隔配置失败，使用默认值{DEFAULT_REFRESH_INTERVAL}秒: {e}")
        return DEFAULT_REFRESH_INTERVAL


def get_smart_refresh_config() -> Dict[str, Any]:
    """获取智能刷新配置"""
    try:
        config = get_config('config.json')
        settings = config.get('settings', {})
        
        return {
            'enabled': settings.get('enable_smart_refresh', False),
            'threshold_percent': settings.get('smart_refresh_threshold_percent', 5),
            'min_check_interval': settings.get('min_refresh_interval_seconds', 60)
        }
    except Exception as e:
        logger.warning(f"读取智能刷新配置失败: {e}")
        return {
            'enabled': False,
            'threshold_percent': 5,
            'min_check_interval': 60
        }


class DataChangeDetector:
    """数据变化检测器，用于智能刷新"""

    def __init__(self) -> None:
        self._last_data_hash: Dict[str, str] = {}
        self._last_check_time: Dict[str, float] = {}
        self._lock: threading.Lock = threading.Lock()

    def detect_changes(self, data: Dict[str, Any], data_type: str) -> bool:
        """
        检测数据是否发生变化

        Args:
            data: 当前数据
            data_type: 数据类型标识

        Returns:
            bool: 是否发生变化
        """
        # 生成数据哈希
        data_str = json.dumps(data, sort_keys=True, default=str)
        current_hash = hashlib.md5(data_str.encode()).hexdigest()

        with self._lock:
            # 比较哈希值
            last_hash = self._last_data_hash.get(data_type)
            has_changed = (last_hash != current_hash)

            # 更新记录
            self._last_data_hash[data_type] = current_hash
            self._last_check_time[data_type] = time.time()

        if has_changed:
            logger.debug(f"检测到 {data_type} 数据变化")

        return has_changed

    def should_force_refresh(self, data_type: str, threshold_percent: float = 5) -> bool:
        """
        判断是否应该强制刷新（即使数据未变化）

        Args:
            data_type: 数据类型标识
            threshold_percent: 强制刷新阈值百分比

        Returns:
            bool: 是否应该强制刷新
        """
        with self._lock:
            last_check = self._last_check_time.get(data_type, 0)
        elapsed = time.time() - last_check
        max_interval = get_refresh_interval()
        threshold_time = max_interval * (threshold_percent / 100)

        should_refresh = elapsed >= threshold_time
        if should_refresh:
            logger.debug(f"{data_type} 达到强制刷新时间阈值 ({elapsed:.1f}s >= {threshold_time:.1f}s)")

        return should_refresh


# 全局状态管理器实例（向后兼容）
# 新代码建议通过参数传递
from state_manager import state_manager as global_state_manager

# 全局数据变化检测器
data_detector = DataChangeDetector()


def update_balance_cache(results: List[Dict[str, Any]], state_mgr: StateManager = global_state_manager) -> None:
    """更新余额缓存（使用状态管理器）"""
    state_mgr.update_balance_state(results)


def update_subscription_cache(results: List[Dict[str, Any]], state_mgr: StateManager = global_state_manager) -> None:
    """更新订阅缓存（使用状态管理器）"""
    state_mgr.update_subscription_state(results)


def save_cache_file(state_mgr: StateManager = global_state_manager) -> None:
    """保存缓存到文件（使用状态管理器）"""
    # 状态管理器会自动处理保存逻辑
    state_mgr.save_to_cache()


def _audit_log(action: str, details: Dict[str, Any]) -> None:
    """记录配置变更审计日志"""
    ip = request.remote_addr if request else 'N/A'
    details_json = json.dumps(details, ensure_ascii=False, default=str)
    logger.info(f"[AUDIT] {action} | ip={ip} | {details_json}")


def _write_config(config: Dict[str, Any], config_path: str = 'config.json') -> None:
    """原子写入配置文件（写入临时文件后重命名）"""
    dir_path = os.path.dirname(os.path.abspath(config_path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp', prefix='.config_')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, config_path)
    except BaseException:
        os.unlink(tmp_path)
        raise


def _validate_renewal_day(renewal_day: int, cycle_type: str) -> Optional[str]:
    """验证续费日期，返回错误消息或 None"""
    if cycle_type == 'weekly' and (renewal_day < 1 or renewal_day > 7):
        return '周周期的续费日期必须在 1-7 之间'
    elif (cycle_type == 'monthly' or cycle_type == 'yearly') and (renewal_day < 1 or renewal_day > 31):
        return '续费日期必须在 1-31 之间' if cycle_type == 'monthly' else '月/年周期的续费日期必须在 1-31 之间'
    return None


def _calculate_yearly_renewed_date(renewal_month: int, renewal_day: int) -> Tuple[Optional[str], Optional[str]]:
    """计算年周期的 last_renewed_date，返回 (date_str, error_msg)"""
    current_year = datetime.now().year
    try:
        base_date = datetime(current_year, renewal_month, renewal_day)
        if base_date > datetime.now():
            base_date = datetime(current_year - 1, renewal_month, renewal_day)
        return base_date.strftime('%Y-%m-%d'), None
    except ValueError:
        return None, f'{renewal_month}月{renewal_day}日不是有效日期'


def refresh_subscription_cache(state_mgr: StateManager = global_state_manager) -> None:
    """重新检查订阅并更新缓存（公共逻辑提取）"""
    try:
        subscription_checker = SubscriptionChecker('config.json')
        subscription_checker.check_subscriptions(dry_run=not get_enable_web_alarm())
        update_subscription_cache(subscription_checker.results, state_mgr)
    except Exception as e:
        logger.error(f'更新订阅缓存失败: {e}')


def update_credits(state_mgr: StateManager = global_state_manager, detector: Optional[DataChangeDetector] = None):
    """
    后台定时更新余额数据

    Args:
        state_mgr: 状态管理器实例（默认使用全局实例）
        detector: 数据变化检测器（默认使用全局实例）
    """
    if detector is None:
        detector = data_detector

    while not _stop_event.is_set():
        try:
            # 获取智能刷新配置
            smart_config = get_smart_refresh_config()
            smart_refresh_enabled = smart_config['enabled']

            logger.info(f"开始更新数据 (智能刷新: {'启用' if smart_refresh_enabled else '禁用'})")

            # 更新余额/积分数据
            monitor = CreditMonitor('config.json')
            monitor.run(dry_run=not get_enable_web_alarm())

            # 检测余额数据变化（智能刷新）
            balance_changed = False
            if smart_refresh_enabled:
                balance_changed = detector.detect_changes(
                    monitor.results,
                    'balance'
                )

            # 更新缓存
            update_balance_cache(monitor.results, state_mgr)

            # 更新订阅数据
            subscription_checker = SubscriptionChecker('config.json')
            subscription_checker.check_subscriptions(dry_run=not get_enable_web_alarm())

            # 检测订阅数据变化（智能刷新）
            subscription_changed = False
            if smart_refresh_enabled:
                subscription_changed = detector.detect_changes(
                    subscription_checker.results,
                    'subscription'
                )

            # 更新缓存
            update_subscription_cache(subscription_checker.results, state_mgr)

            # 更新 Prometheus 指标
            metrics_collector.update_balance_metrics(monitor.results)
            metrics_collector.update_subscription_metrics(subscription_checker.results)

            # 保存缓存到文件
            save_cache_file(state_mgr)

            # 智能刷新日志
            if smart_refresh_enabled:
                logger.info(f"数据更新完成 - 余额变化: {'是' if balance_changed else '否'}, "
                           f"订阅变化: {'是' if subscription_changed else '否'}")

        except Exception as e:
            logger.error(f"更新数据失败: {e}", exc_info=True)
            metrics_collector.set_check_failed('balance')

        # 根据配置间隔等待
        sleep_seconds = get_refresh_interval()

        # 智能刷新逻辑
        if smart_config['enabled']:
            # 检查是否需要强制刷新
            force_balance_refresh = detector.should_force_refresh(
                'balance', smart_config['threshold_percent']
            )
            force_subscription_refresh = detector.should_force_refresh(
                'subscription', smart_config['threshold_percent']
            )

            if force_balance_refresh or force_subscription_refresh:
                logger.info(f"达到强制刷新阈值，下次将在 {sleep_seconds} 秒后更新")
            elif balance_changed or subscription_changed:
                logger.info(f"检测到数据变化，下次将在 {sleep_seconds} 秒后更新")
            else:
                logger.info(f"数据无变化，下次将在 {sleep_seconds} 秒后更新")
        else:
            logger.info(f"下次更新将在 {sleep_seconds} 秒后")

        # 使用可中断的 sleep
        _stop_event.wait(sleep_seconds)

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/health')
def health():
    """健康检查端点"""
    has_data = global_state_manager.has_data()
    now = time.time()

    # 数据过期检测
    data_stale = False
    if has_data:
        balance_state = global_state_manager.get_balance_state()
        last_update_str = balance_state.get('last_update')
        if last_update_str:
            try:
                last_update_dt = datetime.strptime(last_update_str, '%Y-%m-%d %H:%M:%S')
                age_seconds = now - last_update_dt.timestamp()
                refresh_interval = get_refresh_interval()
                if age_seconds > refresh_interval * STALENESS_MULTIPLIER:
                    data_stale = True
            except (ValueError, OSError):
                pass

    # Cron 失败检测
    cron_healthy = True
    last_cron_failure = None
    try:
        if os.path.exists(CRON_FAILURE_LOG):
            stat = os.stat(CRON_FAILURE_LOG)
            if stat.st_size > 0:
                cron_healthy = False
                last_cron_failure = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    except OSError:
        pass

    # 决定状态
    if not has_data:
        health_status = 'initializing'
        code = 503
    elif data_stale or not cron_healthy:
        health_status = 'degraded'
        code = 503
    else:
        health_status = 'ok'
        code = 200

    status = {
        'status': health_status,
        'timestamp': now,
        'has_data': has_data,
        'data_stale': data_stale,
        'cron_healthy': cron_healthy,
        'web_alarm_enabled': get_enable_web_alarm()
    }
    if last_cron_failure:
        status['last_cron_failure'] = last_cron_failure

    return jsonify(status), code

def _make_etag_response(data):
    """生成带 ETag 的 JSON 响应，支持 304 Not Modified"""
    body = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    etag = '"' + hashlib.md5(body.encode()).hexdigest() + '"'

    if request.headers.get('If-None-Match') == etag:
        return '', 304

    resp = app.response_class(body, mimetype='application/json')
    resp.headers['ETag'] = etag
    return resp


@app.route('/api/credits')
def get_credits():
    """获取所有项目余额"""
    return _make_etag_response(global_state_manager.get_balance_state())

@app.route('/api/refresh', methods=['GET', 'POST'])
@require_api_key
def refresh_credits():
    """手动刷新余额（带速率限制）"""
    global _last_refresh_time
    with _refresh_lock:
        now = time.time()
        if now - _last_refresh_time < REFRESH_COOLDOWN:
            remaining = int(REFRESH_COOLDOWN - (now - _last_refresh_time))
            return jsonify({
                'status': 'error',
                'message': f'刷新过于频繁，请 {remaining} 秒后再试'
            }), 429
        _last_refresh_time = now
    try:
        # 刷新余额/积分
        monitor = CreditMonitor('config.json')
        monitor.run(dry_run=not get_enable_web_alarm())

        # 使用公共方法更新缓存
        update_balance_cache(monitor.results, global_state_manager)

        # 刷新订阅
        subscription_checker = SubscriptionChecker('config.json')
        subscription_checker.check_subscriptions(dry_run=not get_enable_web_alarm())

        # 使用公共方法更新缓存
        update_subscription_cache(subscription_checker.results, global_state_manager)

        # 更新 Prometheus 指标
        metrics_collector.update_balance_metrics(monitor.results)
        metrics_collector.update_subscription_metrics(subscription_checker.results)

        # 保存缓存到文件
        save_cache_file(global_state_manager)

        # 返回最新的状态数据
        balance_state = global_state_manager.get_balance_state()
        subscription_state = global_state_manager.get_subscription_state()

        return jsonify({
            'status': 'success',
            'data': {
                'last_update': balance_state.get('last_update'),
                'projects': balance_state.get('projects', []),
                'summary': balance_state.get('summary', {}),
                'subscriptions': subscription_state.get('subscriptions', [])
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def load_config_safe(config_path='config.json'):
    """安全加载配置文件"""
    try:
        from config_loader import load_config_with_env_vars
        return load_config_with_env_vars(config_path, validate=False)
    except Exception as e:
        logger.error(f"配置加载失败: {e}")
        return {}


@app.route('/api/config/projects', methods=['GET'])
def get_projects_config():
    """获取所有项目配置"""
    try:
        config = load_config_safe()
        
        # 只返回项目配置，隐藏 api_key
        projects = []
        for p in config.get('projects', []):
            projects.append({
                'name': p.get('name'),
                'provider': p.get('provider'),
                'threshold': p.get('threshold'),
                'type': p.get('type'),
                'enabled': p.get('enabled', True)
            })
        
        return jsonify({'status': 'success', 'projects': projects})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/subscriptions')
def get_subscriptions():
    """获取订阅数据"""
    return _make_etag_response(global_state_manager.get_subscription_state())

@app.route('/api/config/subscriptions', methods=['GET'])
def get_subscriptions_config():
    """获取所有订阅配置"""
    try:
        config = load_config_safe()
        subscriptions = config.get('subscriptions', [])
        return jsonify({'status': 'success', 'subscriptions': subscriptions})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/config/subscription', methods=['POST'])
@require_api_key
@validate_request(UpdateSubscriptionRequest)
def update_subscription(validated_data: UpdateSubscriptionRequest):
    """更新订阅配置（使用 Pydantic 验证）"""
    try:
        # 读取配置文件
        config = load_config_safe()

        # 查找订阅
        subscription_found = False
        updated_fields = []

        for sub in config.get('subscriptions', []):
            if sub.get('name') == validated_data.name:
                # 更新名称
                if validated_data.new_name is not None:
                    sub['name'] = validated_data.new_name
                    updated_fields.append('name')

                # 更新周期类型
                if validated_data.cycle_type is not None:
                    sub['cycle_type'] = validated_data.cycle_type
                    updated_fields.append('cycle_type')

                # 更新续费日
                if validated_data.renewal_day is not None:
                    sub['renewal_day'] = validated_data.renewal_day
                    updated_fields.append('renewal_day')

                # 更新提醒天数
                if validated_data.alert_days_before is not None:
                    sub['alert_days_before'] = validated_data.alert_days_before
                    updated_fields.append('alert_days_before')

                # 更新金额
                if validated_data.amount is not None:
                    sub['amount'] = validated_data.amount
                    updated_fields.append('amount')

                # 更新货币
                if validated_data.currency is not None:
                    sub['currency'] = validated_data.currency
                    updated_fields.append('currency')

                # 更新启用状态
                if validated_data.enabled is not None:
                    sub['enabled'] = validated_data.enabled
                    updated_fields.append('enabled')

                # 更新最后续费日期
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
        _write_config(config)
        _audit_log('update_subscription', {
            'subscription': validated_data.name,
            'fields': updated_fields
        })

        # 立即重新检查一次，更新缓存
        refresh_subscription_cache(global_state_manager)

        return jsonify({
            'status': 'success',
            'message': f'订阅 [{validated_data.name}] 配置已更新',
            'updated_fields': updated_fields
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/subscription/add', methods=['POST'])
@require_api_key
@validate_request(AddSubscriptionRequest)
def add_subscription(validated_data: AddSubscriptionRequest):
    """添加新订阅（使用 Pydantic 验证）"""
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

        # 创建新订阅（从验证后的数据）
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
        _write_config(config)
        _audit_log('add_subscription', {
            'subscription': validated_data.name,
            'cycle_type': validated_data.cycle_type,
            'amount': validated_data.amount
        })

        # 立即重新检查一次，更新缓存
        refresh_subscription_cache(global_state_manager)

        return jsonify({
            'status': 'success',
            'message': f'订阅 [{name}] 已成功添加'
        })
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'数据格式错误: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/subscription/delete', methods=['POST', 'DELETE'])
@require_api_key
@validate_request(DeleteSubscriptionRequest)
def delete_subscription(validated_data: DeleteSubscriptionRequest):
    """删除订阅（使用 Pydantic 验证）"""
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
        _write_config(config)
        _audit_log('delete_subscription', {'subscription': validated_data.name})

        # 立即重新检查一次，更新缓存
        refresh_subscription_cache(global_state_manager)

        return jsonify({
            'status': 'success',
            'message': f'订阅 [{validated_data.name}] 已成功删除'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/subscription/mark_renewed', methods=['POST'])
@require_api_key
def mark_subscription_renewed():
    """标记订阅已续费"""
    try:
        data = request.get_json()
        subscription_name = data.get('name')
        renewed_date = data.get('renewed_date')  # 可选，默认使用今天
        
        if not subscription_name:
            return jsonify({
                'status': 'error',
                'message': '缺少订阅名称'
            }), 400
        
        # 如果没有提供续费日期，使用今天
        if not renewed_date:
            renewed_date = datetime.now().strftime('%Y-%m-%d')
        else:
            # 验证日期格式
            try:
                datetime.strptime(renewed_date, '%Y-%m-%d')
            except ValueError:
                return jsonify({
                    'status': 'error',
                    'message': '日期格式错误，应为 YYYY-MM-DD'
                }), 400
        
        # 读取配置文件
        config = load_config_safe()
        
        # 查找订阅并更新续费日期
        subscription_found = False
        for sub in config.get('subscriptions', []):
            if sub.get('name') == subscription_name:
                sub['last_renewed_date'] = renewed_date
                subscription_found = True
                break
        
        if not subscription_found:
            return jsonify({
                'status': 'error',
                'message': f'未找到订阅: {subscription_name}'
            }), 404

        # 保存配置文件
        _write_config(config)
        _audit_log('mark_renewed', {'subscription': subscription_name, 'renewed_date': renewed_date})

        # 立即重新检查一次，更新缓存
        refresh_subscription_cache(global_state_manager)

        return jsonify({
            'status': 'success',
            'message': f'订阅 [{subscription_name}] 已标记为已续费',
            'data': {
                'subscription_name': subscription_name,
                'renewed_date': renewed_date
            }
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/subscription/clear_renewed', methods=['POST'])
@require_api_key
def clear_subscription_renewed():
    """清除订阅续费标记"""
    try:
        data = request.get_json()
        subscription_name = data.get('name')
        
        if not subscription_name:
            return jsonify({
                'status': 'error',
                'message': '缺少订阅名称'
            }), 400
        
        # 读取配置文件
        config = load_config_safe()
        
        # 查找订阅并删除续费日期
        subscription_found = False
        for sub in config.get('subscriptions', []):
            if sub.get('name') == subscription_name:
                # 删除 last_renewed_date 字段
                if 'last_renewed_date' in sub:
                    del sub['last_renewed_date']
                subscription_found = True
                break
        
        if not subscription_found:
            return jsonify({
                'status': 'error',
                'message': f'未找到订阅: {subscription_name}'
            }), 404

        # 保存配置文件
        _write_config(config)
        _audit_log('clear_renewed', {'subscription': subscription_name})

        # 立即重新检查一次，更新缓存
        refresh_subscription_cache(global_state_manager)

        return jsonify({
            'status': 'success',
            'message': f'已取消订阅 [{subscription_name}] 的续费标记'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/config/threshold', methods=['POST'])
@require_api_key
def update_threshold():
    """更新项目的告警阈值"""
    try:
        data = request.get_json()
        project_name = data.get('project_name')
        new_threshold = data.get('threshold')
        
        if not project_name or new_threshold is None:
            return jsonify({
                'status': 'error',
                'message': '缺少必要参数: project_name 或 threshold'
            }), 400
        
        # 验证阈值是否为数字
        try:
            new_threshold = float(new_threshold)
            if new_threshold < 0:
                raise ValueError("阈值不能为负数")
        except (ValueError, TypeError) as e:
            return jsonify({
                'status': 'error',
                'message': '阈值必须为非负数'
            }), 400
        
        # 读取配置文件
        config = load_config_safe()
        
        # 查找并更新项目
        project_found = False
        for project in config.get('projects', []):
            if project.get('name') == project_name:
                old_threshold = project.get('threshold')
                project['threshold'] = new_threshold
                project_found = True
                break
        
        if not project_found:
            return jsonify({
                'status': 'error',
                'message': f'未找到项目: {project_name}'
            }), 404

        # 保存配置文件
        _write_config(config)
        _audit_log('update_threshold', {'project': project_name, 'old': old_threshold, 'new': new_threshold})

        # 立即重新检查一次，更新缓存
        try:
            monitor = CreditMonitor('config.json')
            monitor.run(dry_run=not get_enable_web_alarm())

            # 使用公共方法更新缓存（线程安全）
            update_balance_cache(monitor.results, global_state_manager)
        except Exception as e:
            logger.error(f'更新缓存失败: {e}')
        
        return jsonify({
            'status': 'success',
            'message': f'项目 [{project_name}] 阈值已更新: {old_threshold} -> {new_threshold}',
            'data': {
                'project_name': project_name,
                'old_threshold': old_threshold,
                'new_threshold': new_threshold
            }
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ==================== 历史数据与趋势分析 API ====================

@app.route('/api/history/balance', methods=['GET'])
@require_api_key
def get_balance_history():
    """
    获取余额历史记录

    查询参数:
        - project_id: 项目ID（可选）
        - provider: Provider类型（可选）
        - days: 查询天数（默认7天）
        - limit: 返回记录数限制（默认100）
    """
    if not DB_AVAILABLE:
        return jsonify({
            'status': 'error',
            'message': '数据库功能未启用'
        }), 503

    try:
        project_id = request.args.get('project_id')
        provider = request.args.get('provider')
        days = int(request.args.get('days', 7))
        limit = int(request.args.get('limit', 100))

        # 参数验证
        if days < 1 or days > 365:
            return jsonify({
                'status': 'error',
                'message': 'days 必须在 1-365 之间'
            }), 400

        if limit < 1 or limit > 1000:
            return jsonify({
                'status': 'error',
                'message': 'limit 必须在 1-1000 之间'
            }), 400

        history = BalanceRepository.get_balance_history(
            project_id=project_id,
            provider=provider,
            days=days,
            limit=limit
        )

        return jsonify({
            'status': 'success',
            'count': len(history),
            'data': history
        })

    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
    except Exception as e:
        logger.error(f"查询余额历史失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/history/trend/<project_id>', methods=['GET'])
@require_api_key
def get_balance_trend(project_id: str):
    """
    获取项目余额趋势分析

    路径参数:
        - project_id: 项目唯一标识

    查询参数:
        - days: 分析天数（默认30天）
    """
    if not DB_AVAILABLE:
        return jsonify({
            'status': 'error',
            'message': '数据库功能未启用'
        }), 503

    try:
        days = int(request.args.get('days', 30))

        if days < 1 or days > 365:
            return jsonify({
                'status': 'error',
                'message': 'days 必须在 1-365 之间'
            }), 400

        trend = BalanceRepository.get_balance_trend(project_id, days)

        if 'error' in trend:
            return jsonify({
                'status': 'error',
                'message': trend['error']
            }), 404 if trend['error'] == 'No data found' else 500

        return jsonify({
            'status': 'success',
            'data': trend
        })

    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
    except Exception as e:
        logger.error(f"获取余额趋势失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/history/alerts', methods=['GET'])
@require_api_key
def get_alert_history():
    """
    获取告警历史记录

    查询参数:
        - project_id: 项目ID（可选）
        - alert_type: 告警类型（可选）
        - days: 查询天数（默认7天）
        - limit: 返回记录数限制（默认50）
    """
    if not DB_AVAILABLE:
        return jsonify({
            'status': 'error',
            'message': '数据库功能未启用'
        }), 503

    try:
        project_id = request.args.get('project_id')
        alert_type = request.args.get('alert_type')
        days = int(request.args.get('days', 7))
        limit = int(request.args.get('limit', 50))

        if days < 1 or days > 365:
            return jsonify({
                'status': 'error',
                'message': 'days 必须在 1-365 之间'
            }), 400

        if limit < 1 or limit > 1000:
            return jsonify({
                'status': 'error',
                'message': 'limit 必须在 1-1000 之间'
            }), 400

        alerts = AlertRepository.get_recent_alerts(
            project_id=project_id,
            alert_type=alert_type,
            days=days,
            limit=limit
        )

        return jsonify({
            'status': 'success',
            'count': len(alerts),
            'data': alerts
        })

    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
    except Exception as e:
        logger.error(f"查询告警历史失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/history/stats', methods=['GET'])
@require_api_key
def get_alert_statistics():
    """
    获取告警统计信息

    查询参数:
        - days: 统计天数（默认30天）
    """
    if not DB_AVAILABLE:
        return jsonify({
            'status': 'error',
            'message': '数据库功能未启用'
        }), 503

    try:
        days = int(request.args.get('days', 30))

        if days < 1 or days > 365:
            return jsonify({
                'status': 'error',
                'message': 'days 必须在 1-365 之间'
            }), 400

        stats = AlertRepository.get_alert_statistics(days)

        if 'error' in stats:
            return jsonify({
                'status': 'error',
                'message': stats['error']
            }), 500

        return jsonify({
            'status': 'success',
            'data': stats
        })

    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
    except Exception as e:
        logger.error(f"获取告警统计失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/history/projects', methods=['GET'])
@require_api_key
def get_all_projects_summary():
    """
    获取所有项目的最新状态摘要
    """
    if not DB_AVAILABLE:
        return jsonify({
            'status': 'error',
            'message': '数据库功能未启用'
        }), 503

    try:
        summary = BalanceRepository.get_all_projects_summary()

        return jsonify({
            'status': 'success',
            'count': len(summary),
            'data': summary
        })

    except Exception as e:
        logger.error(f"获取项目摘要失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    # 从环境变量读取端口配置
    web_port = int(os.environ.get('WEB_PORT', '8080'))
    metrics_port = int(os.environ.get('METRICS_PORT', '9100'))

    # 注册信号处理器实现优雅关闭
    def _shutdown_handler(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info(f"收到 {sig_name} 信号，正在优雅关闭...")
        _stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    # 启动配置文件监听器
    start_config_watcher('config.json')

    try:
        # 启动后台更新线程
        update_thread = threading.Thread(target=update_credits, daemon=True)
        update_thread.start()
        
        # 启动独立的 Prometheus Metrics 服务器
        from prometheus_client import start_http_server
        logger.info(f"📊 启动 Prometheus Metrics 服务器...")
        logger.info(f"🔗 Metrics 端点: http://localhost:{metrics_port}/metrics")
        start_http_server(metrics_port)
        
        # 启动 Flask 服务器
        logger.info(f"\n🚀 余额监控 Web 服务器启动中...")
        logger.info(f"📊 访问地址: http://localhost:{web_port}")
        if get_enable_web_alarm():
            logger.warning("⚠️  告警模式: 已启用（Web 会发送真实告警）")
        else:
            logger.info("🔕 告警模式: 仅查询（不发送告警，由定时任务负责）")
        logger.info("ℹ️  要启用 Web 告警，请设置环境变量: ENABLE_WEB_ALARM=true")
        logger.info("🔄 配置文件自动重载已启用")
        logger.info("")
        try:
            from waitress import serve
            logger.info("使用 waitress 生产服务器")
            serve(app, host='0.0.0.0', port=web_port)
        except ImportError:
            logger.warning("waitress 未安装，使用 Flask 开发服务器")
            app.run(host='0.0.0.0', port=web_port, debug=False)
        
    finally:
        # 优雅关闭：通知后台线程停止
        _stop_event.set()
        # 停止配置文件监听器
        stop_config_watcher()
        logger.info("服务已关闭")
