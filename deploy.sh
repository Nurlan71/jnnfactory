#!/usr/bin/env bash
set -e

echo "=== Deploy: JNN Factory ==="
cd /var/www/jnnfactory

echo "1. Pull latest changes..."
git pull origin main

echo "2. Install Python dependencies..."
pip3 install -r requirements.txt --quiet

echo "3. Restart admin service..."
systemctl daemon-reload
systemctl restart jnnfactory-admin

echo "4. Restart Nginx..."
systemctl restart nginx

echo "=== Deploy complete ==="
systemctl status jnnfactory-admin --no-pager | head -5
