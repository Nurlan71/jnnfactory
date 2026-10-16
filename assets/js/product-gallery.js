// JNN Product Gallery v3 — галерея товара из Directus (до 20 фото).
// Источник фото: M2M products.gallery_files -> directus_files (порядок задаётся
// перетаскиванием в админке; первое фото - главное). Резерв: поля gallery / image
// (пути /assets/...), затем статическая вёрстка Tilda.
// Режим A: контейнер [data-gallery-auto] -> модуль JNNGallery (главное фото + миниатюры).
// Режим B: статическая сетка Tilda .t989__gallery-wrapper — ячейки и стили сохраняются,
// меняются только сами фото (список и порядок из админки).
// Плюс цена в [data-price-auto] и строка минимальной партии на странице товара.
// Fallback: если API недоступен, статическая вёрстка остаётся как есть.
(function () {
  'use strict';

  var MAX = 20;
  var FIELDS = 'name,price,image,gallery,min_order,slug,gallery_files.directus_files_id,gallery_files.sort';
  var API = '/api/items/products?fields=' + FIELDS + '&limit=1&filter[slug][_eq]=';
  var API_ALL = '/api/items/products?fields=' + FIELDS + '&limit=100';

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

  function urlOf(item) {
    if (!item) return '';
    if (typeof item === 'string') return item;
    return item.url || item.src || item.data_url || item.filename_download || '';
  }

  // Фото из M2M-галереи Directus: junction-строки, порядок по полю sort.
  function m2mImages(product) {
    var rows = product.gallery_files;
    if (!Array.isArray(rows) || !rows.length) return [];
    return rows.slice()
      .sort(function (a, b) { return ((a && a.sort) || 0) - ((b && b.sort) || 0); })
      .map(function (r) {
        var id = r && (r.directus_files_id || (typeof r === 'string' ? r : ''));
        return id ? '/assets/' + id : '';
      })
      .filter(Boolean);
  }

  function collectImages(product) {
    var urls = m2mImages(product);
    if (!urls.length) {
      // Резерв: старое поле gallery (пути/объекты) + image
      parseList(product.gallery).forEach(function (item) {
        var u = urlOf(item);
        if (u) urls.push(abs(u));
      });
      parseList(product.image).forEach(function (item) {
        var u = urlOf(item);
        if (u) urls.unshift(abs(u));
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
    return fetch(API + encodeURIComponent(slug))
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (j) {
        var p = (j.data || [])[0];
        if (p) return p;
        return fetch(API_ALL)
          .then(function (r2) { return r2.ok ? r2.json() : { data: [] }; })
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
