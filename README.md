# JNN Factory — Официальный сайт швейной фабрики

## О проекте
- Сайт фабрики: jnnfactory.online
- Админ-панель Directus: admin.jnnfactory.online (вход через Directus; basic auth отключён)
- Галерея: https://admin.jnnfactory.online/gallery — только для администраторов Directus
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

`https://admin.jnnfactory.online/gallery` — админ-галерея файлов сайта и медиатеки
Directus. Публичной страницы `/gallery.html` и публичного `/gallery-api/*` больше нет:
на основном домене nginx отдаёт для них 404.

Управление доступно только после входа под аккаунтом Directus с правами
администратора. Пароль проверяет сам Directus (`/auth/login`), сервис хранит
только непрозрачную серверную сессию в HttpOnly cookie `jnn_gallery_sid`.
Для API также поддерживается `Authorization: Bearer <admin token>`.

Все `/gallery-api/*` защищены middleware: без валидной админ-сессии или
Bearer-токена администратора возвращается 401/403. Мутации из браузера
дополнительно требуют CSRF-заголовок `X-CSRF-Token`.

### Переменные окружения сервиса админки
- `JNN_DIRECTUS_API` — по умолчанию `http://127.0.0.1:8055`.
- `JNN_DIRECTUS_TOKEN` (или `DIRECTUS_TOKEN`) — сервисный токен Directus для
  `files.create/update/delete` и `products_files`. Без него медиатека доступна
  только для чтения; операции записи возвращают 503.
- `JNN_DIRECTUS_UPLOADS` — каталог uploads Directus для хэшей, по умолчанию
  `/opt/directus/uploads`.
- `JNN_GALLERY_FOLDERS_FILE` — путь к manifest виртуальных папок, по умолчанию
  `admin/.gallery_folders.json` (в Git не входит). Если задан другой путь,
  добавьте его в `.gitignore` и backup.
- `JNN_ADMIN_ORIGIN` — origin админки для CSRF, по умолчанию
  `https://admin.jnnfactory.online`.
- `JNN_GALLERY_COOKIE_SECURE` — `0` только для локальной отладки по HTTP;
  в production оставлять `1`.
- `JNN_PUBLISH_WEBHOOK_SECRET` — секрет автоматической публикации из Directus.
  Без него `/webhooks/directus/publish` отвечает 503.
- `JNN_ASSETS_DIR` — необязательное переопределение каталога assets (удобно
  для локальных тестов); в production не задавать.
- `JNN_GALLERY_KEY` — остаётся только для legacy-эндпоинтов `/api/*`.
  Галерея и `/gallery-api/*` его больше не используют.

### Папки и массовые операции
Папки виртуальные: manifest хранит только привязку файла к папке, физические
URL `/assets/<file>` не меняются. Поддерживаются вложенные папки.
В галерее есть чекбоксы, «Выбрать все», массовое перемещение в папку и массовое
удаление. Перед удалением сервер проверяет использование в товарах и Git:
- используемый файл или Git-tracked файл требуют явного force-подтверждения;
- при недоступной проверке usage/Git операция запрещена (fail closed);
- force-удаление tracked-файла выполняет `git rm`, после чего нужен commit,
  иначе `deploy.sh` блокирует деплой.

### Nginx
- Публичный домен: `scripts/nginx/all_jnn.conf` — `/gallery`, `/gallery.html` и
  `/gallery-api/` отдают 404.
- Админ-домен: `scripts/nginx/admin_gallery.conf` — location-блоки для
  `/gallery`, `/gallery/static/`, `/gallery-auth/`, `/gallery-api/` и
  `/webhooks/directus/publish`. Вставить в `/etc/nginx/sites-available/admin_jnn.conf`
  до `location /`, затем `nginx -t && systemctl reload nginx`.

### Миграция автопубликации Directus
Старый flow `publish_product` ходил на `https://jnnfactory.online/gallery-api/publish`
с заголовком `x-gallery-key`. После включения новой авторизации этот путь требует
админ-сессию и для flow не подходит.

Порядок без необратимых изменений:
1. Задать `JNN_PUBLISH_WEBHOOK_SECRET` в окружении сервиса админки и
   перезапустить его.
2. Задеплоить новую версию кода и проверить, что
   `POST /webhooks/directus/publish` с секретом отвечает.
3. В Directus → Settings → Flows → `publish_product` изменить webhook:
   - URL: `https://admin.jnnfactory.online/webhooks/directus/publish`
   - заголовок: `X-Webhook-Secret: <значение JNN_PUBLISH_WEBHOOK_SECRET>`
4. Сделать тестовое обновление товара и проверить страницу, `sitemap.xml`,
   `llms.txt` и лог `/gallery-api/publish/log`.
5. Только после успешной проверки закрыть maintenance-окно.

Ручные вызовы публикации остаются на `/gallery-api/publish` и теперь требуют
входа администратора (сессия или Bearer-токен).

## Проверки
```bash
py -m py_compile admin/main.py
node --check admin/static/gallery-admin.js
py -m pytest -q
```
