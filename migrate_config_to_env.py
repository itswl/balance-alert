#!/usr/bin/env python3
"""
配置迁移脚本：从 config.json 提取敏感信息到 .env 文件

功能：
1. 读取 config.json 中的敏感信息
2. 生成 .env 文件（保留原有配置格式）
3. 将 config.json 中的敏感字段替换为环境变量引用
4. 备份原始 config.json

使用方法：
    python migrate_config_to_env.py
"""

import json
import os
import shutil
from datetime import datetime
from typing import Dict, Any


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """加载配置文件"""
    if not os.path.exists(config_path):
        print(f"❌ 配置文件不存在: {config_path}")
        return {}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def backup_config(config_path: str = "config.json") -> str:
    """备份原始配置文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{config_path}.backup_{timestamp}"
    shutil.copy2(config_path, backup_path)
    print(f"✅ 已备份原配置到: {backup_path}")
    return backup_path


def generate_env_file(config: Dict[str, Any], env_path: str = ".env") -> None:
    """生成 .env 文件"""
    lines = []
    
    # 顶部注释
    lines.append("# ========================================")
    lines.append("# 余额告警系统 - 环境变量配置")
    lines.append("# ========================================")
    lines.append(f"# 自动生成于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("# ⚠️ 警告：此文件包含敏感信息，请勿提交到 Git！")
    lines.append("")
    
    # 系统设置
    lines.append("# ========================================")
    lines.append("# 系统设置")
    lines.append("# ========================================")
    settings = config.get('settings', {})
    lines.append(f"BALANCE_REFRESH_INTERVAL_SECONDS={settings.get('balance_refresh_interval_seconds', 3600)}")
    lines.append(f"MAX_CONCURRENT_CHECKS={settings.get('max_concurrent_checks', 5)}")
    lines.append(f"MIN_REFRESH_INTERVAL_SECONDS={settings.get('min_refresh_interval_seconds', 60)}")
    lines.append(f"ENABLE_SMART_REFRESH={str(settings.get('enable_smart_refresh', False)).lower()}")
    lines.append(f"SMART_REFRESH_THRESHOLD_PERCENT={settings.get('smart_refresh_threshold_percent', 5)}")
    lines.append("")
    
    # Webhook 配置
    lines.append("# ========================================")
    lines.append("# Webhook 告警配置")
    lines.append("# ========================================")
    webhook = config.get('webhook', {})
    lines.append(f"WEBHOOK_URL={webhook.get('url', '')}")
    lines.append(f"WEBHOOK_SOURCE={webhook.get('source', 'credit-monitor')}")
    lines.append(f"WEBHOOK_TYPE={webhook.get('type', 'feishu')}")
    lines.append("")
    
    # 邮箱配置
    lines.append("# ========================================")
    lines.append("# 邮箱配置")
    lines.append("# ========================================")
    emails = config.get('email', [])
    for idx, email in enumerate(emails, 1):
        lines.append(f"# 邮箱{idx} - {email.get('name', '')}")
        lines.append(f"EMAIL_{idx}_NAME={email.get('name', '')}")
        lines.append(f"EMAIL_{idx}_HOST={email.get('host', '')}")
        lines.append(f"EMAIL_{idx}_PORT={email.get('port', 993)}")
        lines.append(f"EMAIL_{idx}_USERNAME={email.get('username', '')}")
        lines.append(f"EMAIL_{idx}_PASSWORD={email.get('password', '')}")
        lines.append(f"EMAIL_{idx}_USE_SSL={str(email.get('use_ssl', True)).lower()}")
        lines.append(f"EMAIL_{idx}_ENABLED={str(email.get('enabled', True)).lower()}")
        lines.append("")
    
    # 项目监控配置
    lines.append("# ========================================")
    lines.append("# 项目监控配置")
    lines.append("# ========================================")
    projects = config.get('projects', [])
    for idx, project in enumerate(projects, 1):
        lines.append(f"# 项目{idx} - {project.get('name', '')}")
        lines.append(f"PROJECT_{idx}_NAME={project.get('name', '')}")
        lines.append(f"PROJECT_{idx}_PROVIDER={project.get('provider', '')}")
        lines.append(f"PROJECT_{idx}_API_KEY={project.get('api_key', '')}")
        lines.append(f"PROJECT_{idx}_THRESHOLD={project.get('threshold', 0)}")
        lines.append(f"PROJECT_{idx}_TYPE={project.get('type', 'credits')}")
        lines.append(f"PROJECT_{idx}_ENABLED={str(project.get('enabled', True)).lower()}")
        lines.append("")
    
    # 订阅配置
    lines.append("# ========================================")
    lines.append("# 订阅续费提醒配置")
    lines.append("# ========================================")
    subscriptions = config.get('subscriptions', [])
    for idx, sub in enumerate(subscriptions, 1):
        lines.append(f"# 订阅{idx} - {sub.get('name', '')}")
        lines.append(f"SUBSCRIPTION_{idx}_NAME={sub.get('name', '')}")
        lines.append(f"SUBSCRIPTION_{idx}_CYCLE_TYPE={sub.get('cycle_type', 'monthly')}")
        lines.append(f"SUBSCRIPTION_{idx}_RENEWAL_DAY={sub.get('renewal_day', 1)}")
        lines.append(f"SUBSCRIPTION_{idx}_ALERT_DAYS_BEFORE={sub.get('alert_days_before', 3)}")
        lines.append(f"SUBSCRIPTION_{idx}_AMOUNT={sub.get('amount', 0)}")
        lines.append(f"SUBSCRIPTION_{idx}_CURRENCY={sub.get('currency', 'CNY')}")
        lines.append(f"SUBSCRIPTION_{idx}_ENABLED={str(sub.get('enabled', True)).lower()}")
        if 'last_renewed_date' in sub:
            lines.append(f"SUBSCRIPTION_{idx}_LAST_RENEWED_DATE={sub['last_renewed_date']}")
        lines.append("")
    
    # 写入文件
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    print(f"✅ 已生成 .env 文件: {env_path}")
    print(f"📝 包含 {len(projects)} 个项目, {len(emails)} 个邮箱, {len(subscriptions)} 个订阅")


def update_config_with_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """更新 config.json，将敏感信息替换为环境变量引用"""
    new_config = config.copy()
    
    # 替换 Webhook URL
    if 'webhook' in new_config:
        new_config['webhook']['url'] = "${WEBHOOK_URL}"
    
    # 替换邮箱密码
    emails = new_config.get('email', [])
    for idx, email in enumerate(emails, 1):
        email['password'] = f"${{EMAIL_{idx}_PASSWORD}}"
    
    # 替换项目 API Key
    projects = new_config.get('projects', [])
    for idx, project in enumerate(projects, 1):
        project['api_key'] = f"${{PROJECT_{idx}_API_KEY}}"
    
    return new_config


def save_sanitized_config(config: Dict[str, Any], config_path: str = "config.json") -> None:
    """保存脱敏后的配置文件"""
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"✅ 已更新配置文件: {config_path} (敏感信息已替换为环境变量引用)")


def update_gitignore() -> None:
    """更新 .gitignore 确保 .env 不被提交"""
    gitignore_path = ".gitignore"
    
    # 读取现有内容
    existing_lines = []
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            existing_lines = f.read().splitlines()
    
    # 检查是否已包含 .env
    has_env = any('.env' in line and not line.strip().startswith('#') for line in existing_lines)
    
    if not has_env:
        # 添加 .env 规则
        with open(gitignore_path, 'a', encoding='utf-8') as f:
            f.write('\n# Environment variables (contains sensitive data)\n')
            f.write('.env\n')
            f.write('.env.local\n')
            f.write('.env.*.local\n')
        print(f"✅ 已更新 .gitignore 添加 .env 规则")
    else:
        print(f"ℹ️  .gitignore 已包含 .env 规则")


def main():
    """主函数"""
    print("=" * 60)
    print("🔄 配置迁移脚本")
    print("=" * 60)
    print()
    
    # 1. 加载配置
    print("📖 步骤 1/5: 读取 config.json...")
    config = load_config()
    if not config:
        print("❌ 无法继续，程序退出")
        return
    
    # 2. 备份配置
    print("\n💾 步骤 2/5: 备份原配置文件...")
    backup_config()
    
    # 3. 生成 .env 文件
    print("\n📝 步骤 3/5: 生成 .env 文件...")
    generate_env_file(config)
    
    # 4. 更新 config.json
    print("\n🔧 步骤 4/5: 更新 config.json (替换为环境变量引用)...")
    sanitized_config = update_config_with_env_vars(config)
    save_sanitized_config(sanitized_config)
    
    # 5. 更新 .gitignore
    print("\n🛡️  步骤 5/5: 更新 .gitignore...")
    update_gitignore()
    
    # 完成提示
    print("\n" + "=" * 60)
    print("✅ 迁移完成！")
    print("=" * 60)
    print("\n📋 后续步骤：")
    print("1. 检查 .env 文件确认内容正确")
    print("2. 确保 .env 文件不会被提交到 Git（已添加到 .gitignore）")
    print("3. 在生产环境中，通过环境变量或密钥管理系统注入敏感信息")
    print("4. 如需恢复原配置，使用备份文件")
    print("\n⚠️  警告：请妥善保管 .env 文件，不要分享给他人！")


if __name__ == "__main__":
    main()
