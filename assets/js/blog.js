// JNN Blog v1 — вывод статей из Directus (/api/items/blog_posts)
// Список: элемент [data-jnn-blog]. Детальная: [data-jnn-blog-post] (по ?slug=)
// Fallback: при недоступности API контейнер остаётся пустым, статическая вёрстка цела.
(function () {
  'use strict';

  var LIST_URL = '/api/items/blog_posts?fields=title,slug,date,cover,excerpt,body&sort=-date&limit=12';
  var DETAIL_URL = '/api/items/blog_posts?fields=title,slug,date,cover,excerpt,body&limit=1&filter[slug][_eq]=';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function fmtDate(s) {
    if (!s) return '';
    var d = new Date(s);
    if (isNaN(d.getTime())) return String(s);
    try {
      return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
    } catch (e) {
      return String(s);
    }
  }

  function abs(u) {
    if (!u) return '';
    if (/^https?:\/\//.test(u) || u.charAt(0) === '/') return u;
    return '/' + u;
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderList(container, posts) {
    container.innerHTML = '';
    if (!posts || !posts.length) {
      container.appendChild(el('div', 'blog-empty', 'Статьи скоро появятся.'));
      return;
    }
    posts.forEach(function (p) {
      var card = el('a', 'blog-card');
      card.href = '/blog-post.html?slug=' + encodeURIComponent(p.slug || '');

      var cover = el('div', 'blog-cover');
      if (p.cover) {
        var img = el('img');
        img.src = abs(p.cover);
        img.alt = p.title || '';
        img.loading = 'lazy';
        cover.appendChild(img);
      }
      card.appendChild(cover);

      var body = el('div', 'blog-body');
      if (p.date) body.appendChild(el('div', 'blog-date', fmtDate(p.date)));
      body.appendChild(el('h3', null, p.title || 'Без названия'));
      if (p.excerpt) body.appendChild(el('p', null, p.excerpt));
      body.appendChild(el('span', 'blog-link', 'Читать →'));
      card.appendChild(body);

      container.appendChild(card);
    });
    console.log('JNN Blog: отрисовано статей — ' + posts.length);
  }

  function renderDetail(container, post) {
    if (!post) {
      container.innerHTML = '<p class="blog-empty">Статья не найдена.</p>';
      return;
    }
    var html = '';
    if (post.date) html += '<div class="blog-date" style="color:var(--accent);font-weight:700;font-size:12px;letter-spacing:.06em;text-transform:uppercase;margin-bottom:12px;">' + esc(fmtDate(post.date)) + '</div>';
    html += '<h1 style="font-size:clamp(28px,4vw,44px);font-weight:800;letter-spacing:-.025em;line-height:1.15;margin:0 0 20px;">' + esc(post.title) + '</h1>';
    if (post.cover) html += '<img src="' + esc(abs(post.cover)) + '" alt="' + esc(post.title) + '" style="width:100%;border-radius:16px;margin-bottom:24px;display:block;">';
    html += '<div class="blog-content" style="font-size:16.5px;line-height:1.75;color:var(--ink);">' + (post.body || esc(post.excerpt || '')) + '</div>';
    container.innerHTML = html;
    if (post.title) document.title = post.title + ' | JNN Factory';
    console.log('JNN Blog: статья загружена — ' + post.slug);
  }

  // Список статей
  var listBox = document.querySelector('[data-jnn-blog]');
  if (listBox) {
    fetch(LIST_URL)
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (j) { renderList(listBox, j.data || []); })
      .catch(function (e) {
        console.warn('JNN Blog: список недоступен (' + e.message + ')');
        renderList(listBox, []);
      });
  }

  // Детальная статья
  var detailBox = document.querySelector('[data-jnn-blog-post]');
  if (detailBox) {
    var slug = new URLSearchParams(location.search).get('slug');
    if (!slug) {
      renderDetail(detailBox, null);
    } else {
      fetch(DETAIL_URL + encodeURIComponent(slug))
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function (j) { renderDetail(detailBox, (j.data || [])[0] || null); })
        .catch(function (e) {
          console.warn('JNN Blog: статья недоступна (' + e.message + ')');
          renderDetail(detailBox, null);
        });
    }
  }
})();
