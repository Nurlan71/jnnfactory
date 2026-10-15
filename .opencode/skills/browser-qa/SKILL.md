---
name: browser-qa
description: Автономное тестирование страниц JNN Factory в headless-браузере через Browser MCP
---

# Browser QA — JNN Factory Autonomous Testing

## Обязательный рабочий процесс

1. После любых изменений в HTML/JS/CSS всегда открывай страницу через Browser MCP:
   ```js
   const tab = await tools.browser.tabs.open({ url: "https://jnnfactory.online/", focus: false });
   await tools.browser.wait({ tabID: tab.id, timeout: 5000 }).catch(() => {});
   ```

2. **Консоль браузера** — собирай все логи:
   ```js
   const logs = await tools.browser.console({ tabID: tab.id });
   const errors = logs.messages.filter(m => m.level === 'error');
   ```

3. **Сетевые ошибки** — фильтруй 404, 500:
   ```js
   const net = await tools.browser.network.list({ tabID: tab.id });
   const bad = net.requests.filter(r => r.statusCode >= 400 && !r.url.includes('google-analytics'));
   ```

4. **При обнаружении 404** — не завершай задачу. Проверь локальные файлы и .gitignore.

5. **Визуальная проверка** DOM:
   ```js
   const dom = await tools.browser.evaluate({
     tabID: tab.id,
     script: `JSON.stringify({cards: document.querySelectorAll('.catalog-grid .cat-card').length})`
   });
   ```

6. При необходимости — скриншот (требует видимого окна браузера).

## Критерии
- 0 ошибок в консоли
- 0 запросов 4xx/5xx (кроме Google Analytics)
- Каталог отрисован (cards > 0)
- Фавикон загружается
- Галерея на детальных страницах работает

## Страницы для проверки
- Главная: https://jnnfactory.online/
- Товар: https://jnnfactory.online/velvet-suit.html
- Товар: https://jnnfactory.online/sweatshirt-fleece.html
- Админка: https://admin.jnnfactory.online/