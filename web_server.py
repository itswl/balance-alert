#!/usr/bin/env python3
"""
余额监控 Web 服务器
提供实时余额查询的 HTTP API
"""
from flask import Flask, jsonify, render_template, send_from_directory, request
from flask_cors import CORS
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from monitor import CreditMonitor
from subscription_checker import SubscriptionChecker
from prometheus_exporter import metrics_endpoint, metrics_collector
from logger import get_logger
from config_loader import get_config, start_config_watcher, stop_config_watcher
from state_manager import state_manager
import threading
import time

# 创建 logger
logger = get_logger('web_server')

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# 配置：是否在 Web 模式下发送真实告警（默认不发送，避免重复告警）
# 如果需要 Web 也发送告警，设置环境变量 ENABLE_WEB_ALARM=true
ENABLE_WEB_ALARM = os.environ.get('ENABLE_WEB_ALARM', 'false').lower() == 'true'

# 使用 state_manager 替代全局变量
# 线程锁已在 state_manager 内部处理

def get_refresh_interval() -> int:
    """从配置文件读取刷新间隔，默认3600秒（60分钟）"""
    try:
        config = get_config('config.json')
        interval = config.get('settings', {}).get('balance_refresh_interval_seconds', 3600)
        return max(60, interval)  # 最小60秒（1分钟）
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"读取刷新间隔配置失败，使用默认值3600秒: {e}")
        return 3600


def update_balance_cache(results: List[Dict[str, Any]]) -> None:
    """更新余额缓存（使用状态管理器）"""
    state_manager.update_balance_state(results)


def update_subscription_cache(results: List[Dict[str, Any]]) -> None:
    """更新订阅缓存（使用状态管理器）"""
    state_manager.update_subscription_state(results)


def save_cache_file(balance_results: List[Dict[str, Any]], subscription_results: List[Dict[str, Any]]) -> None:
    """保存缓存到文件（使用状态管理器）"""
    # 状态管理器会自动处理保存逻辑
    state_manager.save_to_cache()


def update_credits():
    """后台定时更新余额数据"""
    while True:
        try:
            # 更新余额/积分数据
            monitor = CreditMonitor('config.json')
            monitor.run(dry_run=not ENABLE_WEB_ALARM)
            
            # 更新缓存
            update_balance_cache(monitor.results)
            
            # 更新订阅数据
            subscription_checker = SubscriptionChecker('config.json')
            subscription_checker.check_subscriptions(dry_run=not ENABLE_WEB_ALARM)
            
            # 更新缓存
            update_subscription_cache(subscription_checker.results)
            
            # 更新 Prometheus 指标
            metrics_collector.update_balance_metrics(monitor.results)
            metrics_collector.update_subscription_metrics(subscription_checker.results)
            
            # 保存缓存到文件
            save_cache_file(monitor.results, subscription_checker.results)
            
        except (RuntimeError, ValueError, KeyError) as e:
            logger.error(f"更新数据失败: {e}", exc_info=True)
            metrics_collector.set_check_failed('balance')
        
        # 根据配置间隔等待
        sleep_seconds = get_refresh_interval()
        logger.info(f"下次更新将在 {sleep_seconds} 秒后")
        time.sleep(sleep_seconds)

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/health')
def health():
    """健康检查端点"""
    has_data = state_manager.has_data()
    
    status = {
        'status': 'ok' if has_data else 'initializing',
        'timestamp': time.time(),
        'has_data': has_data,
        'web_alarm_enabled': ENABLE_WEB_ALARM
    }
    
    # 如果有数据，返回 200；否则返回 503（服务暂不可用）
    code = 200 if has_data else 503
    return jsonify(status), code

@app.route('/api/credits')
def get_credits():
    """获取所有项目余额"""
    return jsonify(state_manager.get_balance_state())

