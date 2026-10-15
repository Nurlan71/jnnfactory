// JNN Site Content Sync v11 — тексты страниц сайта из Directus
// Источники: /api/items/site_settings, /api/items/pages_content (slug=home),
//            /api/items/pages + /api/items/page_sections (все остальные страницы)
//
// ПРИНЦИП: вёрстка и CSS не меняются. Скрипт находит существующие DOM-узлы
// по селекторам и по ключам data-jnn и обновляет ТОЛЬКО их текст, сохраняя
// вложенные элементы оформления (цветной «+», слоган в <b>, подпись в <b>).
// Fallback: если API недоступен или поле пустое — на странице остаётся
// исходный текст из HTML.
(function () {
  'use strict';

  var SETTINGS_URL = '/api/items/site_settings?fields=*&limit=1';
  var PAGES_URL = '/api/items/pages_content?fields=slug,section,content&filter[slug][_eq]=home&limit=50';

  function safeText(val) {
    if (val === null || val === undefined) return '';
    return String(val).trim();
  }

  function firstRecord(payload) {
    if (!payload || !payload.data) return null;
    if (Array.isArray(payload.data)) return payload.data[0] || null;
    return payload.data;
  }

  function parseContent(c) {
    if (typeof c === 'string') { try { return JSON.parse(c); } catch (e) { return null; } }
    return (c && typeof c === 'object') ? c : null;
  }

  /* ---------- общие обновлялки ---------- */

  function setText(selector, value) {
    var v = safeText(value);
    if (!v) return;
    var els = document.querySelectorAll(selector);
    for (var i = 0; i < els.length; i++) els[i].textContent = v;
  }

  function setElText(el, value) {
    var v = safeText(value);
    if (!el || !v) return;
    el.textContent = v;
  }

  function setHref(selector, value) {
    var v = safeText(value);
    if (!v) return;
    var els = document.querySelectorAll(selector);
    for (var i = 0; i < els.length; i++) els[i].setAttribute('href', v);
  }

  /* ---------- футер и реквизиты общего вида (все страницы) ---------- */

  var SETTINGS = {};

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // Юридическая строка: © + реквизиты + адрес/почта/телефон (значения из CMS).
  function legalHTML() {
    var req = safeText(SETTINGS.requisites);
    var inn = (req.match(/\d{10,}/) || [])[1] || '';
    var company = (req.split(/[-–·]/)[0] || '').trim() || 'ОсОО «Айдана Стайл»';
    var parts = [];
    if (SETTINGS.copyright) parts.push(esc(SETTINGS.copyright));
    parts.push(esc(company));
    if (inn) parts.push('ИНН: ' + inn);
    if (SETTINGS.address) parts.push('Адрес: ' + esc(SETTINGS.address));
    if (SETTINGS.email) parts.push('Email: ' + esc(SETTINGS.email));
    if (SETTINGS.phone) parts.push('Тел: ' + esc(SETTINGS.phone));
    return parts.join('<br/>');
  }

  // Tilda-страницы: весь юр.блок лежит одной строкой с <br>. Пересобираем его из CMS.
  function rebuildLegalBlocks() {
    var els = document.querySelectorAll('footer div, footer p, footer span, footer address');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (el.querySelector('div, p, ul, li')) continue;
      var t = el.textContent;
      if (/©/.test(t) && /(Айдана|ИНН)/.test(t)) el.innerHTML = legalHTML();
    }
  }

  // Простые страницы: <footer class="footer"><p>© ...</p><p>реквизиты/контакты</p>
  function applySimpleFooter(c) {
    var ps = document.querySelectorAll('footer p');
    if (!ps.length) return;
    var req = safeText(c && c.requisites) || safeText(SETTINGS.requisites);
    var line2 = [req, safeText(SETTINGS.email), safeText(SETTINGS.phone)].filter(Boolean).join(' · ');
    for (var i = 0; i < ps.length; i++) {
      var t = ps[i].textContent;
      if (/©/.test(t) && safeText(SETTINGS.copyright)) {
        // Копирайт и реквизиты в одной строке — пересобираем полный юр.блок.
        if (/(Айдана|ИНН)/.test(t)) ps[i].innerHTML = legalHTML();
        else ps[i].textContent = safeText(SETTINGS.copyright);
      } else if (/(Айдана|ИНН\s*0|jnnwear)/.test(t) && line2) {
        ps[i].textContent = line2;
      }
    }
  }

  /* ---------- помощники, сохраняющие вложенную разметку ---------- */

  // Обновляет первый текстовый узел контейнера, НЕ удаляя дочерние элементы
  // (нужно для .f-brand, где после текста идёт <b>со слоганом</b>).
  function setLeadText(el, value, trailSpace) {
    if (!el) return;
    var v = safeText(value);
    if (!v) return;
    if (trailSpace) v += ' ';
    var target = null;
    for (var i = 0; i < el.childNodes.length; i++) {
      var n = el.childNodes[i];
      if (n.nodeType === 3 && n.nodeValue.trim()) { target = n; break; }
    }
    if (target) target.nodeValue = v;
    else el.insertBefore(document.createTextNode(v), el.firstChild);
  }

  // Обновляет текст ПОСЛЕ <b> (напр. имя менеджера), сохраняя подпись <b>.
  function setTextAfterBold(el, value) {
    if (!el) return;
    var v = safeText(value);
    if (!v) return;
    var b = el.querySelector('b');
    if (!b) { el.appendChild(document.createTextNode(v)); return; }
    var n = b.nextSibling;
    if (n && n.nodeType === 3) n.nodeValue = v;
    else el.insertBefore(document.createTextNode(v), b.nextSibling);
  }

  // Обновляет число, СОХРАНЯЯ цветной символ внутри <span> (напр. «12<span>+</span>»).
  function setAccentNum(card, value) {
    var num = card && card.querySelector('.num');
    var v = safeText(value);
    if (!num || !v) return;
    var span = num.querySelector('span');
    if (span) {
      var sym = span.textContent.trim();
      if (sym && v.slice(-sym.length) === sym) {
        var lead = v.slice(0, v.length - sym.length);
        var prev = span.previousSibling;
        if (prev && prev.nodeType === 3) prev.nodeValue = lead;
        else num.insertBefore(document.createTextNode(lead), span);
        return;
      }
    }
    num.textContent = v;
  }

  /* ---------- site_settings (телефоны, почта, копирайт) ---------- */

  function applySettings(d) {
    if (!d) return;
    SETTINGS = d;

    var p = safeText(d.phone);
    if (p) {
      var clean = p.replace(/[\s\-()]/g, '');
      var tels = document.querySelectorAll('a[href^="tel:"]');
      for (var i = 0; i < tels.length; i++) {
        tels[i].setAttribute('href', 'tel:' + clean);
        if (/[\+]?[0-9][\d\s\-()]{6,}/.test(tels[i].textContent.trim())) {
          tels[i].textContent = p;
        }
      }
    }

    // WhatsApp: номер берём из CMS, но готовый текст сообщения (?text=) сохраняем.
    var waBase = safeText(d.whatsapp).replace(/[?&]text=.*$/, '');
    if (waBase) {
      var was = document.querySelectorAll('a[href*="wa.me"]');
      for (var w = 0; w < was.length; w++) {
        var wh = was[w].getAttribute('href') || '';
        var wt = wh.match(/[?&]text=([^&]*)/);
        was[w].setAttribute('href', wt ? waBase + '?text=' + wt[1] : waBase);
      }
    }
    setHref('a[href*="t.me/jnnfactory"]:not([href*="bot"])', d.telegram);

    var email = safeText(d.email);
    if (email) {
      var mails = document.querySelectorAll('a[href^="mailto:"]');
      for (var k = 0; k < mails.length; k++) {
        mails[k].setAttribute('href', 'mailto:' + email);
        mails[k].textContent = email;
      }
    }

    // Футер: копирайт и юридическая строка (footer_about из pages_content
    // применяется позже и при наличии перекрывает «requisites»)
    setText('.f-bottom span:first-child', d.copyright);
    setText('.f-bottom span:nth-child(2)', d.legal);

    setText('[data-jnn="address"]', d.address);
    setText('[data-jnn="phone"]', d.phone);
    setText('[data-jnn="email"]', d.email);

    // Простые footers (на всех страницах): копирайт сразу из настроек.
    // Строки, где © и реквизиты в одном абзаце, оставляем для полной пересборки
    // в applyFooterAbout (чтобы не потерять реквизиты).
    var fps = document.querySelectorAll('footer p');
    for (var q = 0; q < fps.length; q++) {
      var ft = fps[q].textContent;
      if (/©/.test(ft) && !/(Айдана|ИНН|jnnwear)/.test(ft) && safeText(d.copyright)) fps[q].textContent = safeText(d.copyright);
    }

    console.log('JNN SiteContent: site_settings применены');
  }

  /* ---------- блоки главной страницы (pages_content) ---------- */

  // stats — блок цифр (#numbers)
  function applyStats(c) {
    var cards = document.querySelectorAll('#numbers .num-card');
    if (!cards.length) return;
    function num(i) { return cards[i] ? cards[i].querySelector('.num') : null; }
    function lbl(i) { return cards[i] ? cards[i].querySelector('.lbl') : null; }
    setAccentNum(cards[0], c.year_val);   setElText(lbl(0), c.year_label);
    setAccentNum(cards[1], c.models_val); setElText(lbl(1), c.models_label);
    setElText(num(2), c.batch_title);
    setAccentNum(cards[3], c.colors_val); setElText(lbl(3), c.colors_label);
  }

  // benefits — «Почему бренды выбирают JNN Factory» (#why)
  function applyBenefits(c) {
    setText('#why .sec-head h2', c.title);
    var items = c.items;
    if (!Array.isArray(items)) return;
    var cards = document.querySelectorAll('#why .why-grid .why-item');
    for (var i = 0; i < cards.length && i < items.length; i++) {
      var it = items[i] || {};
      setElText(cards[i].querySelector('h3'), it.title);
      setElText(cards[i].querySelector('p'), it.desc);
    }
  }

  // contacts_block — блок контактов (#contact)
  function applyContacts(c) {
    setText('#contact .contact-info h2', c.title);
    setText('#contact .contact-info > p', c.subtitle);
    if (safeText(c.manager_name)) {
      var li = document.querySelector('#contact .c-list li:nth-child(4)');
      var box = li ? li.querySelector('div:not(.ico)') : null;
      setTextAfterBold(box, c.manager_name);
    }
  }

  // footer_about — описание бренда, слоган и реквизиты в футере (на всех страницах)
  function applyFooterAbout(c) {
    if (safeText(c.requisites)) SETTINGS.requisites = c.requisites;

    var brand = document.querySelector('footer .f-brand') || document.querySelector('.f-brand');
    if (brand) {
      if (c.text) setLeadText(brand, c.text, true);
      if (safeText(c.motto)) {
        var b = brand.querySelector('b');
        if (b) b.textContent = safeText(c.motto);
        else { b = document.createElement('b'); b.textContent = safeText(c.motto); brand.appendChild(b); }
      }
    }
    setText('.f-bottom span:nth-child(2)', c.requisites);

    // Общий футер: простые страницы + Tilda-страницы
    applySimpleFooter(c);
    rebuildLegalBlocks();
  }

  // faq — аккордеон вопросов и ответов (#faq), раздел pages_content: faq
  function applyFaq(c) {
    setText('#faq .sec-eyebrow', c.eyebrow);
    setText('#faq .sec-head h2', c.title);
    setText('#faq .sec-head p', c.subtitle);
    var items = c.items;
    if (Array.isArray(items)) {
      var nodes = document.querySelectorAll('#faq .faq-item');
      for (var i = 0; i < nodes.length && i < items.length; i++) {
        var it = items[i] || {};
        setElText(nodes[i].querySelector('summary span'), it.q);
        var ans = nodes[i].querySelector('.faq-a');
        if (ans && safeText(it.a)) ans.innerHTML = String(it.a);
      }
    }
    syncFaqSchema();
  }

  // JSON-LD FAQPage всегда соответствует видимому тексту аккордеона:
  // статичная разметка страницы обновляется после подстановки данных из CMS.
  // Работает для ЛЮБОГО блока [data-jnn-faq] на странице (главная, услуги,
  // товары, лендинги): целевой <script> задаётся атрибутом data-faq-schema
  // (по умолчанию — #faq-schema, как на главной).
  function faqSchemaId() {
    var p = normPath(window.location.pathname).replace(/\/index$/, '/');
    if (p === '' || p === '/index') p = '/';
    var origin = 'https://jnnfactory.online';
    try {
      if (window.location.origin && /^https?:/.test(window.location.origin)) origin = window.location.origin;
    } catch (e) {}
    return origin + p + '#faq';
  }

  function syncFaqSchema() {
    var lists = document.querySelectorAll('[data-jnn-faq]');
    for (var k = 0; k < lists.length; k++) {
      var nodes = lists[k].querySelectorAll('.faq-item');
      if (!nodes.length) continue;
      var qa = [];
      for (var i = 0; i < nodes.length; i++) {
        var qEl = nodes[i].querySelector('summary span') || nodes[i].querySelector('summary') || nodes[i].querySelector('h3');
        var aEl = nodes[i].querySelector('.faq-a') || nodes[i].querySelector('p');
        var q = qEl ? safeText(qEl.textContent).replace(/\s+/g, ' ') : '';
        var a = aEl ? safeText(aEl.textContent).replace(/\s+/g, ' ') : '';
        if (q && a) qa.push({ '@type': 'Question', 'name': q, 'acceptedAnswer': { '@type': 'Answer', 'text': a } });
      }
      if (!qa.length) continue;
      var id = lists[k].getAttribute('data-faq-schema') || 'faq-schema';
      var el = document.getElementById(id);
      if (!el) {
        el = document.createElement('script');
        el.type = 'application/ld+json';
        el.id = id;
        document.head.appendChild(el);
      }
      el.textContent = JSON.stringify({
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        '@id': faqSchemaId(),
        'mainEntity': qa
      }, null, 2);
    }
  }

  var STRUCTURED = {
    stats: applyStats,
    benefits: applyBenefits,
    contacts_block: applyContacts,
    footer_about: applyFooterAbout,
    faq: applyFaq
  };

  function applyPages(records) {
    if (!records || !records.length) return;
    var applied = 0;
    records.forEach(function (rec) {
      var c = parseContent(rec.content);
      if (!c) return;
      var handler = STRUCTURED[rec.section];
      if (handler) { handler(c); applied++; return; }
      // Прочие разделы (hero, offers, catalog, steps, print, blog) — по data-jnn
      Object.keys(c).forEach(function (key) {
        var el = document.querySelector('[data-jnn="' + key + '"]');
        if (el && safeText(c[key])) { el.innerHTML = c[key]; applied++; }
      });
    });
    if (applied) console.log('JNN SiteContent: pages_content применён (' + applied + ' блоков)');
  }

  /* ---------- страницы сайта: pages + page_sections ---------- */

  // Текущий путь приводим к тому виду, в котором он хранится в CMS:
  //   /about.html → /about,  /blog/ → /blog/index,  / → /
  function normPath(p) {
    p = String(p || '/').split('?')[0].split('#')[0];
    try { p = decodeURIComponent(p); } catch (e) {}
    if (p.length > 1 && p.charAt(p.length - 1) === '/') p += 'index';
    p = p.replace(/\.html$/, '');
    if (p === '' || p === '/index') p = '/';
    return p;
  }

  function looksLikeHtml(v) { return /<[a-z!/][\s\S]*?>/i.test(v); }

  // Подставляет значение в ВСЕ узлы с этим ключом (h1 бывает и в шапке, и в тексте).
  function applyRich(key, value) {
    var v = safeText(value);
    if (!v) return 0;
    var els = document.querySelectorAll('[data-jnn="' + key + '"]');
    if (!els.length) return 0;
    var html = looksLikeHtml(v);
    for (var i = 0; i < els.length; i++) {
      if (html) els[i].innerHTML = v;
      else els[i].textContent = v;
    }
    return els.length;
  }

  function setMeta(selector, value) {
    var v = safeText(value);
    if (!v) return;
    var el = document.querySelector(selector);
    if (el) el.setAttribute('content', v);
  }

  function applyPage(page, sections) {
    if (!page) return;
    var n = 0;
    n += applyRich('page_h1', page.h1);
    n += applyRich('page_subtitle', page.subtitle);

    var t = safeText(page.seo_title);
    if (t) {
      document.title = t;
      setMeta('meta[property="og:title"]', t);
      setMeta('meta[name="twitter:title"]', t);
    }
    var d = safeText(page.seo_description);
    if (d) {
      setMeta('meta[name="description"]', d);
      setMeta('meta[property="og:description"]', d);
      setMeta('meta[name="twitter:description"]', d);
    }

    (sections || []).forEach(function (s) {
      if (s && s.key) n += applyRich(s.key, s.content);
    });

    if (n) console.log('JNN SiteContent: страница «' + safeText(page.title) + '» — узлов обновлено: ' + n);
  }

  function loadPage() {
    var path = normPath(window.location.pathname);
    var candidates = [path];
    if (/\/index$/.test(path)) candidates.push(path.replace(/\/index$/, ''));
    if (path === '/') candidates.push('/index');

    function attempt(i) {
      if (i >= candidates.length) return Promise.resolve();
      var url = '/api/items/pages?limit=1'
        + '&fields=id,title,slug,path,h1,subtitle,seo_title,seo_description'
        + '&filter[path][_eq]=' + encodeURIComponent(candidates[i]);
      return fetch(url)
        .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function (j) {
          var page = firstRecord(j);
          if (!page) return attempt(i + 1);
          return fetch('/api/items/page_sections?limit=300&sort=sort&fields=key,kind,content'
              + '&filter[page][_eq]=' + page.id)
            .then(function (r2) { return r2.ok ? r2.json() : { data: [] }; })
            .then(function (j2) { applyPage(page, j2.data || []); });
        });
    }

    return attempt(0).catch(function (e) {
      console.warn('JNN SiteContent: тексты страницы недоступны (' + e.message + ')');
    });
  }

  // Сначала настройки, затем контент страницы (footer_about перекрывает legal).
  fetch(SETTINGS_URL)
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (j) { applySettings(firstRecord(j)); })
    .catch(function (e) { console.warn('JNN SiteContent: site_settings недоступен (' + e.message + ')'); })
    .then(function () { return fetch(PAGES_URL); })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (j) { applyPages(j.data || []); syncFaqSchema(); })
    .catch(function (e) { console.warn('JNN SiteContent: pages_content недоступен (' + e.message + ')'); })
    .then(function () { return loadPage(); })
    .then(function () { syncFaqSchema(); });
})();
