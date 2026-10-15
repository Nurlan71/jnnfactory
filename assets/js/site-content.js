// JNN Site Content Sync v5 — тексты главной страницы из Directus
// Источники: /api/items/site_settings и /api/items/pages_content (slug=home)
//
// ПРИНЦИП: вёрстка и CSS не меняются. Скрипт находит существующие DOM-узлы
// по селекторам и обновляет ТОЛЬКО их текст, сохраняя вложенные элементы
// оформления (цветной «+», слоган в <b>, подпись «Контактное лицо» в <b>).
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

    setHref('a[href*="wa.me"]', d.whatsapp);
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

  // footer_about — описание бренда, слоган и реквизиты в футере
  function applyFooterAbout(c) {
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
  }

  var STRUCTURED = {
    stats: applyStats,
    benefits: applyBenefits,
    contacts_block: applyContacts,
    footer_about: applyFooterAbout
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

  // Сначала настройки, затем контент страницы (footer_about перекрывает legal).
  fetch(SETTINGS_URL)
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (j) { applySettings(firstRecord(j)); })
    .catch(function (e) { console.warn('JNN SiteContent: site_settings недоступен (' + e.message + ')'); })
    .then(function () { return fetch(PAGES_URL); })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (j) { applyPages(j.data || []); })
    .catch(function (e) { console.warn('JNN SiteContent: pages_content недоступен (' + e.message + ')'); });
})();
