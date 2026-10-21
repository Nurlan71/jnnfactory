
### ZERO-DESTRUCTION GUARDRAIL (CRITICAL)
1. Файл /var/www/jnnfactory/index.html является эталонным дизайном JNN Factory.
2. ЗАПРЕЩЕНО полностью перезаписывать index.html.
3. Разрешены только точечные правки текстовых блоков или подключение внешних скриптов.
4. Перед любой модификацией обязательно создавай резервную копию в /var/www/jnnfactory/backups/.

### Публикация товаров из Directus (admin/publish_product.py)
Товар добавляется в Directus (коллекция `products`) — страница `/<slug>.html`, `sitemap.xml` и `llms.txt` обновляются автоматически.

- Модуль: `admin/publish_product.py` (Python 3, только стандартная библиотека, те же проверки, что в `_scripts/build_product_pages.js`).
- Эталон вёрстки: `women-tshirt-letuchka.html` копируется целиком, замены — только точными подстроками; если якорь не найден ровно один раз, публикация падает и ничего не пишет.
- Страницы, собранные пайплайном, помечены `<!-- jnn:publish slug=... hash=... -->`. Файлы без маркера (ручные) не перезаписываются: нужен `--force`.
- Черновик (`show_in_catalog = false`) публикуется с `meta robots "noindex, follow"` и без записей в sitemap/llms.
- Существующие строки `llms.txt` / `llms-full.txt` не переписываются: новые модели дописываются, прежние остаются как есть (`--refresh-llms` перезапишет данными из Directus).
- Ручной запуск: `venv/bin/python -m admin.publish_product --slug <slug> | --sync | --all-missing | --unpublish <slug> | --list`.
- Ручные API админки: `POST /gallery-api/publish` (требует админ-сессию Directus или Bearer-токен администратора), `GET /gallery-api/publish/status`, `GET /gallery-api/publish/log`.
- Автоматика на VPS: флоу Directus `publish_product` (события `items.create`/`items.update` → `POST /webhooks/directus/publish` с заголовком `X-Webhook-Secret`) и systemd-таймер `jnnfactory-publish.timer` (сверка с Directus каждые 5 минут). Секрет — `JNN_PUBLISH_WEBHOOK_SECRET`; старый `x-gallery-key` для flow больше не используется.
