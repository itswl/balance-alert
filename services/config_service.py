#!/usr/bin/env python3
import copy
import os
from typing import Any, Dict, List, Optional

from core.config_loader import load_config_with_env_vars as _load_file_config
from core.config_loader import get_default_config_path


def load_config(config_file: str = 'config.json', validate: bool = True, use_cache: bool = True) -> Dict[str, Any]:
    base = _load_file_config(config_file, validate=validate)
    config = copy.deepcopy(base)

    if os.environ.get('ENABLE_DYNAMIC_CONFIG', 'false').lower() != 'true':
        return config

    try:
        from database.repository import ConfigRepository
    except Exception:
        return config

    try:
        db_projects = ConfigRepository.get_all_projects()
        db_subscriptions = ConfigRepository.get_all_subscriptions()
        db_emails = ConfigRepository.get_all_emails()
    except Exception:
        return config

    if db_projects:
        config['projects'] = [
            {k: v for k, v in p.items() if k not in ['id', 'created_at', 'updated_at']}
            for p in db_projects
        ]
    if db_subscriptions:
        config['subscriptions'] = [
            {k: v for k, v in s.items() if k not in ['id', 'created_at', 'updated_at']}
            for s in db_subscriptions
        ]
    if db_emails:
        config['email'] = [
            {k: v for k, v in e.items() if k not in ['id', 'created_at', 'updated_at']}
            for e in db_emails
        ]

    return config


def get_all_projects() -> List[Dict[str, Any]]:
    config = load_config(get_default_config_path(), validate=False)
    return list(config.get('projects', []) or [])


def get_all_subscriptions() -> List[Dict[str, Any]]:
    config = load_config(get_default_config_path(), validate=False)
    return list(config.get('subscriptions', []) or [])


def get_all_emails() -> List[Dict[str, Any]]:
    config = load_config(get_default_config_path(), validate=False)
    return list(config.get('email', []) or [])


def upsert_project(project: Dict[str, Any]) -> bool:
    try:
        from database.repository import ConfigRepository
        return bool(ConfigRepository.upsert_project(project))
    except Exception:
        return False


def upsert_subscription(subscription: Dict[str, Any]) -> bool:
    try:
        from database.repository import ConfigRepository
        return bool(ConfigRepository.upsert_subscription(subscription))
    except Exception:
        return False


def delete_subscription(name: str) -> bool:
    try:
        from database.repository import ConfigRepository
        return bool(ConfigRepository.delete_subscription(name))
    except Exception:
        return False


def upsert_email(email_config: Dict[str, Any]) -> bool:
    try:
        from database.repository import ConfigRepository
        return bool(ConfigRepository.upsert_email(email_config))
    except Exception:
        return False


def delete_email(name: str) -> bool:
    try:
        from database.repository import ConfigRepository
        return bool(ConfigRepository.delete_email(name))
    except Exception:
        return False
