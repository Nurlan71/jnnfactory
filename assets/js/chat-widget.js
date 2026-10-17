// JNN Factory | ИИ-технолог — плавающий виджет чата.
// Чистый JS/CSS без внешних библиотек: кнопка вызова, окно диалога, быстрые чипсы,
// сбор контакта (WhatsApp/телефон) и отправка лида на /api/chat/lead.
// Бэкенд: /api/chat (Google Gemini -> Groq -> ответ по правилам базы знаний фабрики).
(function () {
  'use strict';

  if (window.__jnnChatWidgetLoaded) return;
  window.__jnnChatWidgetLoaded = true;
  // В админке и внутри iframe виджет не нужен.
  if (window.top !== window.self) return;
  if (/^\/(admin|gallery)/.test(location.pathname)) return;

  var API = '/api/chat';
  var LEAD_API = '/api/chat/lead';
  var PHONE = '+996 700 712 212';
  var WA = 'https://wa.me/996700712212';
  var STORE_KEY = 'jnnChatHistory';
  var SESSION_KEY = 'jnnChatSession';

  var GREETING = 'Здравствуйте! Я виртуальный технолог JNN Factory. Подсказать по наличию ' +
    'готовых моделей на складе (от 50 шт) или рассчитать стоимость пошива вашей партии (от 500 шт)?';

  var CHIPS = [
    { text: 'Минимальный тираж и сроки', kind: 'ask' },
    { text: 'Шелкография и ткани', kind: 'ask' },
    { text: 'Маркировка Честный Знак и карго', kind: 'ask' },
    { text: 'Связаться с менеджером в WhatsApp', kind: 'whatsapp' }
  ];

  var JNN_WA_FALLBACK = 'Если не открылось — напишите или позвоните: ' + PHONE + '.';

  var history = loadHistory();
  var session = loadSession();
  var busy = false;
  var contactShown = false;
  var panel, list, input, sendBtn, fab, badge;

  // ------------------------------------------------------------------ storage
  function loadHistory() {
    try {
      var raw = sessionStorage.getItem(STORE_KEY);
      var data = raw ? JSON.parse(raw) : [];
      return Array.isArray(data) ? data.slice(-20) : [];
    } catch (e) { return []; }
  }

  function saveHistory() {
    try { sessionStorage.setItem(STORE_KEY, JSON.stringify(history.slice(-20))); } catch (e) { /* приватный режим */ }
  }

  function loadSession() {
    try {
      var id = sessionStorage.getItem(SESSION_KEY);
      if (!id) {
        id = 's' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
        sessionStorage.setItem(SESSION_KEY, id);
      }
      return id;
    } catch (e) { return 's' + Math.random().toString(36).slice(2, 10); }
  }

  // ------------------------------------------------------------------- helpers
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function waLink(label, cls) {
    var a = el('a', cls || 'jnnc-wa', label);
    a.href = WA;
    a.target = '_blank';
    a.rel = 'noopener';
    return a;
  }

  // ------------------------------------------------------------------- разметка
  function injectStyles() {
    if (document.getElementById('jnnc-styles')) return;
    var css = [
      '.jnnc-root{--jnnc-accent:#ff7a1a;--jnnc-accent-dark:#e2640b;--jnnc-ink:#16181d;--jnnc-muted:#6b7280;',
      '--jnnc-line:#e7e9ee;--jnnc-bg:#ffffff;--jnnc-bot:#f4f5f8;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;',
      'position:fixed;right:18px;bottom:18px;z-index:2147483000;box-sizing:border-box;}',
      '.jnnc-root *{box-sizing:border-box;}',

      // кнопка вызова
      '.jnnc-fab{display:flex;align-items:center;gap:10px;border:0;cursor:pointer;padding:0;background:transparent;}',
      '.jnnc-fab-circle{position:relative;width:60px;height:60px;border-radius:50%;display:flex;align-items:center;justify-content:center;',
      'background:linear-gradient(145deg,#ff8a2b,#f2640c);box-shadow:0 10px 26px rgba(242,100,12,.42);transition:transform .18s ease,box-shadow .18s ease;}',
      '.jnnc-fab:hover .jnnc-fab-circle{transform:translateY(-2px) scale(1.03);box-shadow:0 14px 30px rgba(242,100,12,.5);}',
      '.jnnc-fab-circle svg{width:28px;height:28px;fill:#fff;}',
      '.jnnc-fab-badge{position:absolute;right:-4px;top:-4px;display:flex;align-items:center;gap:4px;',
      'background:#12b76a;color:#fff;font-size:10px;font-weight:700;letter-spacing:.2px;padding:3px 7px;border-radius:11px;',
      'border:2px solid #fff;white-space:nowrap;}',
      '.jnnc-fab-badge i{width:6px;height:6px;border-radius:50%;background:#fff;display:block;}',
      '.jnnc-fab-label{display:none;}',

      // окно
      '.jnnc-panel{position:fixed;right:18px;bottom:18px;width:372px;max-width:calc(100vw - 24px);height:min(620px,calc(100vh - 36px));',
      'display:none;flex-direction:column;background:var(--jnnc-bg);border-radius:16px;overflow:hidden;',
      'box-shadow:0 24px 60px rgba(15,23,42,.28);border:1px solid rgba(15,23,42,.06);}',
      '.jnnc-root.jnnc-open .jnnc-panel{display:flex;}',
      '.jnnc-root.jnnc-open .jnnc-fab{display:none;}',

      '.jnnc-head{background:linear-gradient(135deg,#ff8a2b,#f2640c);color:#fff;padding:12px 14px;display:flex;align-items:center;gap:10px;}',
      '.jnnc-head-ava{width:38px;height:38px;border-radius:50%;background:rgba(255,255,255,.2);display:flex;align-items:center;justify-content:center;flex:0 0 auto;}',
      '.jnnc-head-ava svg{width:20px;height:20px;fill:#fff;}',
      '.jnnc-head-txt{flex:1 1 auto;min-width:0;}',
      '.jnnc-head-title{font-size:14px;font-weight:700;line-height:1.25;}',
      '.jnnc-head-sub{font-size:11.5px;opacity:.92;line-height:1.3;margin-top:2px;}',
      '.jnnc-close{border:0;background:rgba(255,255,255,.16);color:#fff;width:30px;height:30px;border-radius:9px;cursor:pointer;font-size:16px;line-height:1;}',
      '.jnnc-close:hover{background:rgba(255,255,255,.28);}',

      '.jnnc-list{flex:1 1 auto;overflow-y:auto;padding:14px;background:#fbfbfd;display:flex;flex-direction:column;gap:10px;}',
      '.jnnc-msg{max-width:86%;padding:10px 12px;border-radius:13px;font-size:13.5px;line-height:1.45;white-space:pre-wrap;word-wrap:break-word;}',
      '.jnnc-bot{align-self:flex-start;background:var(--jnnc-bot);color:var(--jnnc-ink);border-bottom-left-radius:5px;}',
      '.jnnc-user{align-self:flex-end;background:var(--jnnc-accent);color:#fff;border-bottom-right-radius:5px;}',
      '.jnnc-sys{align-self:center;background:transparent;color:var(--jnnc-muted);font-size:11.5px;text-align:center;max-width:100%;}',
      '.jnnc-wa{display:inline-block;margin-top:8px;font-size:12.5px;font-weight:600;color:#0a7d43;text-decoration:none;border-bottom:1px dashed #0a7d43;}',

      '.jnnc-chips{display:flex;flex-wrap:wrap;gap:7px;padding:0 14px 12px;background:#fbfbfd;}',
      '.jnnc-chip{border:1px solid var(--jnnc-line);background:#fff;color:var(--jnnc-ink);font-size:12.5px;padding:7px 11px;border-radius:999px;cursor:pointer;transition:.15s;}',
      '.jnnc-chip:hover{border-color:var(--jnnc-accent);color:var(--jnnc-accent-dark);}',

      '.jnnc-foot{border-top:1px solid var(--jnnc-line);background:#fff;padding:10px;display:flex;gap:8px;align-items:flex-end;}',
      '.jnnc-input{flex:1 1 auto;resize:none;border:1px solid var(--jnnc-line);border-radius:11px;padding:10px 11px;font-size:13.5px;line-height:1.35;',
      'max-height:96px;min-height:42px;font-family:inherit;color:var(--jnnc-ink);outline:none;background:#fff;}',
      '.jnnc-input:focus{border-color:var(--jnnc-accent);}',
      '.jnnc-send{flex:0 0 auto;width:42px;height:42px;border-radius:11px;border:0;cursor:pointer;background:var(--jnnc-accent);display:flex;align-items:center;justify-content:center;}',
      '.jnnc-send:hover{background:var(--jnnc-accent-dark);}',
      '.jnnc-send:disabled{opacity:.5;cursor:default;}',
      '.jnnc-send svg{width:19px;height:19px;fill:#fff;}',
      '.jnnc-note{font-size:10.5px;color:var(--jnnc-muted);padding:0 12px 8px;background:#fff;text-align:center;}',

      '.jnnc-form{background:#fff;border:1px solid var(--jnnc-line);border-radius:12px;padding:11px;display:flex;flex-direction:column;gap:7px;max-width:100%;}',
      '.jnnc-form-title{font-size:12.5px;font-weight:700;color:var(--jnnc-ink);}',
      '.jnnc-form input{border:1px solid var(--jnnc-line);border-radius:9px;padding:9px 10px;font-size:13px;font-family:inherit;outline:none;color:var(--jnnc-ink);}',
      '.jnnc-form input:focus{border-color:var(--jnnc-accent);}',
      '.jnnc-form button{border:0;border-radius:9px;background:var(--jnnc-accent);color:#fff;font-size:13px;font-weight:600;padding:10px;cursor:pointer;font-family:inherit;}',
      '.jnnc-form button:hover{background:var(--jnnc-accent-dark);}',
      '.jnnc-hint{font-size:10.5px;color:var(--jnnc-muted);}',

      '.jnnc-typing{align-self:flex-start;background:var(--jnnc-bot);border-radius:13px;padding:11px 13px;display:flex;gap:4px;}',
      '.jnnc-typing i{width:6px;height:6px;border-radius:50%;background:#a6adbb;display:block;animation:jnnc-blink 1.1s infinite;}',
      '.jnnc-typing i:nth-child(2){animation-delay:.18s;}',
      '.jnnc-typing i:nth-child(3){animation-delay:.36s;}',
      '@keyframes jnnc-blink{0%,60%,100%{opacity:.35;transform:translateY(0);}30%{opacity:1;transform:translateY(-2px);}}',

      '@media (max-width:520px){',
      '.jnnc-root{right:12px;bottom:12px;}',
      '.jnnc-panel{right:0;bottom:0;left:0;top:0;width:100%;height:100%;height:100dvh;max-width:none;border-radius:0;}',
      '.jnnc-foot{padding-bottom:calc(10px + env(safe-area-inset-bottom));}',
      '.jnnc-msg{max-width:92%;font-size:14px;}',
      '}',
      '@media (prefers-reduced-motion:reduce){.jnnc-fab-circle,.jnnc-typing i{transition:none;animation:none;}}'
    ].join('\n');

    var style = el('style');
    style.id = 'jnnc-styles';
    style.appendChild(document.createTextNode(css));
    document.head.appendChild(style);
  }

  function icon(id) {
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', svgPaths[id].viewBox);
    svg.setAttribute('aria-hidden', 'true');
    var path = document.createElementNS(ns, 'path');
    path.setAttribute('d', svgPaths[id].d);
    svg.appendChild(path);
    return svg;
  }

  var svgPaths = {
    chat: { viewBox: '0 0 24 24', d: 'M12 3C6.9 3 2.8 6.6 2.8 11c0 2.6 1.4 4.9 3.7 6.4-.2 1-.8 2.3-1.6 3.1-.2.2 0 .5.2.5 1.9-.1 3.6-.9 4.7-1.7 1.1.3 2.3.4 3.5.4 5.1 0 9.2-3.6 9.2-8S17.1 3 12 3z' },
    close: { viewBox: '0 0 24 24', d: 'M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7 4.3 4.3l6.3 6.3 6.3-6.3z' },
    send: { viewBox: '0 0 24 24', d: 'M3 20.5 21 12 3 3.5l0 6.6 12 1.9-12 1.9z' },
    bot: { viewBox: '0 0 24 24', d: 'M12 2a1.6 1.6 0 0 1 1.6 1.6v1.1c2.3.5 4 2.4 4 4.7v3.2l1.6 2.6c.4.7-.1 1.5-.9 1.5H6.7c-.8 0-1.3-.8-.9-1.5l1.6-2.6v-3.2c0-2.3 1.7-4.2 4-4.7V3.6A1.6 1.6 0 0 1 12 2zM9.4 18h5.2v1.1A2.6 2.6 0 0 1 12 21.7a2.6 2.6 0 0 1-2.6-2.6V18z' }
  };

  function build() {
    injectStyles();

    var root = el('div', 'jnnc-root');
    root.id = 'jnnc-root';

    // кнопка вызова
    fab = el('button', 'jnnc-fab');
    fab.type = 'button';
    fab.setAttribute('aria-label', 'Открыть чат с ИИ-технологом JNN Factory');
    var circle = el('span', 'jnnc-fab-circle');
    circle.appendChild(icon('chat'));
    badge = el('span', 'jnnc-fab-badge');
    badge.appendChild(el('i'));
    badge.appendChild(document.createTextNode('Онлайн'));
    circle.appendChild(badge);
    fab.appendChild(circle);
    fab.addEventListener('click', function () { toggle(true); });

    // окно
    panel = el('section', 'jnnc-panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'Чат с ИИ-технологом JNN Factory');
    panel.setAttribute('aria-modal', 'false');

    var head = el('header', 'jnnc-head');
    var ava = el('span', 'jnnc-head-ava');
    ava.appendChild(icon('bot'));
    head.appendChild(ava);
    var headTxt = el('div', 'jnnc-head-txt');
    headTxt.appendChild(el('div', 'jnnc-head-title', 'JNN Factory | ИИ-технолог'));
    headTxt.appendChild(el('div', 'jnnc-head-sub', 'Ответит по тканям, ценам и рассчитает партию'));
    head.appendChild(headTxt);
    var close = el('button', 'jnnc-close');
    close.type = 'button';
    close.setAttribute('aria-label', 'Закрыть чат');
    close.appendChild(icon('close'));
    close.addEventListener('click', function () { toggle(false); });
    head.appendChild(close);

    list = el('div', 'jnnc-list');
    list.setAttribute('aria-live', 'polite');
    list.setAttribute('role', 'log');

    var chips = el('div', 'jnnc-chips');
    CHIPS.forEach(function (chip) {
      var b = el('button', 'jnnc-chip', chip.text);
      b.type = 'button';
      b.addEventListener('click', function () {
        if (chip.kind === 'whatsapp') {
          window.open(WA, '_blank', 'noopener');
          addMessage('bot', 'Открываю WhatsApp. ' + JNN_WA_FALLBACK);
          return;
        }
        sendChip(chip.text);
      });
      chips.appendChild(b);
    });

    var foot = el('footer', 'jnnc-foot');
    input = el('textarea', 'jnnc-input');
    input.rows = 1;
    input.setAttribute('placeholder', 'Ваш вопрос: тираж, ткань, цена…');
    input.setAttribute('aria-label', 'Ваше сообщение');
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendFromInput(); }
    });
    input.addEventListener('input', function () {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 96) + 'px';
    });
    sendBtn = el('button', 'jnnc-send');
    sendBtn.type = 'button';
    sendBtn.setAttribute('aria-label', 'Отправить сообщение');
    sendBtn.appendChild(icon('send'));
    sendBtn.addEventListener('click', sendFromInput);
    foot.appendChild(input);
    foot.appendChild(sendBtn);

    var note = el('div', 'jnnc-note', 'Отвечает ИИ-технолог по данным фабрики. Точный расчёт — у менеджера.');

    panel.appendChild(head);
    panel.appendChild(list);
    panel.appendChild(chips);
    panel.appendChild(foot);
    panel.appendChild(note);

    root.appendChild(fab);
    root.appendChild(panel);
    document.body.appendChild(root);

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && root.classList.contains('jnnc-open')) { toggle(false); fab.focus(); }
    });

    renderHistory();
  }

  function toggle(open) {
    var root = document.getElementById('jnnc-root');
    if (!root) return;
    root.classList.toggle('jnnc-open', open);
    if (open) {
      fab.setAttribute('aria-expanded', 'true');
      if (!list.children.length) addMessage('bot', GREETING);
      setTimeout(function () { input.focus(); }, 60);
    } else {
      fab.setAttribute('aria-expanded', 'false');
    }
  }

  function renderHistory() {
    history.forEach(function (m) { addMessage(m.role === 'user' ? 'user' : 'bot', m.content, true); });
    if (!history.length && document.getElementById('jnnc-root').classList.contains('jnnc-open')) {
      addMessage('bot', GREETING);
    }
  }

  function addMessage(role, text, skipStore) {
    var cls = role === 'user' ? 'jnnc-user' : (role === 'sys' ? 'jnnc-sys' : 'jnnc-bot');
    var node = el('div', 'jnnc-msg ' + cls, text);
    // Предлагаем WhatsApp, если в ответе есть телефон.
    if (role !== 'user' && /7\s*0\s*0\s*7\s*1\s*2\s*2\s*1\s*2|\+996\s*700/.test(text)) {
      node.appendChild(waLink('Написать в WhatsApp'));
    }
    list.appendChild(node);
    list.scrollTop = list.scrollHeight;
    if (!skipStore && role !== 'sys') {
      history.push({ role: role === 'user' ? 'user' : 'assistant', content: text });
      saveHistory();
    }
    return node;
  }

  function typing(on) {
    var existing = document.getElementById('jnnc-typing');
    if (on && !existing) {
      var t = el('div', 'jnnc-typing');
      t.id = 'jnnc-typing';
      t.appendChild(el('i')); t.appendChild(el('i')); t.appendChild(el('i'));
      list.appendChild(t);
      list.scrollTop = list.scrollHeight;
    } else if (!on && existing) {
      existing.parentNode.removeChild(existing);
    }
  }

  function sendFromInput() {
    var text = (input.value || '').trim();
    if (!text || busy) return;
    input.value = '';
    input.style.height = 'auto';
    send(text);
  }

  function sendChip(text) {
    if (busy) return;
    send(text);
  }

  function send(text) {
    busy = true;
    sendBtn.disabled = true;
    // Контекст берём до добавления текущей реплики — иначе она продублируется на бэкенде.
    var context = history.slice(-10);
    addMessage('user', text);
    typing(true);

    var payload = {
      message: text,
      session: session,
      page: location.pathname,
      history: context
    };

    fetch(API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        typing(false);
        var reply = (data && data.reply) || '';
        if (!reply) throw new Error('пустой ответ');
        addMessage('bot', reply);
        if (data.ask_contact && !contactShown) showContactForm();
      })
      .catch(function () {
        typing(false);
        addMessage('bot', 'Не получилось отправить сообщение. Напишите напрямую в WhatsApp — ' + PHONE + '.');
      })
      .then(function () {
        busy = false;
        sendBtn.disabled = false;
      });
  }

  function showContactForm() {
    contactShown = true;
    var box = el('div', 'jnnc-form');
    box.appendChild(el('div', 'jnnc-form-title', 'Куда прислать расчёт?'));

    var tel = el('input');
    tel.type = 'tel';
    tel.placeholder = 'WhatsApp или телефон: +996 ...';
    tel.setAttribute('aria-label', 'Ваш WhatsApp или телефон');
    tel.autocomplete = 'tel';

    var name = el('input');
    name.type = 'text';
    name.placeholder = 'Имя (необязательно)';
    name.setAttribute('aria-label', 'Ваше имя');

    var submit = el('button', null, 'Отправить контакт');
    submit.type = 'button';
    submit.addEventListener('click', function () {
      var value = (tel.value || '').trim();
      if (value.replace(/\D/g, '').length < 6) {
        tel.focus();
        tel.style.borderColor = '#e11d48';
        return;
      }
      submit.disabled = true;
      submit.textContent = 'Отправляю…';
      fetch(LEAD_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact: value,
          name: (name.value || '').trim(),
          session: session,
          page: location.pathname,
          history: history.slice(-10)
        })
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data && data.ok) {
            box.parentNode.removeChild(box);
            var done = addMessage('bot', 'Спасибо! Передал контакт менеджеру — напишем в рабочее время (пн–пт, 09:00–18:00, GMT+6). Срочно — WhatsApp ' + PHONE + '.');
            done.scrollIntoView({ block: 'nearest' });
          } else {
            throw new Error('не сохранилось');
          }
        })
        .catch(function () {
          submit.disabled = false;
          submit.textContent = 'Отправить контакт';
          addMessage('bot', 'Не получилось сохранить контакт. Напишите, пожалуйста, в WhatsApp: ' + PHONE + '.');
        });
    });

    box.appendChild(tel);
    box.appendChild(name);
    box.appendChild(submit);
    box.appendChild(el('div', 'jnnc-hint', 'Отправляя контакт, вы соглашаетесь на обработку данных для расчёта заказа.'));
    list.appendChild(box);
    list.scrollTop = list.scrollHeight;
    setTimeout(function () { tel.focus(); }, 80);
  }

  function init() {
    if (!document.body) { document.addEventListener('DOMContentLoaded', init); return; }
    build();
  }

  init();
})();