@app.route('/api/refresh')
def refresh_credits():
    """手动刷新余额"""
    try:
        # 刷新余额/积分
        monitor = CreditMonitor('config.json')
        monitor.run(dry_run=not ENABLE_WEB_ALARM)
        
        # 使用公共方法更新缓存
        update_balance_cache(monitor.results)
        
        # 刷新订阅
        subscription_checker = SubscriptionChecker('config.json')
        subscription_checker.check_subscriptions(dry_run=not ENABLE_WEB_ALARM)
        
        # 使用公共方法更新缓存
        update_subscription_cache(subscription_checker.results)
        
        # 更新 Prometheus 指标
        metrics_collector.update_balance_metrics(monitor.results)
        metrics_collector.update_subscription_metrics(subscription_checker.results)
        
        # 保存缓存到文件
        save_cache_file(monitor.results, subscription_checker.results)
        
        # 返回最新的状态数据
        balance_state = state_manager.get_balance_state()
        subscription_state = state_manager.get_subscription_state()
        
        return jsonify({
            'status': 'success', 
            'data': {
                'last_update': balance_state.get('last_update'),
                'projects': balance_state.get('projects', []),
                'summary': balance_state.get('summary', {}),
                'subscriptions': subscription_state.get('subscriptions', [])
            }
        })
    except (RuntimeError, ValueError, KeyError) as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/config/projects', methods=['GET'])
def load_config_safe(config_path='config.json'):
    """安全加载配置文件"""
    try:
        from config_loader import load_config_with_env_vars
        return load_config_with_env_vars(config_path)
    except Exception as e:
        logger.error(f"配置加载失败: {e}")
        return {}


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
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/subscriptions')
def get_subscriptions():
    """获取订阅数据"""
    return jsonify(state_manager.get_subscription_state())

