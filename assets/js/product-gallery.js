// JNN Product Gallery v1 — подгрузка галереи товара из Directus (до 20 фото)
// Контейнер: [data-gallery-auto] (slug берётся из data-gallery-slug или из URL).
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
    return (/^https?:\/\//.test(u) || u.charAt(0) === '/') ? u : '/' + u;
  }

  function collectImages(product) {
    var urls = [];
    var g = product.gallery;
    if (typeof g === 'string') { try { g = JSON.parse(g); } catch (e) { g = null; } }
    if (Array.isArray(g)) {
      g.forEach(function (item) {
        var u = typeof item === 'string' ? item : (item && (item.url || item.src));
        if (u) urls.push(abs(u));
      });
    }
    if (product.image) urls.unshift(abs(product.image));
    // дедуп + лимит 20
    var seen = {}, out = [];
    urls.forEach(function (u) { if (u && !seen[u] && out.length < MAX) { seen[u] = 1; out.push(u); } });
    return out;
  }

  function renderGallery(container, images) {
    if (!container || !images.length) return;
    if (window.JNNGallery && window.JNNGallery.init) {
      window.JNNGallery.init(container, images);
    } else {
      // Простая деградация без модуля
      container.innerHTML = images.map(function (u) {
        return '<img src="' + u + '" style="width:120px;height:120px;object-fit:cover;margin:4px;border-radius:8px;">';
      }).join('');
    }
    console.log('JNN Product Gallery: отрисовано фото — ' + images.length);
  }

  function run() {
    var box = document.querySelector('[data-gallery-auto]');
    if (!box) return;
    var slug = box.getAttribute('data-gallery-slug') || slugFromUrl();
    if (!slug) return;

    fetch(API + encodeURIComponent(slug))
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (j) {
        var product = (j.data || [])[0];
        if (!product) { console.warn('JNN Product Gallery: товар не найден (' + slug + ')'); return; }
        renderGallery(box, collectImages(product));

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
