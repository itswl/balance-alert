#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.config_loader import load_config_with_env_vars
from database.repository import ConfigRepository

def main():
    print("开始迁移...")
    config = load_config_with_env_vars()
    
    for p in config.get('projects', []):
        ConfigRepository.upsert_project({
            'name': p['name'],
            'owner_project': p.get('owner_project') or p.get('project'),
            'provider': p.get('provider', ''),
            'api_key': p.get('api_key', ''),
            'threshold': p.get('threshold', 0),
            'type': p.get('type', 'credits'),
            'enabled': p.get('enabled', True)
        })
        print(f"Migrated project: {p['name']}")
        
    for s in config.get('subscriptions', []):
        ConfigRepository.upsert_subscription({
            'name': s['name'],
            'owner_project': s.get('owner_project') or s.get('project'),
            'cycle_type': s.get('cycle_type', 'monthly'),
            'renewal_day': s.get('renewal_day', 1),
            'alert_days_before': s.get('alert_days_before', 3),
            'amount': s.get('amount', 0),
            'enabled': s.get('enabled', True),
            'last_renewed_date': s.get('last_renewed_date')
        })
        print(f"Migrated subscription: {s['name']}")
        
    for e in config.get('email', []):
        ConfigRepository.upsert_email({
            'name': e.get('name', e.get('username', 'email')),
            'host': e.get('host', ''),
            'port': e.get('port', 993),
            'username': e.get('username', ''),
            'password': e.get('password', ''),
            'use_ssl': e.get('use_ssl', True),
            'enabled': e.get('enabled', True)
        })
        print(f"Migrated email: {e.get('name', e.get('username'))}")
    
    print("迁移完成！")

if __name__ == '__main__':
    main()
