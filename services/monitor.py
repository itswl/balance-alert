#!/usr/bin/env python3
"""
多项目余额监控主程序
支持配置驱动的多项目余额检查和告警
"""
import sys
import argparse
import hashlib
import threading
import time
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from providers import get_provider
from services.subscription_checker import SubscriptionChecker
from services.email_scanner import EmailScanner
from services.webhook_adapter import WebhookAdapter
from core.logger import get_logger
from core.config_loader import filter_enabled, load_config, make_project_id, owner_project_of
from core.settings import get_settings
from services import alert_store

logger = get_logger('monitor')

# 并发检查常量
DEFAULT_MAX_CONCURRENT = 20
MAX_CONCURRENT_UPPER_BOUND = 50

PROVIDER_CACHE_TTL = 600  # Provider 实例（含 HTTP Session）缓存 10 分钟


class _TTLCache:
    """线程安全的 {key: (写入时间, 值)} 缓存，读取时按 TTL 判断过期"""

    def __init__(self) -> None:
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl_seconds: int) -> Optional[Any]:
        if ttl_seconds <= 0:
            return None
        with self._lock:
            hit = self._data.get(key)
            if hit is None:
                return None
            cached_at, value = hit
            if time.time() - cached_at >= ttl_seconds:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_provider_cache = _TTLCache()
_response_cache = _TTLCache()


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
    
    def __init__(self) -> None:
        self.config: Dict[str, Any] = load_config()
        self.results: List[Dict[str, Any]] = []

    def _get_max_concurrent_checks(self) -> int:
        """最大并发检查数：环境变量 MAX_CONCURRENT_CHECKS，钳制在 [1, 50]。"""
        max_concurrent = get_settings().max_concurrent_checks
        if max_concurrent is None:
            max_concurrent = DEFAULT_MAX_CONCURRENT
        return max(1, min(max_concurrent, MAX_CONCURRENT_UPPER_BOUND))

    def _failure_result(self, project_name: str, owner_project: Optional[str], provider_name: Optional[str],
                        error_msg: str, balance_type: Optional[str] = None) -> Dict[str, Any]:
        return {
            'project': project_name,
            'owner_project': owner_project,
            'provider': provider_name,
            'type': balance_type,
            'success': False,
            'error': error_msg,
            'alarm_sent': False
        }

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
        owner_project = owner_project_of(project_config)
        provider_name = project_config.get('provider')
        api_key = project_config.get('api_key')
        threshold = project_config.get('threshold', 0)
        
        logger.info(f"检查项目: {project_name} | 服务商: {provider_name} | 告警阈值: {threshold}")
        
        try:
            provider = _get_or_create_provider(provider_name, api_key)
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"{error_msg}")
            return self._failure_result(project_name, owner_project, provider_name, error_msg, project_config.get('type'))
        
        cache_ttl = get_settings().response_cache_ttl
        cache_key = _provider_cache_key(provider_name, api_key)
        result = _response_cache.get(cache_key, cache_ttl)
        cached = result is not None
        if cached:
            logger.info(f"[{project_name}] 使用缓存结果 (TTL: {cache_ttl}s)")
        else:
            result = provider.get_credits()
        
        if not result['success']:
            logger.error(f"获取余额失败: {result['error']}")
            return self._failure_result(project_name, owner_project, provider_name, result['error'], project_config.get('type'))
        
        credits = result['credits']
        logger.info(f"[{project_name}] 当前余额: {credits}")

        # 缓存成功的结果
        if cache_ttl > 0 and not cached:
            _response_cache.set(cache_key, result)

        # 检查是否需要告警
        need_alarm = credits < threshold
        alarm_sent = False

        project_id = make_project_id(provider_name, project_name)
        alert_store.record_balance(
            project_id, project_name, provider_name, credits, threshold,
            project_config.get('type', 'credits'), need_alarm,
        )

        if need_alarm:
            logger.warning(f"[{project_name}] 余额不足! {credits} < {threshold}")

            if not dry_run:
                alert_cooldown = alert_store.cooldown_seconds('balance')
                if alert_store.in_cooldown(project_id, 'low_balance', alert_cooldown):
                    logger.info(f"[{project_name}] 告警仍在冷却窗口内 ({alert_cooldown}s)，跳过重复通知")
                else:
                    alarm_sent = self._send_alarm(project_config, credits)

                    if alarm_sent:
                        alert_store.record_alert(
                            project_id, project_name, 'low_balance',
                            f"余额不足: {credits} < {threshold}", credits, threshold,
                        )
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
        """发送告警到 webhook"""
        adapter = WebhookAdapter.from_settings('credit-monitor')
        if adapter is None:
            logger.error("未配置 webhook 地址")
            return False

        return adapter.send_balance_alert(
            project_name=project_config.get('name'),
            owner_project=owner_project_of(project_config),
            provider=project_config.get('provider'),
            balance_type='余额',
            current_value=credits,
            threshold=project_config.get('threshold'),
            unit=''
        )
    
    def run(self, project_name: Optional[str] = None, dry_run: bool = False) -> None:
        """
        运行监控检查

        Args:
            project_name: 指定项目名称，None 表示检查所有启用的项目
            dry_run: 测试模式，不发送告警
        """
        start_time = time.time()

        projects = self.config.get('projects', [])

        if not projects:
            logger.warning("没有可监控的项目，检查 {PROVIDER}_API_KEY 或数据库动态配置")
            return

        # 过滤项目
        if project_name:
            projects = [p for p in projects if p.get('name') == project_name]
            if not projects:
                logger.error(f"未找到项目: {project_name}")
                return
        else:
            projects = filter_enabled(projects)

        logger.info(f"开始监控 {len(projects)} 个项目...")
        if dry_run:
            logger.info("[测试模式] 不会发送实际告警")

        # 获取配置的并发数
        max_workers = self._get_max_concurrent_checks()
        actual_workers = min(max_workers, len(projects))
        logger.info(f"并发检查数: {actual_workers} (配置: {max_workers}, 项目数: {len(projects)})")
        
        # 并发检查，结果在本线程按完成顺序收集
        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            futures = {executor.submit(self.check_project, project, dry_run): project for project in projects}
            for future in as_completed(futures):
                project = futures[future]
                try:
                    self.results.append(future.result())
                except Exception as e:
                    logger.error(f"检查项目 {project.get('name', 'Unknown')} 时发生错误: {e}", exc_info=True)
                    self.results.append(self._failure_result(
                        project.get('name', 'Unknown'), owner_project_of(project), project.get('provider'), str(e), project.get('type')))

        self._print_summary()
        logger.info(f"监控完成，耗时 {time.time() - start_time:.2f} 秒")
    
    def _print_summary(self) -> None:
        """打印检查汇总"""
        success = sum(1 for r in self.results if r['success'])
        need_alarm = sum(1 for r in self.results if r.get('need_alarm'))
        alarm_sent = sum(1 for r in self.results if r.get('alarm_sent'))
        logger.info(f"检查汇总: 总项目={len(self.results)}, 成功={success}, 失败={len(self.results) - success}, "
                    f"需告警={need_alarm}, 已告警={alarm_sent}")

        for r in self.results:
            if not r['success']:
                logger.error(f"  {r['project']}: {r.get('error', 'Unknown error')}")
                continue
            state = '已告警' if r.get('alarm_sent') else ('需告警' if r.get('need_alarm') else '正常')
            log = logger.warning if r.get('need_alarm') else logger.info
            log(f"  {r['project']}: {r['credits']} / {r['threshold']} - {state}")


