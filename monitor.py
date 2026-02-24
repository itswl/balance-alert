#!/usr/bin/env python3
"""
多项目余额监控主程序
支持配置驱动的多项目余额检查和告警
"""
import json
import sys
import argparse
import hashlib
import threading
import time
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from providers import get_provider
from subscription_checker import SubscriptionChecker
from email_scanner import EmailScanner
from webhook_adapter import WebhookAdapter
from logger import get_logger
from config_loader import load_config_with_env_vars

# 数据持久化（可选）
try:
    from database.repository import BalanceRepository, AlertRepository
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    logger.warning("数据库模块不可用，历史数据不会被保存")

# 创建 logger
logger = get_logger('monitor')

# 并发检查常量
DEFAULT_MAX_CONCURRENT = 20  # 提升默认并发数from 5 to 20
MAX_CONCURRENT_UPPER_BOUND = 50  # 提升上限 from 20 to 50

# Provider 响应缓存（TTL 缓存）
DEFAULT_RESPONSE_CACHE_TTL = 300  # 默认缓存 5 分钟
_response_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_cache_lock = threading.Lock()

# Provider 实例缓存（复用 Session，避免每次创建新实例）
PROVIDER_CACHE_TTL = 600  # 实例缓存 10 分钟
_provider_cache: Dict[str, Tuple[float, Any]] = {}


def _get_or_create_provider(provider_name: str, api_key: str) -> Any:
    """获取或创建 Provider 实例（带 TTL 缓存）"""
    cache_key = f"{provider_name}:{hashlib.md5(api_key.encode()).hexdigest()}"
    now = time.time()

    with _cache_lock:
        if cache_key in _provider_cache:
            cached_time, cached_provider = _provider_cache[cache_key]
            if now - cached_time < PROVIDER_CACHE_TTL:
                return cached_provider
            # TTL 过期，移除旧实例
            del _provider_cache[cache_key]

    # 在锁外创建新实例
    provider_class = get_provider(provider_name)
    provider = provider_class(api_key)

    with _cache_lock:
        _provider_cache[cache_key] = (now, provider)

    return provider


