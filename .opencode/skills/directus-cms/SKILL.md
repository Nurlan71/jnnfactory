---
name: directus-cms
description: Стандарт работы с Directus API и архитектурой управления сайтом JNN Factory
---

# Directus CMS — JNN Factory

## Конфигурация

| Параметр | Значение |
|----------|----------|
| API (публичный) | `https://admin.jnnfactory.online/items/products` |
| API (локально) | `http://127.0.0.1:8055` |
| Контейнер | `jnn-directus` (Docker) |
| Директория | `/opt/directus` |
| База | SQLite `/opt/directus/database/data.db` |

## Аутентификация (API)

```python
import requests
D = "http://127.0.0.1:8055"
L = {"email": "nurlan710201@gmail.com", "password": "..."}
t = requests.post(f"{D}/auth/login", json=L).json()["data"]["access_token"]
h = {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}
```

## Коллекция products (товары)

| Поле | Тип | Назначение |
|------|-----|-----------|
| `name` | string | Название |
| `code` | string | Артикул + категория |
| `price` | integer | Цена (сом) |
| `description` | text | Краткое описание |
| `fabric` | string | Ткань |
| `composition_density` | string | Состав/плотность |
| `sizes` | string | Размеры |
| `badge` | string | Бейдж (ХИТ/NEW) |
| `bullets` | text | Характеристики |
| `image` | string | Фото (список через запятую) |
| `slug` | string | URL детальной страницы |

## Template Card — обязательно

Клонировать существующую `.cat-card` через `cloneNode(true)` — создание новых элементов ломает Tilda-вёрстку.

```js
const templateHTML = grid.querySelector('.cat-card').outerHTML;
grid.innerHTML = '';
products.forEach(p => {
  const wrapper = document.createElement('div');
  wrapper.innerHTML = templateHTML;
  const card = wrapper.firstElementChild;
  // подстановка полей...
  grid.appendChild(card);
});
```

## Поле image — первое фото

```js
function getFirstImage(val) {
  if (!val) return '';
  return String(val).split(',')[0].trim();
}
```

## Галерея (до 20 фото)

- Модуль: `assets/js/gallery.js`
- Стили: `assets/css/gallery.css`
- Разметка: `<div data-gallery='["url1","url2"]'></div>`

## Карта slug → страница

| Товар | slug |
|-------|------|
| Футболка «Летучка» | `women-tshirt-letuchka` |
| Футболка оверсайз | `women-tshirt-oversize` |
| Худи классик | `women-hoodies` |
| Мужская футболка | `men` |
| Свитшот оверсайз | `sweatshirt-futer` |
| Лонгслив базовый | `women-longsleeve-classic` |
| Зип-худи | `zip-hoodie-classic` |
| Костюм вельветовый | `velvet-suit` |
| Джоггеры | `women-pants` |
| Брюки палаццо | `women-pants-list` |

## Архитектура управления сайтом

### site_global (Singleton) — глобальные настройки
- `phone`, `whatsapp`, `telegram`, `email`
- `logo`, `address`
- `footer_text`, `copyright`

### pages_content — блоки главной
- `slug` (страница), `section` (блок), `content` (JSON)

### blog_posts — блог
- `title`, `slug`, `date`, `cover`, `body`

### products (расширение)
- Поле `gallery` типа Files (M2M) для до 20 фото

## Публичный доступ
```python
requests.post(f"{D}/permissions", headers=h, json={
    "policy": policy_id, "collection": "products",
    "action": "read", "fields": ["*"]
})
```

## Проверка API
```bash
curl -s http://127.0.0.1:8055/items/products | python3 -m json.tool | head -20
```