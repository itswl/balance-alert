#!/usr/bin/env python3
"""
日志配置模块
统一日志格式和输出
支持结构化日志（JSON 格式）
"""
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

from pythonjsonlogger import jsonlogger

from core.settings import get_settings


def setup_logging() -> logging.Logger:
    """按 LOG_LEVEL / LOG_FORMAT / LOG_FILE（经 core.settings）配置日志"""
    settings = get_settings()

    logger = logging.getLogger('balance_alert')
    numeric_level = getattr(logging, settings.log_level.upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    logger.setLevel(numeric_level)
    # 不向 root 传播：waitress.serve() 会调用 logging.basicConfig()，否则每条日志打两遍
    logger.propagate = False

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    if settings.log_format.lower() == 'json':
        formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s',
            timestamp=True
        )
    else:
        formatter = logging.Formatter(
            fmt='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件 handler（可选）
    if settings.log_file:
        file_handler = RotatingFileHandler(settings.log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# 全局 logger 实例
logger = setup_logging()


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取 logger 实例

    Args:
        name: logger 名称，None 表示使用根 logger

    Returns:
        logging.Logger: logger 实例
    """
    if name:
        return logging.getLogger(f'balance_alert.{name}')
    return logger
