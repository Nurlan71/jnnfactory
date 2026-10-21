#!/usr/bin/env bash
set -e

echo "=== Deploy: JNN Factory ==="
cd /var/www/jnnfactory

# Удаления/переименования в assets, сделанные из галереи, стагируются
# через git rm/git mv. Пока они не закоммичены, git pull вернёт старый файл.
if git status --porcelain -- assets | grep -Eq '^(D|R|.D|.R)'; then
  echo "ERROR: в assets есть незакоммиченные удаления/переименования."
  echo "Сначала commit (и push), иначе деплой воскресит удалённые файлы."
  git status --short -- assets
  exit 1
fi

echo "1. Pull latest changes..."
git pull origin main

echo "2. Install Python dependencies..."
venv/bin/pip install -r requirements.txt --quiet

echo "3. Restart admin service..."
systemctl daemon-reload
systemctl restart jnnfactory-admin

echo "4. Restart Nginx..."
systemctl restart nginx

echo "=== Deploy complete ==="
systemctl status jnnfactory-admin --no-pager | head -5
