#!/usr/bin/env python3
import hashlib


def get_email_id(msg) -> str:
    message_id = (msg.get('Message-ID', '') or '').strip()
    if message_id:
        return message_id
    date = msg.get('Date', '') or ''
    subject = msg.get('Subject', '') or ''
    sender = msg.get('From', '') or ''
    raw = f"{date}|{subject}|{sender}"
    return hashlib.md5(raw.encode('utf-8', errors='ignore')).hexdigest()

