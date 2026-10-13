# JNN Factory — Официальный сайт швейной фабрики

## О проекте
- Сайт фабрики: jnnfactory.online
- Админ-панель: admin.jnnfactory.online (auth: basic)
- Бэкенд: Flask (порт 5000)
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
