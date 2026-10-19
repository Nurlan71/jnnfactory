// JNN Dynamic Catalog v5 — Template Card Pattern (Vanilla JS)
// Рендерит каталог из Directus API, клонируя первую карточку как шаблон.
// Главное фото берётся из M2M-галереи products.gallery (junction products_files,
// первое фото в админке = главное), резерв — старое имя gallery_files, поле image
// и текстовое gallery_urls. Плюс строка минимальной партии.
// Товары со снятым флагом «Показывать в каталоге на главной» пропускаются.
// При недоступности API оставляет статическую разметку нетронутой.

(function () {
  'use strict';

  // Заглушка (иконка-футболка) показывается ТОЛЬКО если у товара нет фото.
  var PLACEHOLDER = '/assets/favicon-tshirt.png';

  // Источники данных: сначала свой прокси на сайте, затем Directus напрямую.
  var API_BASES = ['/api/items/products', 'https://admin.jnnfactory.online/items/products'];
  // Новое имя M2M-поля галереи — gallery; старое — gallery_files (совместимость).
  var FIELDS = '*,gallery.directus_files_id,gallery.sort';
  var FIELDS_LEGACY = '*,gallery_files.directus_files_id,gallery_files.sort';

  async function loadProducts() {
    var tries = [
      API_BASES[0] + '?fields=' + FIELDS,
      API_BASES[1] + '?fields=' + FIELDS,
      API_BASES[0] + '?fields=' + FIELDS_LEGACY,
      API_BASES[1] + '?fields=' + FIELDS_LEGACY
    ];
    for (var i = 0; i < tries.length; i++) {
      try {
        var resp = await fetch(tries[i]);
        if (!resp.ok) throw new Error('API ' + resp.status);
        var json = await resp.json();
        if (json && Array.isArray(json.data)) return json.data;
      } catch (e) {
        console.warn('JNN Catalog: ' + tries[i] + ' — ' + e.message);
      }
    }
    return null;
  }

  // Первое фото M2M-галереи товара (порядок задаётся в админке перетаскиванием).
  function firstFileUrl(files) {
    if (!Array.isArray(files) || !files.length) return '';
    var rows = files.slice().sort(function (a, b) {
      return ((a && a.sort) || 0) - ((b && b.sort) || 0);
    });
    for (var i = 0; i < rows.length; i++) {
      var url = fileUrl(rows[i]);
      if (url) return url;
    }
    return '';
  }

  // Ссылка на фото: путь/URL, id файла или junction-строка directus_files.
  function fileUrl(value) {
    if (!value) return '';
    if (typeof value === 'string') {
      var s = value.trim();
      if (!s) return '';
      return (/^https?:\/\//.test(s) || s.charAt(0) === '/') ? s : '/assets/' + s;
    }
    if (typeof value === 'object') {
      var direct = value.url || value.src || value.data_url;
      if (direct) return direct;
      var id = value.directus_files_id || value.id || value.file;
      if (id && typeof id === 'object') id = id.id || id.uuid;
      if (id) return fileUrl(String(id));
    }
    return '';
  }

  // Быстрый заказ в WhatsApp с готовым текстом под конкретный товар.
  var WA_PHONE = '996700712212';
  var WA_PREFIX = 'Здравствуйте! Хочу рассчитать стоимость пошива оптом: ';

  function waOrderLink(name) {
    return 'https://wa.me/' + WA_PHONE + '?text=' + encodeURIComponent(WA_PREFIX + (name || ''));
  }

  // Экранирование для вставки данных CMS в разметку карточки.
  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function getFirstImage(imageValue) {
    if (!imageValue) return '';
    if (Array.isArray(imageValue)) {
      return imageValue[0] || '';
    }
    // Строка: несколько URL через запятую -> берём первый
    return String(imageValue).split(',')[0].trim();
  }

  var TRANSLIT = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y',
    'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
    'х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'
  };

  function slugify(name) {    return (name || 'product')
      .toLowerCase()
      .replace(/[«»""''’‘]/g, '')
      .split('')
      .map(function (ch) { return TRANSLIT[ch] !== undefined ? TRANSLIT[ch] : ch; })
      .join('')
      .replace(/[^a-z0-9\s-]/g, '')
      .trim()
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-');
  }

  async function renderCatalog() {
    var grid = document.querySelector('.catalog-grid');
    if (!grid) return;

    var templateCard = grid.querySelector('.cat-card');
    if (!templateCard) return;

    // Пока идёт запрос к Directus, снимаем src у фото статической вёрстки:
    // иначе браузер начинает качать их, а потом витрина заменяется — фото
    // скачивается дважды (и статикой, и из галереи товара). Плейсхолдер
    // (высота задана через aspect-ratio) сохраняется, прыжков вёрстки нет.
    grid.querySelectorAll('.cat-img img').forEach(function (img) {
      var src = img.getAttribute('src');
      if (src) {
        img.setAttribute('data-fallback-src', src);
        img.removeAttribute('src');
      }
    });
    function restoreStatic() {
      grid.querySelectorAll('.cat-img img[data-fallback-src]').forEach(function (img) {
        img.src = img.getAttribute('data-fallback-src');
      });
    }

    try {
      var products = await loadProducts();
      if (!products) throw new Error('API недоступен');

      // Флаг из админки «Показывать в каталоге на главной» (show_in_catalog).
      // Снят флаг — модель есть на сайте (своя страница), но в каталоге её нет.
      // Отсутствие поля (старые записи) считаем «показывать».
      products = products.filter(function (p) {
        var v = p.show_in_catalog;
        return !(v === false || v === 0 || v === 'false' || v === '0');
      });

      if (!products.length) {
        console.log('JNN Catalog: нет товаров в Directus, оставляю статику');
        restoreStatic();
        return;
      }

      var templateHTML = templateCard.outerHTML;
      grid.innerHTML = '';

      products.forEach(function (p) {
        var wrapper = document.createElement('div');
        wrapper.innerHTML = templateHTML;
        var card = wrapper.firstElementChild;

        // Название. В статичной вёрстке оно уже обёрнуто в ссылку на страницу товара:
        // сохраняем ссылку, меняем только текст.
        var h3 = card.querySelector('h3');
        var nameLink = h3 ? h3.querySelector('a') : null;
        if (nameLink) nameLink.textContent = p.name || '';
        else if (h3) h3.textContent = p.name || '';

        // Цена
        var price = card.querySelector('.price');
        if (price && p.price != null) {
          price.innerHTML = 'от ' + p.price + ' <small>сом</small>';
        }

        // Бейдж
        var badge = card.querySelector('.cat-badge');
        if (badge) {
          if (p.badge) { badge.textContent = p.badge; }
          else { badge.style.display = 'none'; }
        }

        // Артикул
        var art = card.querySelector('.cat-art');
        if (art) art.textContent = p.code || '';

        // Описание
        var desc = card.querySelector('.cat-desc');
        if (desc) desc.textContent = p.description || p.subtitle || '';

        // Характеристики — как в оригинальной вёрстке: Ткань / Состав / Размеры
        var specs = card.querySelector('.cat-specs');
        if (specs) {
          var rows = '';
          if (p.fabric) rows += '<div>Ткань: <b>' + esc(p.fabric) + '</b></div>';
          if (p.composition_density) {
            var cd = String(p.composition_density);
            var dot = cd.indexOf(' · ');
            rows += dot > 0
              ? '<div>Состав: <b>' + esc(cd.slice(0, dot)) + '</b>' + esc(cd.slice(dot)) + '</div>'
              : '<div>Состав: <b>' + esc(cd) + '</b></div>';
          }
          if (p.sizes) rows += '<div>Размеры: <b>' + esc(p.sizes) + '</b></div>';
          if (p.min_order) {
            rows += '<div style="margin-top:8px;padding-top:8px;border-top:1px dashed var(--line);">'
              + esc(p.min_order) + '</div>';
          }
          if (rows) specs.innerHTML = rows;
          else if (p.bullets) specs.textContent = p.bullets;
        }

        // Фото (первое из галереи товара). Если фото нет — подставляем заглушку-логотип.
        var img = card.querySelector('.cat-img img');
        if (img) {
          var firstImg = firstFileUrl(p.gallery) || firstFileUrl(p.gallery_files);
          if (!firstImg) firstImg = getFirstImage(p.image || p.img_1);
          if (!firstImg) firstImg = getFirstImage(p.gallery_urls);
          img.src = firstImg || PLACEHOLDER;
          img.alt = p.name || '';
          img.removeAttribute('data-fallback-src');
        }

        // Кликабельны: фото, название (H3) и кнопка «Подробнее»
        var slug = p.slug || slugify(p.name);
        var url = '/' + slug + '.html';
        var links = card.querySelectorAll('.cat-img, .cat-link, .cat-name-link');
        links.forEach(function (a) {
          a.href = url;
        });
        // Если название ещё не ссылка (шаблон из старой разметки) — оборачиваем в ссылку
        if (h3 && !h3.querySelector('a')) {
          var a2 = document.createElement('a');
          a2.className = 'cat-name-link';
          a2.href = url;
          a2.textContent = p.name || '';
          h3.textContent = '';
          h3.appendChild(a2);
        }

        // Кнопка быстрого заказа в WhatsApp с названием товара
        var order = card.querySelector('.cat-order');
        if (order) {
          order.href = waOrderLink(p.name);
          order.setAttribute('aria-label', 'Заказать «' + (p.name || '') + '» в WhatsApp');
        }

        grid.appendChild(card);
      });

      console.log('JNN Catalog: отрисовано ' + products.length + ' товаров из Directus');
    } catch (err) {
      restoreStatic();
      console.warn('JNN Catalog: Directus недоступен, оставляю статику (' + err.message + ')');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderCatalog);
  } else {
    renderCatalog();
  }
})();
