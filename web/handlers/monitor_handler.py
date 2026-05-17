#!/usr/bin/env python3
"""
监控业务逻辑处理器

处理余额监控相关的业务逻辑
"""
from typing import Dict, Any, List
from services.monitor import run_credit_monitor
from core.state_manager import StateManager
from core.logger import get_logger

logger = get_logger('web.handlers.monitor')


def update_balance_cache(results: List[Dict[str, Any]], state_mgr: StateManager, is_partial: bool = False) -> None:
    """
    更新余额状态缓存

    Args:
        results: 监控结果列表
        state_mgr: 状态管理器实例
        is_partial: 是否为增量/局部更新
    """
    if is_partial:
        state_mgr.merge_balance_state(results)
    else:
        state_mgr.update_balance_state(results)


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
    return run_credit_monitor(config_path, project_name=project_name, dry_run=dry_run)
