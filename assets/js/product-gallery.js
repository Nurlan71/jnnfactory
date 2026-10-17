// JNN Product Gallery v3 — галерея товара из Directus (до 20 фото).
// Источник фото: M2M products.gallery -> directus_files (junction products_files;
// порядок задаётся перетаскиванием в админке; первое фото - главное).
// Резерв: старое имя поля gallery_files, текстовое gallery_urls и image
// (пути /assets/...), затем статическая вёрстка Tilda.
// Режим A: контейнер [data-gallery-auto] -> модуль JNNGallery (главное фото + миниатюры).
// Режим B: статическая сетка Tilda .t989__gallery-wrapper — ячейки и стили сохраняются,
// меняются только сами фото (список и порядок из админки).
// Плюс цена в [data-price-auto] и строка минимальной партии на странице товара.
// Fallback: если API недоступен, статическая вёрстка остаётся как есть.
(function () {
  'use strict';

  var MAX = 20;
  // Поля галереи: gallery — M2M-поле (Directus отдаёт junction-строки
  // directus_files_id + sort). FIELDS_LEGACY — старое имя поля (совместимость).
  var FIELDS = 'name,price,image,min_order,slug,gallery_urls,gallery.directus_files_id,gallery.sort';
  var FIELDS_LEGACY = 'name,price,image,min_order,slug,gallery,gallery_files.directus_files_id,gallery_files.sort';
  var API = '/api/items/products?fields=';
  var QUERY_ONE = '&limit=1&filter[slug][_eq]=';
  var QUERY_ALL = '&limit=100';

  function request(fields, tail) {
    return fetch(API + fields + tail).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  // Новые поля; если схема ещё старая (нет gallery) — повторяем со gallery_files.
  function apiGet(tail) {
    return request(FIELDS, tail).catch(function (e) {
      console.warn('JNN Product Gallery: повтор со старым полем gallery_files (' + e.message + ')');
      return request(FIELDS_LEGACY, tail);
    });
  }

  function slugFromUrl() {
    var p = location.pathname.replace(/\/+$/, '');
    var last = p.split('/').pop() || '';
    return last.replace(/\.html?$/i, '');
  }

  function abs(u) {
    if (!u) return '';
    u = String(u).trim();
    if (!u) return '';
    return (/^https?:\/\//.test(u) || u.charAt(0) === '/') ? u : '/' + u;
  }

  // Приводит значение поля к массиву: массив, JSON-строка или строка через запятую.
  function parseList(v) {
    if (v == null || v === '') return [];
    if (Array.isArray(v)) return v;
    if (typeof v === 'string') {
      var t = v.trim();
      if (t.charAt(0) === '[') {
        try { var j = JSON.parse(t); if (Array.isArray(j)) return j; } catch (e) { /* не JSON */ }
      }
      return t.split(',').map(function (x) { return x.trim(); }).filter(Boolean);
    }
    return [];
  }

  // Ссылка на фото товара. Понимает все варианты значения из Directus:
  // прямой путь/URL ("/assets/photo.jpg", "https://..."), id файла ("uuid"),
  // объект файла ({url}) и junction-строку M2M ({directus_files_id: "uuid"}
  // или {directus_files_id: {id: "uuid"}}). Возвращает путь /assets/<id>.
  function fileUrl(value) {
    if (!value) return '';
    if (typeof value === 'string') {
      var s = value.trim();
      if (!s) return '';
      return (/^https?:\/\//.test(s) || s.charAt(0) === '/') ? abs(s) : '/assets/' + s;
    }
    if (typeof value === 'object') {
      var direct = value.url || value.src || value.data_url;
      if (direct) return abs(direct);
      var id = value.directus_files_id || value.id || value.file;
      if (id && typeof id === 'object') id = id.id || id.uuid;
      if (id) return fileUrl(String(id));
    }
    return '';
  }

  // Фото из M2M-галереи Directus: junction-строки, порядок по полю sort.
  // Новое имя поля — gallery; старое (на случай отката схемы) — gallery_files.
  function m2mImages(product) {
    var rows = product.gallery;
    if (!Array.isArray(rows) || !rows.length) rows = product.gallery_files;
    if (!Array.isArray(rows) || !rows.length) return [];
    return rows.slice()
      .sort(function (a, b) { return ((a && a.sort) || 0) - ((b && b.sort) || 0); })
      .map(fileUrl)
      .filter(Boolean);
  }

  function collectImages(product) {
    var urls = m2mImages(product);
    if (!urls.length) {
      // Резерв: текстовое gallery_urls (новое имя) или gallery (старое) + image
      var legacy = (product.gallery_urls !== undefined) ? product.gallery_urls : product.gallery;
      parseList(legacy).forEach(function (item) {
        var u = fileUrl(item);
        if (u) urls.push(u);
      });
      parseList(product.image).forEach(function (item) {
        var u = fileUrl(item);
        if (u) urls.unshift(u);
      });
    }
    var seen = {}, out = [];
    urls.forEach(function (u) { if (u && !seen[u] && out.length < MAX) { seen[u] = 1; out.push(u); } });
    return out;
  }

  function renderGallery(container, images, name) {
    if (!container || !images.length) return;
    if (window.JNNGallery && window.JNNGallery.init) {
      window.JNNGallery.init(container, images, name);
    } else {
      container.innerHTML = images.map(function (u) {
        return '<img src="' + u + '" alt="' + (name || '') + '" loading="lazy" ' +
          'style="width:120px;height:120px;object-fit:cover;margin:4px;border-radius:8px;">';
      }).join('');
    }
    console.log('JNN Product Gallery: отрисовано фото - ' + images.length);
  }

  // Сетка галереи Tilda (.t989__gallery-wrapper): вёрстка и стили ячеек сохраняются,
  // меняются только фото — их список и порядок берутся из админки (Directus).
  // Ячеек становится столько же, сколько фото в админке (до 20).
  function galleryGrid() {
    var wrap = document.querySelector('.t989__gallery-wrapper');
    if (!wrap) return null;
    for (var i = 0; i < wrap.children.length; i++) {
      if (wrap.children[i].tagName === 'DIV' && wrap.children[i].querySelector('img')) return wrap.children[i];
    }
    for (var k = 0; k < wrap.children.length; k++) {
      if (wrap.children[k].tagName === 'DIV') return wrap.children[k];
    }
    return null;
  }

  // Скрывает картинки, которых нет на сервере (чтобы не показывать «битые» иконки).
  function hideBroken(grid) {
    var imgs = grid.querySelectorAll('img');
    for (var i = 0; i < imgs.length; i++) {
      (function (img) {
        var drop = function () {
          var cell = img.parentNode;
          if (cell && cell.parentNode === grid) grid.removeChild(cell);
          else img.style.display = 'none';
        };
        if (img.complete && img.naturalWidth === 0) drop();
        else img.addEventListener('error', drop);
      })(imgs[i]);
    }
  }

  function syncGrid(images, name) {
    var grid = galleryGrid();
    if (!grid) return 0;
    if (!images.length) { hideBroken(grid); return 0; }

    name = name || 'Фото товара';
    var total = Math.min(images.length, MAX);
    var cells = [];
    for (var i = 0; i < grid.children.length; i++) cells.push(grid.children[i]);
    var tpl = cells.length ? cells[0].cloneNode(false) : null;

    // лишние ячейки убираем, недостающие добавляем по образцу первой (стили сохраняются)
    while (cells.length > total) { grid.removeChild(cells.pop()); }
    for (var n = 0; n < total; n++) {
      var cell = grid.children[n];
      if (!cell) {
        cell = tpl ? tpl.cloneNode(false) : document.createElement('div');
        cell.style.padding = cell.style.padding || '4px';
        grid.appendChild(cell);
      }
      var img = cell.querySelector('img');
      if (!img) {
        img = document.createElement('img');
        img.style.cssText = 'width:100%;height:auto;border-radius:6px;display:block;';
        img.loading = 'lazy';
        img.alt = name + ' - фото ' + (n + 1);
        cell.appendChild(img);
      }
      if (img.getAttribute('src') !== images[n]) img.setAttribute('src', images[n]);
    }
    console.log('JNN Product Gallery: в сетке ' + total + ' фото (из админки)');
    return total;
  }

  // Строка минимальной партии: дописываем в блок характеристик страницы товара,
  // если её там ещё нет (в статике она уже есть — тогда ничего не делаем).
  function injectMinOrder(text) {
    if (!text) return;
    var blocks = document.querySelectorAll('[data-min-order], .t165__text');
    for (var i = 0; i < blocks.length; i++) {
      var el = blocks[i];
      if (el.getAttribute('data-min-order-done')) continue;
      var isTarget = el.hasAttribute('data-min-order') || /Артикул/.test(el.textContent || '');
      if (!isTarget) continue;
      el.setAttribute('data-min-order-done', '1');
      if ((el.textContent || '').indexOf(text) >= 0) return;
      el.insertAdjacentHTML('beforeend', '<br/>• ' + text);
      return;
    }
  }

  // Товар по слагу страницы. Если точного совпадения нет (напр. адрес
  // women-hoodies-oversize, а слаг товара women-hoodies) — берём самый длинный
  // слаг-префикс адреса.
  function findProduct(slug) {
    return apiGet(QUERY_ONE + encodeURIComponent(slug))
      .then(function (j) {
        var p = (j.data || [])[0];
        if (p) return p;
        return apiGet(QUERY_ALL)
          .then(function (j2) {
            var best = null;
            (j2.data || []).forEach(function (cand) {
              var s = cand && cand.slug;
              if (s && slug.indexOf(s) === 0 && (!best || s.length > best.slug.length)) best = cand;
            });
            if (best) console.log('JNN Product Gallery: слаг "' + slug + '" сопоставлен товару "' + best.slug + '"');
            return best;
          });
      });
  }

  function run() {
    var box = document.querySelector('[data-gallery-auto]');
    var slug = box ? (box.getAttribute('data-gallery-slug') || slugFromUrl()) : slugFromUrl();
    if (!slug) return;

    findProduct(slug)
      .then(function (product) {
        if (!product) { console.warn('JNN Product Gallery: товар не найден (' + slug + ')'); return; }
        var images = collectImages(product);

        if (images.length) {
          if (box) {
            renderGallery(box, images, product.name);
          } else {
            syncGrid(images, product.name);
          }
        } else {
          var g = galleryGrid();
          if (g) hideBroken(g);
        }

        var priceEl = document.querySelector('[data-price-auto]');
        if (priceEl && product.price != null) {
          priceEl.textContent = 'Оптовая цена: ' + product.price + ' сом';
        }

        injectMinOrder(product.min_order);
      })
      .catch(function (e) { console.warn('JNN Product Gallery: ошибка (' + e.message + ')'); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();
