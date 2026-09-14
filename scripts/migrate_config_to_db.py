#!/usr/bin/env python3
"""把 config.json 里的 projects / subscriptions / email 一次性导入数据库动态配置。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.config_loader import load_config_with_env_vars, normalize_config  # noqa: E402
from database.repository import ConfigRepository  # noqa: E402


def main():
    config = normalize_config(load_config_with_env_vars())
    for section in ConfigRepository.SECTIONS:
        for item in config.get(section, []):
            ConfigRepository.upsert(section, item)
            print(f"已导入 {section}: {item.get('name')}")
    print("迁移完成")


if __name__ == '__main__':
    main()
