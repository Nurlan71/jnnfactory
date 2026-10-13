#!/usr/bin/env python3
"""Минимальный скрипт вставки данных CMS (вызывается через /api/save -> apply.py)."""
import re, json, sys
DATA = {
    "test": "ok"
}
for fname, item in DATA.items():
    path = f"/var/www/jnnfactory/{fname}"
    try:
        html = open(path).read()
        html = re.sub(r"<title>.*?</title>", f"<title>{item.get('title','')}</title>", html, flags=re.S)
        html = re.sub(r'<meta name="description" content=".*?">', f'<meta name="description" content="{item.get("desc","")}">', html, flags=re.S)
        open(path, "w").write(html)
        print(f"OK: {fname}")
    except Exception as e:
        print(f"ERR: {fname} -> {e}")
