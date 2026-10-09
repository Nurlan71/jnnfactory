#!/usr/bin/env python3
"""Читает admin/data.json, обновляет DATA в scripts/cms_insert.py и запускает вставку."""
import json, re, sys

with open("/var/www/jnnfactory/admin/data.json") as f:
    new_data = json.load(f)

# Обновляем DATA в cms_insert.py
path = "/var/www/jnnfactory/scripts/cms_insert.py"
content = open(path).read()
# Простая замена DATA-блока между DATA = { ... }
start = content.find('DATA = {')
# Find the last } before the \nfor loop
for_idx = content.find('\nfor ', start)
brace_idx = content.rfind('}', start, for_idx)
new_block = "DATA = " + json.dumps(new_data, indent=4, ensure_ascii=False)
content = content[:start] + new_block + content[brace_idx+1:]
open(path, "w").write(content)
print("DATA_OK: cms_insert.py обновлён")

# Теперь запускаем cms_insert.py
exec(open("/var/www/jnnfactory/scripts/cms_insert.py").read())
