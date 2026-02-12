#!/usr/bin/env python3
"""
异步版本的余额监控器
使用 asyncio 提高并发效率，为未来性能优化做准备
"""
import asyncio
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List
from providers import get_provider
from subscription_checker import SubscriptionChecker
from email_scanner import EmailScanner
from webhook_adapter import WebhookAdapter
from logger import get_logger
from config_loader import load_config_with_env_vars

# 创建 logger
logger = get_logger('async_monitor')


class AsyncCreditMonitor:
    """异步余额监控器"""
    
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
            return load_config_with_env_vars(str(self.config_path))
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误: {e}")
    
    def _get_max_concurrent_checks(self):
        """获取最大并发检查数，默认为10（异步版本可以更高）"""
        try:
            max_concurrent = self.config.get('settings', {}).get('max_concurrent_checks', 10)
            return max(1, min(max_concurrent, 50))  # 异步版本允许更高的并发数
        except (TypeError, ValueError):
            return 10
    
    async def check_project_async(self, project_config: Dict[str, Any], dry_run: bool = False):
        """
        异步检查单个项目的余额
        
        Args:
            project_config: 项目配置字典
            dry_run: 是否为测试模式
            
        Returns:
            dict: 检查结果
        """
        project_name = project_config.get('name', 'Unknown')
        provider_name = project_config.get('provider')
        api_key = project_config.get('api_key')
        threshold = project_config.get('threshold', 0)
        
        logger.info(f"📊 检查项目: {project_name} ({provider_name})")
        
        # 获取服务商适配器
        try:
            provider_class = get_provider(provider_name)
            provider = provider_class(api_key)
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"❌ {error_msg}")
            return {
                'project': project_name,
                'success': False,
                'error': error_msg,
                'alarm_sent': False
            }
        
        # 获取余额（这里需要 Provider 支持异步方法）
        try:
            # TODO: 需要将 Provider 的 get_credits 方法改为异步
            # result = await provider.get_credits_async()
            result = provider.get_credits()  # 当前还是同步调用
        except Exception as e:
            logger.error(f"❌ 获取余额失败: {e}")
            return {
                'project': project_name,
                'success': False,
                'error': str(e),
                'alarm_sent': False
            }
        
        if not result['success']:
            logger.error(f"❌ 获取余额失败: {result['error']}")
            return {
                'project': project_name,
                'success': False,
                'error': result['error'],
                'alarm_sent': False
            }
        
        credits = result['credits']
        logger.info(f"✅ 当前余额: {credits}")
        
        # 检查是否需要告警
        need_alarm = credits < threshold
        alarm_sent = False
        
        if need_alarm:
            logger.warning(f"⚠️  余额不足! {credits} < {threshold}")
            
            if not dry_run:
                alarm_sent = self._send_alarm(project_config, credits)
            else:
                logger.info("🔍 [测试模式] 跳过发送告警")
        else:
            logger.info(f"✅ 余额充足: {credits} >= {threshold}")
        
        return {
            'project': project_name,
            'provider': provider_name,
            'type': project_config.get('type'),
            'success': True,
            'credits': credits,
            'threshold': threshold,
            'need_alarm': need_alarm,
            'alarm_sent': alarm_sent,
            'error': None
        }
    
    def _send_alarm(self, project_config: Dict[str, Any], credits: float) -> bool:
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
            logger.error("❌ 未配置 webhook 地址")
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
    
    async def run_async(self, project_name: str = None, dry_run: bool = False):
        """
        异步运行监控检查
        
        Args:
            project_name: 指定项目名称，None 表示检查所有启用的项目
            dry_run: 测试模式，不发送告警
        """
        projects = self.config.get('projects', [])
        
        if not projects:
            logger.warning("⚠️  配置文件中没有项目")
            return
        
        # 过滤项目
        if project_name:
            projects = [p for p in projects if p.get('name') == project_name]
            if not projects:
                print(f"❌ 未找到项目: {project_name}")
                return
        else:
            projects = [p for p in projects if p.get('enabled', True)]
        
        print(f"\n🚀 开始异步监控 {len(projects)} 个项目...")
        if dry_run:
            print("🔍 [测试模式] 不会发送实际告警\n")
        
        # 获取配置的并发数
        max_concurrent = self._get_max_concurrent_checks()
        semaphore = asyncio.Semaphore(max_concurrent)
        
        print(f"⚙️  最大并发数: {max_concurrent}")
        
        async def check_with_semaphore(project):
            async with semaphore:
                return await self.check_project_async(project, dry_run)
        
        # 创建所有任务
        tasks = [check_with_semaphore(project) for project in projects]
        
        # 并发执行所有任务
        self.results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        processed_results = []
        for i, result in enumerate(self.results):
            if isinstance(result, Exception):
                project = projects[i]
                logger.error(f"❌ 检查项目 {project.get('name', 'Unknown')} 时发生异常: {result}")
                processed_results.append({
                    'project': project.get('name', 'Unknown'),
                    'success': False,
                    'error': str(result),
                    'alarm_sent': False
                })
            else:
                processed_results.append(result)
        
        self.results = processed_results
        
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
        description='异步多项目余额监控工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                          # 异步检查所有启用的项目
  %(prog)s --project "项目A"        # 异步检查指定项目
  %(prog)s --dry-run                # 测试模式，不发送告警
  %(prog)s --config custom.json     # 使用自定义配置文件
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
    
    args = parser.parse_args()
    
    try:
        # 异步运行监控
        monitor = AsyncCreditMonitor(args.config)
        asyncio.run(monitor.run_async(project_name=args.project, dry_run=args.dry_run))
        
    except (FileNotFoundError, json.JSONDecodeError, RuntimeError) as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()