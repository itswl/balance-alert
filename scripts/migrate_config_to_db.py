#!/usr/bin/env python3
"""把旧的 config.json 一次性导入数据库动态配置。

项目本身已经不再读配置文件，这个脚本只为从旧版本升级的人保留：

    ENABLE_DATABASE=true ENABLE_DYNAMIC_CONFIG=true \
        python scripts/migrate_config_to_db.py [config.json]

导入后即可删掉该文件。项目也可以改用 {PROVIDER}_API_KEY 环境变量，不必入库。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.config_loader import normalize_config  # noqa: E402
from database.repository import ConfigRepository  # noqa: E402

SECTION_LABELS = {'projects': '项目', 'subscriptions': '订阅', 'email': '邮箱'}


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else 'config.json'
    if not os.path.isfile(path):
        sys.exit(f"找不到配置文件: {path}")

    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    # 旧文件里的 ${VAR} 占位符按当前环境变量展开
    def expand(value):
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        if isinstance(value, list):
            return [expand(v) for v in value]
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            return os.environ.get(value[2:-1], '')
        return value

    config = normalize_config({section: expand(raw.get(section) or []) for section in SECTION_LABELS})

    total = 0
    for section, label in SECTION_LABELS.items():
        for item in config[section]:
            item.pop('from_env', None)
            if ConfigRepository.upsert(section, item):
                total += 1
                print(f"已导入{label}: {item.get('name')}")
    print(f"迁移完成，共 {total} 条。确认页面上能看到之后即可删除 {path}")


if __name__ == '__main__':
    main()
