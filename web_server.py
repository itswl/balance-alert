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
from monitor import CreditMonitor
from subscription_checker import SubscriptionChecker
import threading
import time

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# 配置：是否在 Web 模式下发送真实告警（默认不发送，避免重复告警）
# 如果需要 Web 也发送告警，设置环境变量 ENABLE_WEB_ALARM=true
ENABLE_WEB_ALARM = os.environ.get('ENABLE_WEB_ALARM', 'false').lower() == 'true'

# 全局变量存储最新的监控结果
latest_results = {
    'last_update': None,
    'projects': [],
    'summary': {}
}

# 全局变量存储订阅检查结果
latest_subscriptions = {
    'last_update': None,
    'subscriptions': [],
    'summary': {}
}

def update_credits():
    """后台定时更新余额数据"""
    global latest_results, latest_subscriptions
    
    while True:
        try:
            # 更新余额/积分数据
            monitor = CreditMonitor('config.json')
            monitor.run(dry_run=not ENABLE_WEB_ALARM)
            
            latest_results = {
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
                'projects': monitor.results,
                'summary': {
                    'total': len(monitor.results),
                    'success': sum(1 for r in monitor.results if r['success']),
                    'failed': sum(1 for r in monitor.results if not r['success']),
                    'need_alarm': sum(1 for r in monitor.results if r.get('need_alarm', False)),
                }
            }
            
            # 更新订阅数据
            subscription_checker = SubscriptionChecker('config.json')
            subscription_checker.check_subscriptions(dry_run=not ENABLE_WEB_ALARM)
            
            latest_subscriptions = {
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
                'subscriptions': subscription_checker.results,
                'summary': {
                    'total': len(subscription_checker.results),
                    'need_alert': sum(1 for r in subscription_checker.results if r.get('need_alert', False)),
                }
            }
            
        except Exception as e:
            print(f"更新数据失败: {e}")
        
        # 每 60 分钟更新一次
        time.sleep(60 * 60)

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/api/credits')
def get_credits():
    """获取所有项目余额"""
    return jsonify(latest_results)

@app.route('/api/refresh')
def refresh_credits():
    """手动刷新余额"""
    try:
        # 刷新余额/积分
        monitor = CreditMonitor('config.json')
        monitor.run(dry_run=not ENABLE_WEB_ALARM)
        
        global latest_results, latest_subscriptions
        latest_results = {
            'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
            'projects': monitor.results,
            'summary': {
                'total': len(monitor.results),
                'success': sum(1 for r in monitor.results if r['success']),
                'failed': sum(1 for r in monitor.results if not r['success']),
                'need_alarm': sum(1 for r in monitor.results if r.get('need_alarm', False)),
            }
        }
        
        # 刷新订阅
        subscription_checker = SubscriptionChecker('config.json')
        subscription_checker.check_subscriptions(dry_run=not ENABLE_WEB_ALARM)
        
        latest_subscriptions = {
            'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
            'subscriptions': subscription_checker.results,
            'summary': {
                'total': len(subscription_checker.results),
                'need_alert': sum(1 for r in subscription_checker.results if r.get('need_alert', False)),
            }
        }
        
        return jsonify({'status': 'success', 'data': latest_results})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/config/projects', methods=['GET'])
def get_projects_config():
    """获取所有项目配置"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
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
    return jsonify(latest_subscriptions)

@app.route('/api/config/subscriptions', methods=['GET'])
def get_subscriptions_config():
    """获取所有订阅配置"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        subscriptions = config.get('subscriptions', [])
        return jsonify({'status': 'success', 'subscriptions': subscriptions})
    except Exception as e:
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
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
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
            
            global latest_subscriptions
            latest_subscriptions = {
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
                'subscriptions': subscription_checker.results,
                'summary': {
                    'total': len(subscription_checker.results),
                    'need_alert': sum(1 for r in subscription_checker.results if r.get('need_alert', False)),
                }
            }
        except Exception as e:
            print(f'更新订阅缓存失败: {e}')
        
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
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
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
            
            global latest_subscriptions
            latest_subscriptions = {
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
                'subscriptions': subscription_checker.results,
                'summary': {
                    'total': len(subscription_checker.results),
                    'need_alert': sum(1 for r in subscription_checker.results if r.get('need_alert', False)),
                }
            }
        except Exception as e:
            print(f'更新订阅缓存失败: {e}')
        
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
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
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
            
            global latest_subscriptions
            latest_subscriptions = {
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
                'subscriptions': subscription_checker.results,
                'summary': {
                    'total': len(subscription_checker.results),
                    'need_alert': sum(1 for r in subscription_checker.results if r.get('need_alert', False)),
                }
            }
        except Exception as e:
            print(f'更新订阅缓存失败: {e}')
        
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
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
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
            
            global latest_subscriptions
            latest_subscriptions = {
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
                'subscriptions': subscription_checker.results,
                'summary': {
                    'total': len(subscription_checker.results),
                    'need_alert': sum(1 for r in subscription_checker.results if r.get('need_alert', False)),
                }
            }
        except Exception as e:
            print(f'更新订阅缓存失败: {e}')
        
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
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
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
            
            global latest_subscriptions
            latest_subscriptions = {
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
                'subscriptions': subscription_checker.results,
                'summary': {
                    'total': len(subscription_checker.results),
                    'need_alert': sum(1 for r in subscription_checker.results if r.get('need_alert', False)),
                }
            }
        except Exception as e:
            print(f'更新订阅缓存失败: {e}')
        
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
                raise ValueError()
        except:
            return jsonify({
                'status': 'error',
                'message': '阈值必须为非负数'
            }), 400
        
        # 读取配置文件
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
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
            
            global latest_results
            latest_results = {
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
                'projects': monitor.results,
                'summary': {
                    'total': len(monitor.results),
                    'success': sum(1 for r in monitor.results if r['success']),
                    'failed': sum(1 for r in monitor.results if not r['success']),
                    'need_alarm': sum(1 for r in monitor.results if r.get('need_alarm', False)),
                }
            }
        except Exception as e:
            print(f'更新缓存失败: {e}')
        
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
    # 启动后台更新线程
    update_thread = threading.Thread(target=update_credits, daemon=True)
    update_thread.start()
    
    # 启动 Flask 服务器
    print("🚀 余额监控 Web 服务器启动中...")
    print("📊 访问地址: http://localhost:8080")
    if ENABLE_WEB_ALARM:
        print("⚠️  告警模式: 已启用（Web 会发送真实告警）")
    else:
        print("🔕 告警模式: 仅查询（不发送告警，由定时任务负责）")
    print("ℹ️  要启用 Web 告警，请设置环境变量: ENABLE_WEB_ALARM=true")
    print()
    app.run(host='0.0.0.0', port=8080, debug=False)
