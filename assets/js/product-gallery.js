// JNN Product Gallery v2 — подгрузка галереи товара из Directus (до 20 фото).
// Поддерживает: массив URL, массив объектов Directus, JSON-строку, строку через запятую.
// Режим A: контейнер [data-gallery-auto] -> модуль JNNGallery (главное фото + миниатюры).
// Режим B: статическая сетка Tilda .t989__gallery-wrapper -> дозаполнение недостающих фото.
// Плюс подтягивает цену в [data-price-auto]. Fallback: статическая вёрстка цела.
(function () {
  'use strict';

  var MAX = 20;
  var API = '/api/items/products?fields=name,price,image,gallery,slug&limit=1&filter[slug][_eq]=';

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

  function collectImages(product) {
    var urls = [];
    parseList(product.gallery).forEach(function (item) {
      var u = urlOf(item);
      if (u) urls.push(abs(u));
    });
    parseList(product.image).forEach(function (item) {
      var u = urlOf(item);
      if (u) urls.unshift(abs(u));
    });
    // дедуп + лимит 20
    var seen = {}, out = [];
    urls.forEach(function (u) { if (u && !seen[u] && out.length < MAX) { seen[u] = 1; out.push(u); } });
    return out;
  }

  function renderGallery(container, images, name) {
    if (!container || !images.length) return;
    if (window.JNNGallery && window.JNNGallery.init) {
      window.JNNGallery.init(container, images, name);
    } else {
      // Простая деградация без модуля
      container.innerHTML = images.map(function (u) {
        return '<img src="' + u + '" alt="' + (name || '') + '" loading="lazy" ' +
          'style="width:120px;height:120px;object-fit:cover;margin:4px;border-radius:8px;">';
      }).join('');
    }
    console.log('JNN Product Gallery: отрисовано фото - ' + images.length);
  }

  // Дозаполняет существующую статическую сетку Tilda недостающими фото (дизайн не меняется).
  function enhanceGrid(images, name) {
    var wrap = document.querySelector('.t989__gallery-wrapper');
    var grid = null;
    if (wrap) {
      for (var i = 0; i < wrap.children.length; i++) {
        if (wrap.children[i].tagName === 'DIV') { grid = wrap.children[i]; break; }
      }
    }
    if (!grid) return 0;

    var have = {};
    var nodes = grid.querySelectorAll('img');
    for (var k = 0; k < nodes.length; k++) {
      var src = nodes[k].getAttribute('src') || '';
      if (src) have[src] = 1;
    }

    var added = 0;
    images.forEach(function (u) {
      if (have[u] || added >= MAX) return;
      have[u] = 1;
      var cell = document.createElement('div');
      cell.style.padding = '4px';
      var img = document.createElement('img');
      img.src = u;
      img.loading = 'lazy';
      img.alt = name ? (name + ' - фото ' + (added + 2)) : 'Фото товара';
      img.style.cssText = 'width:100%;height:auto;border-radius:6px;display:block;';
      cell.appendChild(img);
      grid.appendChild(cell);
      added++;
    });
    if (added) console.log('JNN Product Gallery: добавлено фото в сетку - ' + added);
    return added;
  }

  function run() {
    var box = document.querySelector('[data-gallery-auto]');
    var slug = box ? (box.getAttribute('data-gallery-slug') || slugFromUrl()) : slugFromUrl();
    if (!slug) return;

    fetch(API + encodeURIComponent(slug))
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (j) {
        var product = (j.data || [])[0];
        if (!product) { console.warn('JNN Product Gallery: товар не найден (' + slug + ')'); return; }
        var images = collectImages(product);
        if (!images.length) return;

        if (box) {
          renderGallery(box, images, product.name);
        } else {
          enhanceGrid(images, product.name);
        }

        var priceEl = document.querySelector('[data-price-auto]');
        if (priceEl && product.price != null) {
          priceEl.textContent = 'Оптовая цена: ' + product.price + ' сом';
        }
      })
      .catch(function (e) { console.warn('JNN Product Gallery: ошибка (' + e.message + ')'); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();
