#!/usr/bin/env python3
"""Bind the existing private Telegram bot to a meeting owner; sends no messages."""
import argparse
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit
import meeting_report as report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', help='Open WebUI owner ID; inferred only when exactly one owner exists')
    parser.add_argument('--openwebui-url', default='', help='Existing HTTPS Open WebUI URL, optional')
    parser.add_argument('--update-url', action='store_true', help='Update only the dashboard origin in an existing binding; preserve bot/account settings')
    args = parser.parse_args()
    home = Path.home()/'ai-platform/ingestion-monitor'
    if args.update_url:
        url = urlsplit(args.openwebui_url)
        if url.scheme != 'https' or not url.netloc or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
            parser.error('Supply --openwebui-url with the existing HTTPS Open WebUI origin, without a path')
        target = home/'meeting-notifications.json'
        if not target.is_file():
            parser.error('Create the existing owner/bot binding first')
        binding = json.loads(target.read_text(encoding='utf-8'))
        if not isinstance(binding.get('owner_chats'), dict) or not binding['owner_chats']:
            parser.error('Existing owner binding is invalid; nothing changed')
        backup = home/('meeting-notifications.pre-dashboard-' + str(time.time_ns()) + '.json')
        report.save(backup, binding)
        backup.chmod(0o600)
        binding['openwebui_url'] = args.openwebui_url.rstrip('/')
        report.save(target, binding)
        target.chmod(0o600)
        print('Dashboard links configured. Existing bot and owner mappings preserved. No message sent.')
        return
    config = json.loads((home/'monitor.json').read_text(encoding='utf-8'))
    if not (home/'telegram-token.txt').is_file() or not config.get('telegram_chat_id'):
        parser.error('Configure the existing monitor bot first; credentials were not changed')
    with sqlite3.connect((Path.home()/'ai-platform/meetings/jobs.sqlite3').as_uri()+'?mode=ro', uri=True) as c:
        owners = [r[0] for r in c.execute('SELECT DISTINCT owner FROM jobs')]
    owner = args.owner
    if not owner and len(owners) == 1:
        owner = owners[0]
    if not owner or owner not in owners:
        parser.error('Specify --owner with the intended Open WebUI owner ID from the jobs database')
    if args.openwebui_url:
        p = urlsplit(args.openwebui_url)
        if p.scheme != 'https' or not p.netloc or p.username or p.password or p.query or p.fragment:
            parser.error('Use the existing HTTPS Open WebUI address without credentials/query/fragment')
    target = home/'meeting-notifications.json'
    if target.exists():
        parser.error('Binding already exists; inspect it deliberately rather than overwriting it')
    report.save(target, {'enabled': True, 'owner_chats': {owner: config['telegram_chat_id']}, 'openwebui_url': args.openwebui_url})
    target.chmod(0o600)
    print('Meeting notifications configured for one owner. Existing bot/token unchanged. No message sent.')


if __name__ == '__main__':
    main()
