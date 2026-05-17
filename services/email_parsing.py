#!/usr/bin/env python3
from email.header import decode_header
import re


def decode_str(value):
    if value is None:
        return ""

    if isinstance(value, bytes):
        value = value.decode('utf-8', errors='ignore')

    try:
        decoded_parts = decode_header(value)
        result = []
        for content, encoding in decoded_parts:
            if isinstance(content, bytes):
                if encoding:
                    result.append(content.decode(encoding, errors='ignore'))
                else:
                    result.append(content.decode('utf-8', errors='ignore'))
            else:
                result.append(str(content))
        return ''.join(result)
    except (UnicodeDecodeError, LookupError):
        return str(value)


def extract_text_from_email(msg):
    text_content = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if "attachment" in content_disposition:
                continue

            if content_type == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        text_content.append(payload.decode(charset, errors='ignore'))
                except (UnicodeDecodeError, LookupError, AttributeError):
                    pass
            elif content_type == "text/html":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or 'utf-8'
                        html_text = payload.decode(charset, errors='ignore')
                        clean_text = re.sub(r'<[^>]+>', ' ', html_text)
                        text_content.append(clean_text)
                except (UnicodeDecodeError, LookupError, AttributeError):
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or 'utf-8'
                text_content.append(payload.decode(charset, errors='ignore'))
        except (UnicodeDecodeError, LookupError, AttributeError):
            pass

    return '\n'.join(text_content)

