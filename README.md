# JNN Factory — Официальный сайт швейной фабрики

## О проекте
- Сайт фабрики: jnnfactory.online
- Админ-панель: admin.jnnfactory.online (auth: basic)
- Бэкенд: FastAPI/uvicorn (порт 5000)
- Сток-API: Docker (порт 8095) — /health, /api/v1/stock/velvet-640
- Nginx: SSL (Let's Encrypt), proxy, CORS

## Каталог (12 моделей)
- Футболки, худи, лонгсливы, свитшоты, зип-худи, костюмы
- Женская одежда, мужская одежда

## Установка
```bash
docker build -t jnn-stock-api .
docker run -p 8095:5000 jnn-stock-api
```

## Структура
- `/admin/` — CMS (index.html, settings.json, data.json)
- `/assets/` — медиа
- `/backups/` — резервные копии
- `sitemap.xml`, `robots.txt`

## Галерея и медиатека
`/gallery` — админ-галерея файлов сайта и медиатеки Directus.

Переменные окружения сервиса админки:
- `JNN_GALLERY_KEY` или `admin/.gallery_key` — ключ записи (обязателен для загрузки, переименования, удаления и папок).
- `JNN_DIRECTUS_TOKEN` (или `DIRECTUS_TOKEN`) — токен Directus: `files.create/update/delete` и чтение/создание `products_files` (для привязки и `sort`). Без него медиатека доступна только для чтения; операции возвращают 503.
- `JNN_DIRECTUS_API` — по умолчанию `http://127.0.0.1:8055`.
- `JNN_DIRECTUS_UPLOADS` — каталог uploads Directus для хэшей, по умолчанию `/opt/directus/uploads`.
- `JNN_GALLERY_FOLDERS_FILE` — путь к manifest виртуальных папок, по умолчанию `admin/.gallery_folders.json` (в Git не входит). Если задан другой путь, добавьте его в `.gitignore` и backup.

Папки виртуальные: физические URL `/assets/<file>` не меняются. Для tracked-файлов force-удаление/переименование выполняется через `git rm`/`git mv`; `deploy.sh` блокирует деплой, пока такие изменения не закоммичены. Нативную загрузку в админке Directus нельзя перехватить без Directus flow/hook — для неё есть кнопка «SEO-имя» на карточке медиатеки.
