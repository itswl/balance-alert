#!/usr/bin/env python3
import copy
import os
from typing import Any, Dict, List, Optional

from core.config_loader import get_config as _get_file_config
from core.config_loader import get_default_config_path, load_config_with_env_vars as _load_file_config


_DB_META_FIELDS = {'id', 'created_at', 'updated_at'}


def _dynamic_config_enabled() -> bool:
    return os.environ.get('ENABLE_DYNAMIC_CONFIG', 'false').lower() == 'true'


def _load_base_config(config_file: str, validate: bool, use_cache: bool) -> Dict[str, Any]:
    if use_cache:
        return _get_file_config(config_file, use_cache=True, validate=validate)
    return _load_file_config(config_file, validate=validate)


def _get_config_repository():
    try:
        from database.repository import ConfigRepository
        return ConfigRepository
    except Exception:
        return None


def _strip_meta_fields(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: v for k, v in item.items() if k not in _DB_META_FIELDS} for item in items]


def _load_default_config() -> Dict[str, Any]:
    return load_config(get_default_config_path(), validate=False)


def _call_repo_bool(method_name: str, *args) -> bool:
    repo = _get_config_repository()
    if repo is None:
        return False
    try:
        return bool(getattr(repo, method_name)(*args))
    except Exception:
        return False


def load_config(config_file: str = 'config.json', validate: bool = True, use_cache: bool = True) -> Dict[str, Any]:
    base = _load_base_config(config_file, validate=validate, use_cache=use_cache)
    config = copy.deepcopy(base)

    if not _dynamic_config_enabled():
        return config

    repo = _get_config_repository()
    if repo is None:
        return config

    try:
        db_projects = repo.get_all_projects()
        db_subscriptions = repo.get_all_subscriptions()
        db_emails = repo.get_all_emails()
    except Exception:
        return config

    if db_projects:
        config['projects'] = _strip_meta_fields(db_projects)
    if db_subscriptions:
        config['subscriptions'] = _strip_meta_fields(db_subscriptions)
    if db_emails:
        config['email'] = _strip_meta_fields(db_emails)

    return config


def get_all_projects() -> List[Dict[str, Any]]:
    config = _load_default_config()
    return list(config.get('projects', []) or [])


def get_all_subscriptions() -> List[Dict[str, Any]]:
    config = _load_default_config()
    return list(config.get('subscriptions', []) or [])


def get_all_emails() -> List[Dict[str, Any]]:
    config = _load_default_config()
    return list(config.get('email', []) or [])


def upsert_project(project: Dict[str, Any]) -> bool:
    return _call_repo_bool('upsert_project', project)


def upsert_subscription(subscription: Dict[str, Any]) -> bool:
    return _call_repo_bool('upsert_subscription', subscription)


def delete_subscription(name: str) -> bool:
    return _call_repo_bool('delete_subscription', name)


def upsert_email(email_config: Dict[str, Any]) -> bool:
    return _call_repo_bool('upsert_email', email_config)


def delete_email(name: str) -> bool:
    return _call_repo_bool('delete_email', name)
