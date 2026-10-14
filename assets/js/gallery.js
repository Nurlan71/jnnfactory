/* JNN Gallery — lightweight vanilla JS gallery (up to 20 photos) */
(function () {
  function initGallery(container, images) {
    if (!container || !images || images.length === 0) return;

    // Normalize: accept array of strings (URLs) or array of objects (Directus Files)
    const urls = images.map(function (img) {
      if (typeof img === 'string') return img;
      if (img && typeof img === 'object') {
        // Directus Files structure
        return img.url || img.src || img.data_url || '';
      }
      return '';
    }).filter(function (u) { return u && u.trim().length > 0; });

    if (urls.length === 0) return;

    // Build gallery markup
    container.classList.add('jnn-gallery');

    var mainWrap = document.createElement('div');
    mainWrap.className = 'jnn-gallery__main';

    var mainImg = document.createElement('img');
    mainImg.className = 'jnn-gallery__main-img';
    mainImg.src = urls[0];
    mainImg.alt = '';
    mainWrap.appendChild(mainImg);

    var thumbs = document.createElement('div');
    thumbs.className = 'jnn-gallery__thumbs';

    var activeIndex = 0;

    urls.forEach(function (url, i) {
      var t = document.createElement('button');
      t.type = 'button';
      t.className = 'jnn-gallery__thumb' + (i === 0 ? ' jnn-gallery__thumb--active' : '');
      t.setAttribute('aria-label', 'Фото ' + (i + 1));
      var ti = document.createElement('img');
      ti.src = url;
      ti.alt = '';
      ti.loading = 'lazy';
      t.appendChild(ti);
      t.addEventListener('click', function () {
        mainImg.src = url;
        activeIndex = i;
        thumbs.querySelectorAll('.jnn-gallery__thumb').forEach(function (x, idx) {
          x.classList.toggle('jnn-gallery__thumb--active', idx === i);
        });
      });
      thumbs.appendChild(t);
    });

    container.appendChild(mainWrap);
    container.appendChild(thumbs);
  }

  // Expose global API
  window.JNNGallery = {
    init: initGallery
  };

  // Auto-init: find containers with data-gallery attribute
  document.addEventListener('DOMContentLoaded', function () {
    var containers = document.querySelectorAll('[data-gallery]');
    containers.forEach(function (c) {
      var raw = c.getAttribute('data-gallery');
      try {
        var images = JSON.parse(raw);
        initGallery(c, images);
      } catch (e) {
        console.warn('JNN Gallery: invalid JSON in data-gallery', e);
      }
    });
  });
})();
