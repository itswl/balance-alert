#!/usr/bin/env python3
"""
多项目余额监控主程序
支持配置驱动的多项目余额检查和告警
"""
import json
import os
import sys
import argparse
import hashlib
import threading
import time
from typing import Dict, Any, List, Optional, Tuple, Callable, TypeVar, Generic
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from providers import get_provider
from services.subscription_checker import SubscriptionChecker
from services.email_scanner import EmailScanner
from services.webhook_adapter import WebhookAdapter
from core.logger import get_logger
from core.config_loader import make_project_id
from services.config_service import load_config

# 创建 logger（必须在使用前定义）
logger = get_logger('monitor')

# 数据持久化（可选）
try:
    from database.repository import BalanceRepository, AlertRepository
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    logger.warning("数据库模块不可用，历史数据不会被保存")

# 并发检查常量
DEFAULT_MAX_CONCURRENT = 20  # 提升默认并发数from 5 to 20
MAX_CONCURRENT_UPPER_BOUND = 50  # 提升上限 from 20 to 50

DEFAULT_RESPONSE_CACHE_TTL = 300  # 默认缓存 5 分钟
PROVIDER_CACHE_TTL = 600  # 实例缓存 10 分钟

T = TypeVar('T')


class _TTLCache(Generic[T]):
    def __init__(self) -> None:
        self._data: Dict[str, Tuple[float, T]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl_seconds: int) -> Optional[T]:
        if ttl_seconds <= 0:
            return None

        now = time.time()
        with self._lock:
            hit = self._data.get(key)
            if not hit:
                return None
            cached_at, value = hit
            if now - cached_at >= ttl_seconds:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: T) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def keys(self):
        with self._lock:
            return list(self._data.keys())

    def __getitem__(self, key: str):
        with self._lock:
            return self._data[key]

    def __setitem__(self, key: str, value):
        with self._lock:
            self._data[key] = value


_provider_cache: _TTLCache[Any] = _TTLCache()
_response_cache: _TTLCache[Dict[str, Any]] = _TTLCache()


def _get_alert_cooldown_seconds(config: Dict[str, Any]) -> int:
    """获取告警冷却时间，默认 24 小时。"""
    env_value = os.environ.get('ALERT_COOLDOWN_SECONDS')
    raw_value = env_value if env_value is not None else config.get('settings', {}).get('alert_cooldown_seconds', 86400)
    try:
        return max(0, int(raw_value))
    except (TypeError, ValueError):
        return 86400


def _safe_metrics_call(action: Callable[[], None]) -> None:
    try:
        action()
    except Exception:
        return None


def _get_metrics_collector():
    try:
        from services.prometheus_exporter import metrics_collector
        return metrics_collector
    except Exception:
        return None


def _set_active_projects_count(count: int) -> None:
    collector = _get_metrics_collector()
    if collector is None:
        return None
    _safe_metrics_call(lambda: collector.active_projects_count.set(count))


def _observe_monitor_execution_time(seconds: float) -> None:
    collector = _get_metrics_collector()
    if collector is None:
        return None
    _safe_metrics_call(lambda: collector.monitor_execution_time.observe(seconds))


def _project_id(provider_name: str, project_name: str) -> str:
    return make_project_id(provider_name, project_name)


def _provider_cache_key(provider_name: str, api_key: str) -> str:
    return f"{provider_name}:{hashlib.md5(api_key.encode()).hexdigest()}"


