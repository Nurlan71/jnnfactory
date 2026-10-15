---
name: git-ssh-deploy
description: Регламент безопасного коммита и деплоя JNN Factory на VPS через SSH
---

# Git + SSH Deploy — JNN Factory

## Конфигурация

| Переменная | Значение |
|-----------|----------|
| Проект | `D:\Info\JNN\Soft\Jnnfactory` |
| Git путь | `C:\Program Files\Git\cmd\git.exe` |
| Remote | `https://github.com/Nurlan71/jnnfactory.git` |
| VPS IP | `173.249.56.248` |
| Web root | `/var/www/jnnfactory` |
| SSH | `ssh -o ConnectTimeout=20 root@173.249.56.248` |

## Протокол деплоя

**Шаг 1 — Проверка:**
```powershell
& "C:\Program Files\Git\cmd\git.exe" -C "D:\Info\JNN\Soft\Jnnfactory" status --short
```

**Шаг 2 — Коммит (Conventional Commits):**
```powershell
& "C:\Program Files\Git\cmd\git.exe" -C "D:\Info\JNN\Soft\Jnnfactory" add -A
& "C:\Program Files\Git\cmd\git.exe" -C "D:\Info\JNN\Soft\Jnnfactory" commit -m "fix(scope): описание"
```

**Шаг 3 — Пуш:**
```powershell
& "C:\Program Files\Git\cmd\git.exe" -C "D:\Info\JNN\Soft\Jnnfactory" push origin main
```

**Шаг 4 — Деплой на VPS:**
```powershell
ssh -o ConnectTimeout=20 root@173.249.56.248 "cd /var/www/jnnfactory && git stash 2>/dev/null; git pull --no-rebase origin main 2>&1 | tail -5"
```

**Шаг 5 — Перезагрузка Nginx:**
```powershell
ssh -o ConnectTimeout=20 root@173.249.56.248 "systemctl reload nginx"
```

## Правила
1. Никаких force-push
2. Stash перед pull если есть локальные изменения на VPS
3. --no-rebase всегда
4. Бэкап перед batch-обработкой HTML: тестировать на одном файле

## Синхронизация с VPS (VPS → локально)
```powershell
& "C:\Program Files\Git\cmd\git.exe" -C "D:\Info\JNN\Soft\Jnnfactory" fetch origin
& "C:\Program Files\Git\cmd\git.exe" -C "D:\Info\JNN\Soft\Jnnfactory" reset --hard origin/main
```
**Предупреждение:** `reset --hard` удалит все незакоммиченные локальные изменения!