@app.route('/api/config/subscriptions', methods=['GET'])
def get_subscriptions_config():
    """获取所有订阅配置"""
    try:
        config = load_config_safe()
        subscriptions = config.get('subscriptions', [])
        return jsonify({'status': 'success', 'subscriptions': subscriptions})
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/config/subscription', methods=['POST'])
def update_subscription():
    """更新订阅配置"""
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
        
        # 查找订阅
        subscription_found = False
        for sub in config.get('subscriptions', []):
            if sub.get('name') == subscription_name:
                # 更新周期类型
                if 'cycle_type' in data:
                    cycle_type = data['cycle_type']
                    if cycle_type not in ['weekly', 'monthly', 'yearly']:
                        return jsonify({
                            'status': 'error',
                            'message': '周期类型必须是 weekly、monthly 或 yearly'
                        }), 400
                    sub['cycle_type'] = cycle_type
                
                # 更新字段
                if 'renewal_day' in data:
                    renewal_day = int(data['renewal_day'])
                    cycle_type = sub.get('cycle_type', 'monthly')
                    
                    # 根据周期类型验证
                    if cycle_type == 'weekly' and (renewal_day < 1 or renewal_day > 7):
                        return jsonify({
                            'status': 'error',
                            'message': '周周期的续费日期必须在 1-7 之间'
                        }), 400
                    elif (cycle_type == 'monthly' or cycle_type == 'yearly') and (renewal_day < 1 or renewal_day > 31):
                        return jsonify({
                            'status': 'error',
                            'message': '续费日期必须在 1-31 之间'
                        }), 400
                    
                    sub['renewal_day'] = renewal_day
                
                # 如果是年周期且提供了月份，更新 last_renewed_date
                if 'renewal_month' in data and sub.get('cycle_type') == 'yearly':
                    from datetime import datetime
                    renewal_month = int(data['renewal_month'])
                    renewal_day = sub.get('renewal_day', 1)
                    current_year = datetime.now().year
                    
                    try:
                        # 设置一个基准日期（使用当前年份或去年）
                        base_date = datetime(current_year, renewal_month, renewal_day)
                        # 如果这个日期还没到，使用去年
                        if base_date > datetime.now():
                            base_date = datetime(current_year - 1, renewal_month, renewal_day)
                        sub['last_renewed_date'] = base_date.strftime('%Y-%m-%d')
                    except ValueError:
                        return jsonify({
                            'status': 'error',
                            'message': f'{renewal_month}月{renewal_day}日不是有效日期'
                        }), 400
                
                if 'alert_days_before' in data:
                    alert_days = int(data['alert_days_before'])
                    if alert_days < 0:
                        return jsonify({
                            'status': 'error',
                            'message': '提醒天数不能为负数'
                        }), 400
                    sub['alert_days_before'] = alert_days
                
                if 'amount' in data:
                    amount = float(data['amount'])
                    if amount < 0:
                        return jsonify({
                            'status': 'error',
                            'message': '金额不能为负数'
                        }), 400
                    sub['amount'] = amount
                
                if 'currency' in data:
                    sub['currency'] = data['currency']
                
                subscription_found = True
                break
        
        if not subscription_found:
            return jsonify({
                'status': 'error',
                'message': f'未找到订阅: {subscription_name}'
            }), 404
        
        # 保存配置文件
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        # 立即重新检查一次，更新缓存
        try:
            subscription_checker = SubscriptionChecker('config.json')
            subscription_checker.check_subscriptions(dry_run=not ENABLE_WEB_ALARM)
            
            # 使用公共方法更新缓存（线程安全）
            update_subscription_cache(subscription_checker.results)
        except Exception as e:
            logger.error(f'更新订阅缓存失败: {e}')
        
        return jsonify({
            'status': 'success',
            'message': f'订阅 [{subscription_name}] 配置已更新'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/subscription/add', methods=['POST'])
def add_subscription():
    """添加新订阅"""
    try:
        data = request.get_json()
        
        # 验证必填字段
        required_fields = ['name', 'renewal_day', 'alert_days_before', 'amount', 'currency']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'status': 'error',
                    'message': f'缺少必填字段: {field}'
                }), 400
        
        # 验证数据有效性
        name = data['name'].strip()
        if not name:
            return jsonify({
                'status': 'error',
                'message': '订阅名称不能为空'
            }), 400
        
        cycle_type = data.get('cycle_type', 'monthly')
        if cycle_type not in ['weekly', 'monthly', 'yearly']:
            return jsonify({
                'status': 'error',
                'message': '周期类型必须是 weekly、monthly 或 yearly'
            }), 400
        
        renewal_day = int(data['renewal_day'])
        # 根据周期类型验证续费日
        if cycle_type == 'weekly' and (renewal_day < 1 or renewal_day > 7):
            return jsonify({
                'status': 'error',
                'message': '周周期的续费日期必须在 1-7 之间'
            }), 400
        elif cycle_type == 'monthly' and (renewal_day < 1 or renewal_day > 31):
            return jsonify({
                'status': 'error',
                'message': '月周期的续费日期必须在 1-31 之间'
            }), 400
        
        alert_days = int(data['alert_days_before'])
        if alert_days < 0:
            return jsonify({
                'status': 'error',
                'message': '提醒天数不能为负数'
            }), 400
        
        amount = float(data['amount'])
        if amount < 0:
            return jsonify({
                'status': 'error',
                'message': '金额不能为负数'
            }), 400
        
        # 读取配置文件
        config = load_config_safe()
        
        # 检查订阅名称是否已存在
        subscriptions = config.get('subscriptions', [])
        for sub in subscriptions:
            if sub.get('name') == name:
                return jsonify({
                    'status': 'error',
                    'message': f'订阅名称 [{name}] 已存在'
                }), 400
        
        # 创建新订阅
        new_subscription = {
            'name': name,
            'cycle_type': cycle_type,
            'renewal_day': renewal_day,
            'alert_days_before': alert_days,
            'amount': amount,
            'currency': data['currency'],
            'enabled': data.get('enabled', True)
        }
        
        # 如果是年周期且提供了月份，设置 last_renewed_date
        if cycle_type == 'yearly' and 'renewal_month' in data:
            from datetime import datetime
            renewal_month = int(data['renewal_month'])
            current_year = datetime.now().year
            
            try:
                # 设置基准日期
                base_date = datetime(current_year, renewal_month, renewal_day)
                # 如果这个日期还没到，使用去年
                if base_date > datetime.now():
                    base_date = datetime(current_year - 1, renewal_month, renewal_day)
                new_subscription['last_renewed_date'] = base_date.strftime('%Y-%m-%d')
            except ValueError:
                return jsonify({
                    'status': 'error',
                    'message': f'{renewal_month}月{renewal_day}日不是有效日期'
                }), 400
        
        # 添加到配置
        subscriptions.append(new_subscription)
        config['subscriptions'] = subscriptions
        
        # 保存配置文件
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        # 立即重新检查一次，更新缓存
        try:
            subscription_checker = SubscriptionChecker('config.json')
            subscription_checker.check_subscriptions(dry_run=not ENABLE_WEB_ALARM)
            
            # 使用公共方法更新缓存（线程安全）
            update_subscription_cache(subscription_checker.results)
        except Exception as e:
            logger.error(f'更新订阅缓存失败: {e}')
        
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

