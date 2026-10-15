// JNN Site Content Sync — мягкое обновление шапки/футера из Directus
// Fallback: если API недоступен или поля пустые, вёрстка остаётся нетронутой
(function () {
  'use strict';

  var API_URL = '/api/items/site_settings?fields=*';

  function safeText(val) {
    if (val === null || val === undefined) return '';
    var s = String(val).trim();
    return s.length > 0 ? s : '';
  }

  function updateText(selector, value) {
    var v = safeText(value);
    if (!v) return;
    var els = document.querySelectorAll(selector);
    for (var i = 0; i < els.length; i++) {
      els[i].textContent = v;
    }
  }

  function updatePhone(phone) {
    var p = safeText(phone);
    if (!p) return;
    var tels = document.querySelectorAll('a[href^="tel:"]');
    var cleanPhone = p.replace(/[\s\-()]/g, '');
    for (var i = 0; i < tels.length; i++) {
      tels[i].setAttribute('href', 'tel:' + cleanPhone);
      var txt = tels[i].textContent.trim();
      if (/[\+]?[0-9][\d\s\-()]{6,}/.test(txt)) {
        tels[i].textContent = p;
      }
    }
  }

  function applyData(data) {
    // site_settings — singleton, но API может вернуть массив или объект
    var d = null;
    if (data && data.data) {
      if (Array.isArray(data.data)) {
        d = data.data[0];
      } else {
        d = data.data;
      }
    }
    if (!d) return;

    // Телефон
    updatePhone(d.phone);

    // WhatsApp
    var wa = safeText(d.whatsapp);
    if (wa) {
      var waLinks = document.querySelectorAll('a[href*="wa.me"]');
      for (var i = 0; i < waLinks.length; i++) {
        waLinks[i].setAttribute('href', wa);
      }
    }

    // Telegram
    var tg = safeText(d.telegram);
    if (tg) {
      var tgLinks = document.querySelectorAll('a[href*="t.me/jnnfactory"]:not([href*="bot"])');
      for (var j = 0; j < tgLinks.length; j++) {
        tgLinks[j].setAttribute('href', tg);
      }
    }

    // Email
    var email = safeText(d.email);
    if (email) {
      var mailLinks = document.querySelectorAll('a[href^="mailto:"]');
      for (var k = 0; k < mailLinks.length; k++) {
        mailLinks[k].setAttribute('href', 'mailto:' + email);
        mailLinks[k].textContent = email;
      }
    }

    // Footer copyright
    updateText('.f-bottom span:first-child', d.copyright);

    // Footer text / brand description
    var footerText = safeText(d.footer_text);
    if (footerText) {
      var brandEl = document.querySelector('.f-brand');
      if (brandEl) {
        brandEl.innerHTML = footerText;
      }
    }

    console.log('JNN SiteContent: данные применены из Directus');
  }

  fetch(API_URL)
    .then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then(applyData)
    .catch(function (err) {
      console.warn('JNN SiteContent: API недоступен, использую статику (' + err.message + ')');
    });
})();