def _get_or_create_provider(provider_name: str, api_key: str) -> Any:
    """获取或创建 Provider 实例（带 TTL 缓存）"""
    if not api_key:
        raise ValueError(f"项目缺少 API Key，无法创建服务商适配器: {provider_name}")

    cache_key = _provider_cache_key(provider_name, api_key)
    cached = _provider_cache.get(cache_key, PROVIDER_CACHE_TTL)
    if cached is not None:
        return cached

    provider_class = get_provider(provider_name)
    provider = provider_class(api_key)
    _provider_cache.set(cache_key, provider)
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
        if not self.config_path.exists() and os.environ.get('ENABLE_DYNAMIC_CONFIG', 'false').lower() != 'true':
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        return load_config(str(self.config_path))
    
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

    def _failure_result(self, project_name: str, owner_project: Optional[str], provider_name: Optional[str], error_msg: str) -> Dict[str, Any]:
        return {
            'project': project_name,
            'owner_project': owner_project,
            'provider': provider_name,
            'success': False,
            'error': error_msg,
            'alarm_sent': False
        }

    def _save_balance_history(self, provider_name: str, project_name: str, credits: float, threshold: float, project_config: Dict[str, Any], need_alarm: bool) -> None:
        if not DB_AVAILABLE:
            return None
        try:
            project_id = _project_id(provider_name, project_name)
            BalanceRepository.save_balance_record(
                project_id=project_id,
                project_name=project_name,
                provider=provider_name,
                balance=credits,
                threshold=threshold,
                balance_type=project_config.get('type', 'credits'),
                need_alarm=need_alarm
            )
        except Exception as e:
            logger.error(f"保存余额历史失败: {e}", exc_info=True)

    def _should_skip_alarm(self, project_id: str, alert_type: str, cooldown_seconds: int) -> bool:
        if not DB_AVAILABLE:
            return False
        try:
            return AlertRepository.has_recent_alert(project_id, alert_type, cooldown_seconds)
        except Exception:
            return False

    def _save_alert_history(self, project_id: str, project_name: str, alert_type: str, message: str, credits: float, threshold: float) -> None:
        if not DB_AVAILABLE:
            return None
        try:
            AlertRepository.save_alert_record(
                project_id=project_id,
                project_name=project_name,
                alert_type=alert_type,
                message=message,
                balance_value=credits,
                threshold_value=threshold,
                status='sent'
            )
        except Exception as e:
            logger.error(f"保存告警历史失败: {e}", exc_info=True)
    
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
        owner_project = project_config.get('owner_project') or project_config.get('project')
        provider_name = project_config.get('provider')
        api_key = project_config.get('api_key')
        threshold = project_config.get('threshold', 0)
        
        logger.info(f"检查项目: {project_name} | 服务商: {provider_name} | 告警阈值: {threshold}")
        
        try:
            provider = _get_or_create_provider(provider_name, api_key)
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"❌ {error_msg}")
            return self._failure_result(project_name, owner_project, provider_name, error_msg)
        
        cache_ttl = int(self.config.get('settings', {}).get('response_cache_ttl', DEFAULT_RESPONSE_CACHE_TTL) or 0)
        cache_key = _provider_cache_key(provider_name, api_key)
        result = _response_cache.get(cache_key, cache_ttl)
        cached = result is not None
        if cached:
            logger.info(f"[{project_name}] 使用缓存结果 (TTL: {cache_ttl}s)")
        else:
            result = provider.get_credits()
        
        if not result['success']:
            logger.error(f"❌ 获取余额失败: {result['error']}")
            return self._failure_result(project_name, owner_project, provider_name, result['error'])
        
        credits = result['credits']
        logger.info(f"[{project_name}] 当前余额: {credits}")

        # 缓存成功的结果
        if cache_ttl > 0 and not cached:
            _response_cache.set(cache_key, result)

        # 检查是否需要告警
        need_alarm = credits < threshold
        alarm_sent = False

        self._save_balance_history(provider_name, project_name, credits, threshold, project_config, need_alarm)
        
        if need_alarm:
            logger.warning(f"[{project_name}] 余额不足! {credits} < {threshold}")

            if not dry_run:
                project_id = _project_id(provider_name, project_name)
                alert_cooldown = _get_alert_cooldown_seconds(self.config)
                if self._should_skip_alarm(project_id, 'low_balance', alert_cooldown):
                    logger.info(f"[{project_name}] 告警仍在冷却窗口内 ({alert_cooldown}s)，跳过重复通知")
                else:
                    alarm_sent = self._send_alarm(project_config, credits)

                    if alarm_sent:
                        self._save_alert_history(project_id, project_name, 'low_balance', f"余额不足: {credits} < {threshold}", credits, threshold)
            else:
                logger.info(f"[{project_name}] [测试模式] 跳过发送告警")
        else:
            logger.info(f"[{project_name}] 余额充足: {credits} >= {threshold}")
        
        return {
            'project': project_name,
            'owner_project': owner_project,
            'provider': provider_name,
            'type': project_config.get('type'),  # 传递类型字段到前端
            'success': True,
            'credits': credits,
            'threshold': threshold,
            'need_alarm': need_alarm,
            'alarm_sent': alarm_sent,
            'error': None,
            'cached': cached
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
        balance_type = '余额'
        unit = ''
        
        # 发送告警
        return adapter.send_balance_alert(
            project_name=project_name,
            owner_project=project_config.get('owner_project') or project_config.get('project'),
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

        _set_active_projects_count(len(projects))

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
                        self.results.append(self._failure_result(project.get('name', 'Unknown'), project.get('owner_project') or project.get('project'), project.get('provider'), str(e)))
        
        # 输出汇总
        self._print_summary()

        # 记录执行时间（Prometheus 指标）
        execution_time = time.time() - start_time
        _observe_monitor_execution_time(execution_time)
        logger.info(f"✅ 监控完成，耗时 {execution_time:.2f} 秒")
    
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


def run_credit_monitor(config_path: str, project_name: Optional[str] = None, dry_run: bool = True) -> Dict[str, Any]:
    try:
        monitor = CreditMonitor(config_path)
        monitor.run(project_name=project_name, dry_run=dry_run)
        return {
            'success': True,
            'results': monitor.results,
            'count': len(monitor.results),
        }
    except Exception as e:
        logger.error(f"刷新失败: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'count': 0,
            'results': [],
        }


def _build_arg_parser() -> argparse.ArgumentParser:
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

    from core.config_loader import get_default_config_path
    default_config = get_default_config_path()

    parser.add_argument('--config', default=default_config, help=f'配置文件路径 (默认: {default_config})')
    parser.add_argument('--project', help='指定要检查的项目名称')
    parser.add_argument('--dry-run', action='store_true', help='测试模式，只显示余额不发送告警')
    parser.add_argument('--check-subscriptions', action='store_true', help='检查订阅续费提醒')
    parser.add_argument('--check-email', action='store_true', help='扫描邮箱告警邮件')
    parser.add_argument('--email-days', type=int, default=1, help='扫描最近几天的邮件 (默认: 1天)')
    return parser


def _run_from_args(args) -> None:
    monitor = CreditMonitor(args.config)
    monitor.run(project_name=args.project, dry_run=args.dry_run)

    if args.check_subscriptions or args.project is None:
        subscription_checker = SubscriptionChecker(args.config)
        subscription_checker.check_subscriptions(dry_run=args.dry_run)

    if args.check_email:
        email_scanner = EmailScanner(args.config)
        email_scanner.scan_emails(days=args.email_days, dry_run=args.dry_run)


def main() -> None:
    """主函数"""
    parser = _build_arg_parser()
    args = parser.parse_args()
    try:
        _run_from_args(args)
    except Exception as e:
        logger.error(f"错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
