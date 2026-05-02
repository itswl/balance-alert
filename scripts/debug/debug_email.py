#!/usr/bin/env python3
"""测试邮箱连接"""
import imaplib
import json

# 读取配置
with open('config.json', 'r') as f:
    config = json.load(f)

emails = config.get('email', [])
if isinstance(emails, dict):
    emails = [emails]

if not emails:
    print("❌ 未找到邮箱配置")
    exit(1)

for email_config in emails:
    if not email_config.get('enabled', True):
        continue

    host = email_config.get('host')
    port = email_config.get('port', 993)
    username = email_config.get('username')
    password = email_config.get('password')
    name = email_config.get('name', username)
    print(email_config)

    print(f"\n--- 测试邮箱: {name} ---")
    print(f"连接到: {host}:{port}")
    print(f"用户名: {username}")

    try:
        mail = imaplib.IMAP4_SSL(host, port, timeout=5)
        print("✅ SSL 连接成功")
        
        mail.login(username, password)
        print("✅ 登录成功")
        
        status, mailboxes = mail.list()
        print(f"✅ 邮箱列表: {status}")
        
        mail.select('INBOX')
        print("✅ 选择收件箱成功")
        
        status, messages = mail.search(None, 'ALL')
        if status == 'OK':
            email_ids = messages[0].split()
            print(f"✅ 找到 {len(email_ids)} 封邮件")
        
        mail.logout()
        print("✅ 测试完成")
        
    except imaplib.IMAP4.error as e:
        print(f"❌ IMAP 错误: {e}")
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
