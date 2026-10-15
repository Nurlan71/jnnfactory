// JNN Site Content Sync v3 — обновление шапки/футера/блоков из Directus
// Источники: /api/items/site_settings и /api/items/pages_content
// Fallback: при недоступности API статическая вёрстка остаётся нетронутой
(function () {
  'use strict';

  var SETTINGS_URL = '/api/items/site_settings?fields=*&limit=1';
  var PAGES_URL = '/api/items/pages_content?fields=slug,section,content&filter[slug][_eq]=index&limit=50';

  function safeText(val) {
    if (val === null || val === undefined) return '';
    return String(val).trim();
  }

  function firstRecord(payload) {
    if (!payload || !payload.data) return null;
    if (Array.isArray(payload.data)) return payload.data[0] || null;
    return payload.data;
  }

  function setText(selector, value) {
    var v = safeText(value);
    if (!v) return;
    var els = document.querySelectorAll(selector);
    for (var i = 0; i < els.length; i++) els[i].textContent = v;
  }

  function setHTML(selector, value) {
    var v = safeText(value);
    if (!v) return;
    var els = document.querySelectorAll(selector);
    for (var i = 0; i < els.length; i++) els[i].innerHTML = v;
  }

  function setHref(selector, value) {
    var v = safeText(value);
    if (!v) return;
    var els = document.querySelectorAll(selector);
    for (var i = 0; i < els.length; i++) els[i].setAttribute('href', v);
  }

  function applySettings(d) {
    if (!d) return;

    // Телефон: все tel:-ссылки + видимый текст
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

    // WhatsApp / Telegram / Email
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

    // Футер: копирайт и юридическая строка
    setText('.f-bottom span:first-child', d.copyright);
    setText('.f-bottom span:nth-child(2)', d.legal);

    // Описание бренда в футере (HTML допускается)
    setHTML('.f-brand', d.footer_text);

    // Адрес
    setText('[data-jnn="address"]', d.address);

    console.log('JNN SiteContent: site_settings применены');
  }

  function applyPages(records) {
    if (!records || !records.length) return;
    var applied = 0;
    records.forEach(function (rec) {
      var content = rec.content;
      if (typeof content === 'string') {
        try { content = JSON.parse(content); } catch (e) { return; }
      }
      if (!content || typeof content !== 'object') return;
      Object.keys(content).forEach(function (key) {
        var el = document.querySelector('[data-jnn="' + key + '"]');
        if (el && safeText(content[key])) {
          el.innerHTML = content[key];
          applied++;
        }
      });
    });
    if (applied) console.log('JNN SiteContent: pages_content применён (' + applied + ' блоков)');
  }

  // Оба запроса независимы; ошибка одного не ломает другой
  fetch(SETTINGS_URL)
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (j) { applySettings(firstRecord(j)); })
    .catch(function (e) { console.warn('JNN SiteContent: site_settings недоступен (' + e.message + ')'); });

  fetch(PAGES_URL)
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (j) { applyPages(j.data || []); })
    .catch(function (e) { console.warn('JNN SiteContent: pages_content недоступен (' + e.message + ')'); });
})();
