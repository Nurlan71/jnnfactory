/* JNN Gallery — lightweight vanilla JS gallery (up to 20 photos) */
(function () {
  var MAX = 20;

  function normalize(images) {
    var list = [];
    if (typeof images === 'string') {
      var t = images.trim();
      if (t.charAt(0) === '[') {
        try { images = JSON.parse(t); } catch (e) { images = t.split(','); }
      } else {
        images = t.split(',');
      }
    }
    if (!Array.isArray(images)) return list;
    images.forEach(function (img) {
      var u = '';
      if (typeof img === 'string') u = img;
      else if (img && typeof img === 'object') u = img.url || img.src || img.data_url || img.filename_download || '';
      if (u && String(u).trim()) list.push(String(u).trim());
    });
    return list.slice(0, MAX);
  }

  function initGallery(container, images, name) {
    if (!container) return;
    var urls = normalize(images);
    if (urls.length === 0) return;

    container.innerHTML = '';
    container.classList.add('jnn-gallery');

    var mainWrap = document.createElement('div');
    mainWrap.className = 'jnn-gallery__main';

    var mainImg = document.createElement('img');
    mainImg.className = 'jnn-gallery__main-img';
    mainImg.src = urls[0];
    mainImg.alt = name ? (name + ' - фото 1') : 'Фото товара';
    mainWrap.appendChild(mainImg);

    var thumbs = document.createElement('div');
    thumbs.className = 'jnn-gallery__thumbs';

    urls.forEach(function (url, i) {
      var t = document.createElement('button');
      t.type = 'button';
      t.className = 'jnn-gallery__thumb' + (i === 0 ? ' jnn-gallery__thumb--active' : '');
      t.setAttribute('aria-label', 'Фото ' + (i + 1));
      var ti = document.createElement('img');
      ti.src = url;
      ti.alt = name ? (name + ' - фото ' + (i + 1)) : '';
      ti.loading = 'lazy';
      t.appendChild(ti);
      t.addEventListener('click', function () {
        mainImg.src = url;
        mainImg.alt = name ? (name + ' - фото ' + (i + 1)) : 'Фото товара';
        thumbs.querySelectorAll('.jnn-gallery__thumb').forEach(function (x, idx) {
          x.classList.toggle('jnn-gallery__thumb--active', idx === i);
        });
      });
      thumbs.appendChild(t);
    });

    container.appendChild(mainWrap);
    if (urls.length > 1) container.appendChild(thumbs);
  }

  // Expose global API
  window.JNNGallery = {
    init: initGallery
  };

  // Auto-init: find containers with data-gallery attribute
  document.addEventListener('DOMContentLoaded', function () {
    var containers = document.querySelectorAll('[data-gallery]');
    containers.forEach(function (c) {
      if (c.hasAttribute('data-gallery-auto')) return; // обрабатывает product-gallery.js
      initGallery(c, c.getAttribute('data-gallery'));
    });
  });
})();