def run_credit_monitor(project_name: Optional[str] = None, dry_run: bool = True) -> Dict[str, Any]:
    try:
        monitor = CreditMonitor()
        monitor.run(project_name=project_name, dry_run=dry_run)
        # 阈值告警看的是当下，跑道与突增看的是趋势，后者依赖历史，放在整轮检查之后
        from services import runway
        runway.analyze(monitor.results, dry_run=dry_run)
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
  %(prog)s --check-subscriptions    # 检查订阅续费提醒
  %(prog)s --check-email            # 扫描邮箱告警邮件
  %(prog)s --check-email --email-days 3  # 扫描最近3天的邮件
        """
    )

    parser.add_argument('--project', help='指定要检查的项目名称')
    parser.add_argument('--dry-run', action='store_true', help='测试模式，只显示余额不发送告警')
    parser.add_argument('--check-subscriptions', action='store_true', help='检查订阅续费提醒')
    parser.add_argument('--check-email', action='store_true', help='扫描邮箱告警邮件')
    parser.add_argument('--email-days', type=int, default=1, help='扫描最近几天的邮件 (默认: 1天)')
    parser.add_argument('--show-config', action='store_true',
                        help='自检配置：显示每项配置来自哪里、缺什么，有问题时退出码非零')
    return parser


def _run_from_args(args) -> None:
    if args.show_config:
        from core.config_check import check_config
        sys.exit(1 if check_config() else 0)

    monitor = CreditMonitor()
    monitor.run(project_name=args.project, dry_run=args.dry_run)

    # 与 Web 主流程同一开关语义：--check-subscriptions 可强制执行
    if args.check_subscriptions or (args.project is None and get_settings().enable_subscriptions):
        subscription_checker = SubscriptionChecker()
        subscription_checker.check_subscriptions(dry_run=args.dry_run)

    if args.check_email:
        email_scanner = EmailScanner()
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
