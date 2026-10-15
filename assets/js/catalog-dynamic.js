// JNN Dynamic Catalog — Template Card Pattern (Vanilla JS)
// Рендерит каталог из Directus API, клонируя первую карточку как шаблон.
// При недоступности API оставляет статическую разметку нетронутой.

(function () {
  'use strict';

  // Заглушка-логотип JNN показывается ТОЛЬКО если у товара нет фото.
  var PLACEHOLDER = '/assets/letuchka_nurlan.jpg';

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

    try {
      var resp = await fetch('https://admin.jnnfactory.online/items/products');
      if (!resp.ok) throw new Error('API ' + resp.status);
      var json = await resp.json();
      var products = json.data || [];

      if (!products.length) {
        console.log('JNN Catalog: нет товаров в Directus, оставляю статику');
        return;
      }

      var templateHTML = templateCard.outerHTML;
      grid.innerHTML = '';

      products.forEach(function (p) {
        var wrapper = document.createElement('div');
        wrapper.innerHTML = templateHTML;
        var card = wrapper.firstElementChild;

        // Название
        var h3 = card.querySelector('h3');
        if (h3) h3.textContent = p.name || '';

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
          if (rows) specs.innerHTML = rows;
          else if (p.bullets) specs.textContent = p.bullets;
        }

        // Фото (первое из списка). Если фото нет — подставляем заглушку-логотип.
        var img = card.querySelector('.cat-img img');
        if (img) {
          var firstImg = getFirstImage(p.image || p.img_1);
          img.src = firstImg || PLACEHOLDER;
          img.alt = p.name || '';
        }

        // Ссылка на детальную страницу
        var slug = p.slug || slugify(p.name);
        var links = card.querySelectorAll('.cat-img, .cat-link');
        links.forEach(function (a) {
          a.href = '/' + slug + '.html';
        });

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
      console.warn('JNN Catalog: Directus недоступен, оставляю статику (' + err.message + ')');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderCatalog);
  } else {
    renderCatalog();
  }
})();
