#!/usr/bin/env python3
"""
监控业务逻辑处理器

处理余额监控相关的业务逻辑
"""
from typing import Dict, Any, List
from monitor import CreditMonitor
from state_manager import StateManager
from logger import get_logger

logger = get_logger('web.handlers.monitor')


def update_balance_cache(results: List[Dict[str, Any]], state_mgr: StateManager) -> None:
    """
    更新余额状态缓存

    Args:
        results: 监控结果列表
        state_mgr: 状态管理器实例
    """
    state_mgr.update_balance(results)


def refresh_credits(config_path: str, project_name: str = None, dry_run: bool = True) -> Dict[str, Any]:
    """
    执行余额刷新

    Args:
        config_path: 配置文件路径
        project_name: 项目名称（可选，指定则只刷新该项目）
        dry_run: 是否为测试模式（不发送告警）

    Returns:
        刷新结果字典
    """
    try:
        monitor = CreditMonitor(config_path)
        monitor.run(project_name=project_name, dry_run=dry_run)

        return {
            'success': True,
            'results': monitor.results,
            'count': len(monitor.results)
        }
    except Exception as e:
        logger.error(f"刷新失败: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'count': 0
        }
