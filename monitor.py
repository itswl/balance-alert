#!/usr/bin/env python3
"""
多项目余额监控主程序
支持配置驱动的多项目余额检查和告警
"""
import json
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from providers import get_provider
from subscription_checker import SubscriptionChecker
from email_scanner import EmailScanner
from webhook_adapter import WebhookAdapter
from logger import get_logger

# 创建 logger
logger = get_logger('monitor')


class CreditMonitor:
    """余额监控器"""
    
    def __init__(self, config_path='config.json'):
        """
        初始化监控器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.results = []
    
    def _load_config(self):
        """加载配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误: {e}")
    
    def check_project(self, project_config, dry_run=False):
        """
        检查单个项目的余额
        
        Args:
            project_config: 项目配置字典
            dry_run: 是否为测试模式（不发送告警）
            
        Returns:
            dict: 检查结果
        """
        project_name = project_config.get('name', 'Unknown')
        provider_name = project_config.get('provider')
        api_key = project_config.get('api_key')
        threshold = project_config.get('threshold', 0)
        
        print(f"\n{'='*60}")
        print(f"📊 检查项目: {project_name}")
        print(f"   服务商: {provider_name}")
        print(f"   告警阈值: {threshold}")
        print(f"{'='*60}")
        
        # 获取服务商适配器
        try:
            provider_class = get_provider(provider_name)
            provider = provider_class(api_key)
        except ValueError as e:
            error_msg = str(e)
            print(f"❌ {error_msg}")
            return {
                'project': project_name,
                'success': False,
                'error': error_msg,
                'alarm_sent': False
            }
        
        # 获取余额
        result = provider.get_credits()
        
        if not result['success']:
            print(f"❌ 获取余额失败: {result['error']}")
            return {
                'project': project_name,
                'success': False,
                'error': result['error'],
                'alarm_sent': False
            }
        
        credits = result['credits']
        print(f"✅ 当前余额: {credits}")
        
        # 检查是否需要告警
        need_alarm = credits < threshold
        alarm_sent = False
        
        if need_alarm:
            print(f"⚠️  余额不足! {credits} < {threshold}")
            
            if not dry_run:
                alarm_sent = self._send_alarm(project_config, credits)
            else:
                print("🔍 [测试模式] 跳过发送告警")
        else:
            print(f"✅ 余额充足: {credits} >= {threshold}")
        
        return {
            'project': project_name,
            'provider': provider_name,
            'type': project_config.get('type'),  # 传递类型字段到前端
            'success': True,
            'credits': credits,
            'threshold': threshold,
            'need_alarm': need_alarm,
            'alarm_sent': alarm_sent,
            'error': None
        }
    
    def _send_alarm(self, project_config, credits):
        """
        发送告警到 webhook
        
        Args:
            project_config: 项目配置
            credits: 当前余额
            
        Returns:
            bool: 是否发送成功
        """
        webhook_config = self.config.get('webhook', {})
        webhook_url = webhook_config.get('url')
        webhook_type = webhook_config.get('type', 'custom')
        webhook_source = webhook_config.get('source', 'credit-monitor')
        
        if not webhook_url:
            print("❌ 未配置 webhook 地址")
            return False
        
        # 创建 webhook 适配器
        adapter = WebhookAdapter(webhook_url, webhook_type, webhook_source)
        
        # 获取项目信息
        project_name = project_config.get('name')
        provider = project_config.get('provider')
        threshold = project_config.get('threshold')
        balance_type = '余额' if project_config.get('type') == 'balance' else '积分'
        unit = '￥' if project_config.get('type') == 'balance' else ''
        
        # 发送告警
        return adapter.send_balance_alert(
            project_name=project_name,
            provider=provider,
            balance_type=balance_type,
            current_value=credits,
            threshold=threshold,
            unit=unit
        )
    
    def run(self, project_name=None, dry_run=False):
        """
        运行监控检查
        
        Args:
            project_name: 指定项目名称，None 表示检查所有启用的项目
            dry_run: 测试模式，不发送告警
        """
        projects = self.config.get('projects', [])
        
        if not projects:
            print("⚠️  配置文件中没有项目")
            return
        
        # 过滤项目
        if project_name:
            projects = [p for p in projects if p.get('name') == project_name]
            if not projects:
                print(f"❌ 未找到项目: {project_name}")
                return
        else:
            projects = [p for p in projects if p.get('enabled', True)]
        
        print(f"\n🚀 开始监控 {len(projects)} 个项目...")
        if dry_run:
            print("🔍 [测试模式] 不会发送实际告警\n")
        
        # 使用线程池并发检查项目（最多5个并发）
        max_workers = min(5, len(projects))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_project = {
                executor.submit(self.check_project, project, dry_run): project 
                for project in projects
            }
            
            # 收集结果
            for future in as_completed(future_to_project):
                project = future_to_project[future]
                try:
                    result = future.result()
                    self.results.append(result)
                except Exception as e:
                    logger.error(f"❌ 检查项目 {project.get('name', 'Unknown')} 时发生错误: {e}", exc_info=True)
                    self.results.append({
                        'project': project.get('name', 'Unknown'),
                        'success': False,
                        'error': str(e),
                        'alarm_sent': False
                    })
        
        # 输出汇总
        self._print_summary()
    
    def _print_summary(self):
        """打印检查汇总"""
        print(f"\n\n{'='*60}")
        print("📋 检查汇总")
        print(f"{'='*60}")
        
        total = len(self.results)
        success = sum(1 for r in self.results if r['success'])
        failed = total - success
        need_alarm = sum(1 for r in self.results if r.get('need_alarm', False))
        alarm_sent = sum(1 for r in self.results if r.get('alarm_sent', False))
        
        print(f"总项目数: {total}")
        print(f"检查成功: {success}")
        print(f"检查失败: {failed}")
        print(f"需要告警: {need_alarm}")
        print(f"告警已发送: {alarm_sent}")
        
        # 详细列表
        if self.results:
            print(f"\n详细结果:")
            for r in self.results:
                status = "✅" if r['success'] else "❌"
                project = r['project']
                
                if r['success']:
                    credits = r['credits']
                    threshold = r['threshold']
                    alarm_status = "🔔已告警" if r.get('alarm_sent') else ("⚠️需告警" if r.get('need_alarm') else "✅正常")
                    print(f"  {status} {project}: {credits} / {threshold} - {alarm_status}")
                else:
                    error = r.get('error', 'Unknown error')
                    print(f"  {status} {project}: {error}")
        
        print(f"{'='*60}\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='多项目余额监控工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                          # 检查所有启用的项目
  %(prog)s --project "项目A"        # 检查指定项目
  %(prog)s --dry-run                # 测试模式，不发送告警
  %(prog)s --config custom.json     # 使用自定义配置文件
  %(prog)s --check-subscriptions    # 检查订阅续费提醒
  %(prog)s --check-email            # 扫描邮箱告警邮件
  %(prog)s --check-email --email-days 3  # 扫描最近3天的邮件
        """
    )
    
    parser.add_argument(
        '--config',
        default='config.json',
        help='配置文件路径 (默认: config.json)'
    )
    
    parser.add_argument(
        '--project',
        help='指定要检查的项目名称'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='测试模式，只显示余额不发送告警'
    )
    
    parser.add_argument(
        '--check-subscriptions',
        action='store_true',
        help='检查订阅续费提醒'
    )
    
    parser.add_argument(
        '--check-email',
        action='store_true',
        help='扫描邮箱告警邮件'
    )
    
    parser.add_argument(
        '--email-days',
        type=int,
        default=1,
        help='扫描最近几天的邮件 (默认: 1天)'
    )
    
    args = parser.parse_args()
    
    try:
        # 检查余额/积分
        monitor = CreditMonitor(args.config)
        monitor.run(project_name=args.project, dry_run=args.dry_run)
        
        # 检查订阅续费（默认启用）
        if args.check_subscriptions or args.project is None:
            print("\n" + "="*60)
            subscription_checker = SubscriptionChecker(args.config)
            subscription_checker.check_subscriptions(dry_run=args.dry_run)
        
        # 扫描邮箱（如果指定）
        if args.check_email:
            print("\n" + "="*60)
            email_scanner = EmailScanner(args.config)
            email_scanner.scan_emails(days=args.email_days, dry_run=args.dry_run)
            
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