@app.route('/api/subscription/delete', methods=['POST'])
def delete_subscription():
    """删除订阅"""
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
        
        # 查找并删除订阅
        subscriptions = config.get('subscriptions', [])
        subscription_found = False
        new_subscriptions = []
        
        for sub in subscriptions:
            if sub.get('name') == subscription_name:
                subscription_found = True
                # 跳过该订阅，不添加到新列表中
                continue
            new_subscriptions.append(sub)
        
        if not subscription_found:
            return jsonify({
                'status': 'error',
                'message': f'未找到订阅: {subscription_name}'
            }), 404
        
        # 更新配置
        config['subscriptions'] = new_subscriptions
        
        # 保存配置文件
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        # 立即重新检查一次，更新缓存
        try:
            subscription_checker = SubscriptionChecker('config.json')
            subscription_checker.check_subscriptions(dry_run=not ENABLE_WEB_ALARM)
            
            # 使用公共方法更新缓存（线程安全）
            update_subscription_cache(subscription_checker.results)
        except Exception as e:
            logger.error(f'更新订阅缓存失败: {e}')
        
        return jsonify({
            'status': 'success',
            'message': f'订阅 [{subscription_name}] 已成功删除'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/subscription/mark_renewed', methods=['POST'])
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
            from datetime import datetime
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
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        # 立即重新检查一次，更新缓存
        try:
            subscription_checker = SubscriptionChecker('config.json')
            subscription_checker.check_subscriptions(dry_run=not ENABLE_WEB_ALARM)
            
            # 使用公共方法更新缓存（线程安全）
            update_subscription_cache(subscription_checker.results)
        except Exception as e:
            logger.error(f'更新订阅缓存失败: {e}')
        
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
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        # 立即重新检查一次，更新缓存
        try:
            subscription_checker = SubscriptionChecker('config.json')
            subscription_checker.check_subscriptions(dry_run=not ENABLE_WEB_ALARM)
            
            # 使用公共方法更新缓存（线程安全）
            update_subscription_cache(subscription_checker.results)
        except Exception as e:
            logger.error(f'更新订阅缓存失败: {e}')
        
        return jsonify({
            'status': 'success',
            'message': f'已取消订阅 [{subscription_name}] 的续费标记'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/config/threshold', methods=['POST'])
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
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        # 立即重新检查一次，更新缓存
        try:
            monitor = CreditMonitor('config.json')
            monitor.run(dry_run=not ENABLE_WEB_ALARM)
            
            # 使用公共方法更新缓存（线程安全）
            update_balance_cache(monitor.results)
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

if __name__ == '__main__':
    # 从环境变量读取端口配置
    web_port = int(os.environ.get('WEB_PORT', '8080'))
    metrics_port = int(os.environ.get('METRICS_PORT', '9100'))
    
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
        if ENABLE_WEB_ALARM:
            logger.warning("⚠️  告警模式: 已启用（Web 会发送真实告警）")
        else:
            logger.info("🔕 告警模式: 仅查询（不发送告警，由定时任务负责）")
        logger.info("ℹ️  要启用 Web 告警，请设置环境变量: ENABLE_WEB_ALARM=true")
        logger.info("🔄 配置文件自动重载已启用")
        logger.info("")
        app.run(host='0.0.0.0', port=web_port, debug=False)
        
    finally:
        # 程序退出时停止监听器
        stop_config_watcher()