class CreditMonitor:
    """余额监控器"""
    
    def __init__(self, config_path: str = 'config.json') -> None:
        """
        初始化监控器

        Args:
            config_path: 配置文件路径
        """
        self.config_path: Path = Path(config_path)
        self.config: Dict[str, Any] = self._load_config()
        self.results: List[Dict[str, Any]] = []
        self._results_lock = threading.Lock()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件

        Returns:
            Dict[str, Any]: 配置字典
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        try:
            return load_config_with_env_vars(str(self.config_path))
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误: {e}")
    
    def _get_max_concurrent_checks(self) -> int:
        """获取最大并发检查数，默认为5

        Returns:
            int: 最大并发检查数
        """
        try:
            max_concurrent = self.config.get('settings', {}).get('max_concurrent_checks', DEFAULT_MAX_CONCURRENT)
            return max(1, min(max_concurrent, MAX_CONCURRENT_UPPER_BOUND))
        except (TypeError, ValueError):
            return DEFAULT_MAX_CONCURRENT
    
    def check_project(self, project_config: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
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
        
        logger.info(f"检查项目: {project_name} | 服务商: {provider_name} | 告警阈值: {threshold}")
        
        # 获取服务商适配器（复用缓存实例）
        try:
            provider = _get_or_create_provider(provider_name, api_key)
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"❌ {error_msg}")
            return {
                'project': project_name,
                'success': False,
                'error': error_msg,
                'alarm_sent': False
            }
        
        # 检查 TTL 缓存
        cache_ttl = self.config.get('settings', {}).get('response_cache_ttl', DEFAULT_RESPONSE_CACHE_TTL)
        cache_key = f"{provider_name}:{hashlib.md5(api_key.encode()).hexdigest()}"

        if cache_ttl > 0:
            with _cache_lock:
                if cache_key in _response_cache:
                    cached_time, cached_result = _response_cache[cache_key]
                    if time.time() - cached_time < cache_ttl:
                        logger.info(f"[{project_name}] 使用缓存结果 (TTL: {cache_ttl}s)")
                        result = cached_result
                        credits = result['credits']
                        need_alarm = credits < threshold
                        return {
                            'project': project_name,
                            'provider': provider_name,
                            'type': project_config.get('type'),
                            'success': True,
                            'credits': credits,
                            'threshold': threshold,
                            'need_alarm': need_alarm,
                            'alarm_sent': False,
                            'error': None,
                            'cached': True
                        }

        # 获取余额
        result = provider.get_credits()
        
        if not result['success']:
            logger.error(f"❌ 获取余额失败: {result['error']}")
            return {
                'project': project_name,
                'success': False,
                'error': result['error'],
                'alarm_sent': False
            }
        
        credits = result['credits']
        logger.info(f"[{project_name}] 当前余额: {credits}")

        # 缓存成功的结果
        if cache_ttl > 0:
            with _cache_lock:
                _response_cache[cache_key] = (time.time(), result)

        # 检查是否需要告警
        need_alarm = credits < threshold
        alarm_sent = False

        # 保存余额历史到数据库
        if DB_AVAILABLE:
            try:
                project_id = hashlib.md5(f"{provider_name}:{project_name}".encode()).hexdigest()
                BalanceRepository.save_balance_record(
                    project_id=project_id,
                    project_name=project_name,
                    provider=provider_name,
                    balance=credits,
                    threshold=threshold,
                    currency=result.get('currency', 'USD'),
                    balance_type=project_config.get('type', 'credits'),
                    need_alarm=need_alarm
                )
            except Exception as e:
                logger.error(f"保存余额历史失败: {e}")
        
        if need_alarm:
            logger.warning(f"[{project_name}] 余额不足! {credits} < {threshold}")

            if not dry_run:
                alarm_sent = self._send_alarm(project_config, credits)

                # 保存告警历史到数据库
                if DB_AVAILABLE and alarm_sent:
                    try:
                        project_id = hashlib.md5(f"{provider_name}:{project_name}".encode()).hexdigest()
                        balance_type = '余额' if project_config.get('type') == 'balance' else '积分'
                        AlertRepository.save_alert_record(
                            project_id=project_id,
                            project_name=project_name,
                            alert_type='low_balance',
                            message=f"{balance_type}不足: {credits} < {threshold}",
                            balance_value=credits,
                            threshold_value=threshold,
                            status='sent'
                        )
                    except Exception as e:
                        logger.error(f"保存告警历史失败: {e}")
            else:
                logger.info(f"[{project_name}] [测试模式] 跳过发送告警")
        else:
            logger.info(f"[{project_name}] 余额充足: {credits} >= {threshold}")
        
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
    
    def run(self, project_name: Optional[str] = None, dry_run: bool = False) -> None:
        """
        运行监控检查

        Args:
            project_name: 指定项目名称，None 表示检查所有启用的项目
            dry_run: 测试模式，不发送告警
        """
        # 记录开始时间（用于 Prometheus 指标）
        start_time = time.time()

        projects = self.config.get('projects', [])

        if not projects:
            logger.warning("⚠️  配置文件中没有项目")
            return

        # 过滤项目
        if project_name:
            projects = [p for p in projects if p.get('name') == project_name]
            if not projects:
                logger.error(f"未找到项目: {project_name}")
                return
        else:
            projects = [p for p in projects if p.get('enabled', True)]

        logger.info(f"开始监控 {len(projects)} 个项目...")
        if dry_run:
            logger.info("[测试模式] 不会发送实际告警")

        # 记录活跃项目数（Prometheus 指标）
        try:
            from prometheus_exporter import set_active_projects_count
            set_active_projects_count(len(projects))
        except Exception:
            pass  # 容错，不影响主流程

        # 获取配置的并发数
        max_workers = self._get_max_concurrent_checks()
        actual_workers = min(max_workers, len(projects))
        logger.info(f"并发检查数: {actual_workers} (配置: {max_workers}, 项目数: {len(projects)})")
        
        # 使用线程池并发检查项目
        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
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
                    with self._results_lock:
                        self.results.append(result)
                except Exception as e:
                    logger.error(f"❌ 检查项目 {project.get('name', 'Unknown')} 时发生错误: {e}", exc_info=True)
                    with self._results_lock:
                        self.results.append({
                            'project': project.get('name', 'Unknown'),
                            'success': False,
                            'error': str(e),
                            'alarm_sent': False
                        })
        
        # 输出汇总
        self._print_summary()

        # 记录执行时间（Prometheus 指标）
        execution_time = time.time() - start_time
        try:
            from prometheus_exporter import record_monitor_execution
            record_monitor_execution(execution_time)
            logger.info(f"✅ 监控完成，耗时 {execution_time:.2f} 秒")
        except Exception:
            pass  # 容错
    
    def _print_summary(self) -> None:
        """打印检查汇总"""
        total = len(self.results)
        success = sum(1 for r in self.results if r['success'])
        failed = total - success
        need_alarm = sum(1 for r in self.results if r.get('need_alarm', False))
        alarm_sent = sum(1 for r in self.results if r.get('alarm_sent', False))

        logger.info(f"检查汇总: 总项目={total}, 成功={success}, 失败={failed}, 需告警={need_alarm}, 已告警={alarm_sent}")

        # 详细列表
        for r in self.results:
            project = r['project']
            if r['success']:
                credits = r['credits']
                threshold = r['threshold']
                if r.get('alarm_sent'):
                    logger.warning(f"  {project}: {credits} / {threshold} - 已告警")
                elif r.get('need_alarm'):
                    logger.warning(f"  {project}: {credits} / {threshold} - 需告警")
                else:
                    logger.info(f"  {project}: {credits} / {threshold} - 正常")
            else:
                error = r.get('error', 'Unknown error')
                logger.error(f"  {project}: {error}")


def main() -> None:
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
            subscription_checker = SubscriptionChecker(args.config)
            subscription_checker.check_subscriptions(dry_run=args.dry_run)
        
        # 扫描邮箱（如果指定）
        if args.check_email:
            email_scanner = EmailScanner(args.config)
            email_scanner.scan_emails(days=args.email_days, dry_run=args.dry_run)
            
    except Exception as e:
        logger.error(f"错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
