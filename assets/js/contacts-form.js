// JNN Contact form v1 — отправка формы со страницы «Контакты» в бэкенд сайта.
// Было: <form action="/contacts" method="POST"> — nginx отдаёт статику и отвечает 405,
// заявка никуда не уходила. Стало: POST /api/chat/lead (тот же приёмник, что у чата):
// лид пишется в лог и уходит уведомлением в Telegram.
// Поля payload совпадают с chat-widget.js: contact / name / comment / session / page / history.
// Если JS отключён — работает fallback из атрибута action у формы (WhatsApp).
(function () {
  'use strict';

  var LEAD_API = '/api/chat/lead';
  var SESSION_KEY = 'jnnChatSession';
  var RED = '#e11d48';

  // Тот же идентификатор сессии, что и в чате: заявка с формы и диалог связываются.
  function getSession() {
    try {
      var id = sessionStorage.getItem(SESSION_KEY);
      if (!id) {
        id = 'web-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
        sessionStorage.setItem(SESSION_KEY, id);
      }
      return id;
    } catch (e) {
      return '';
    }
  }

  function init() {
    var form = document.getElementById('jnnContactForm');
    if (!form) return;

    var status = document.getElementById('jnnFormStatus');
    var button = form.querySelector('button[type=submit]');
    var label = button ? button.textContent : '';

    function setStatus(text, kind, link) {
      if (!status) return;
      status.className = kind ? 'form-status form-status-' + kind : 'form-status';
      status.textContent = text || '';
      if (link) {
        status.appendChild(document.createTextNode(' '));
        var a = document.createElement('a');
        a.href = link.href;
        a.textContent = link.text;
        a.target = '_blank';
        a.rel = 'noopener';
        status.appendChild(a);
      }
    }

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();

      var nameInput = form.querySelector('[name=name]');
      var phoneInput = form.querySelector('[name=phone]');
      var messageInput = form.querySelector('[name=message]');
      var phone = (phoneInput && phoneInput.value ? phoneInput.value : '').trim();

      // Проверяем контакт так же, как бэкенд: минимум 6 цифр.
      if (phone.replace(/\D/g, '').length < 6) {
        phoneInput.style.borderColor = RED;
        phoneInput.focus();
        setStatus('Проверьте телефон или WhatsApp: нужно минимум 6 цифр.', 'error');
        return;
      }
      phoneInput.style.borderColor = '';

      var payload = {
        contact: phone,
        name: (nameInput && nameInput.value ? nameInput.value : '').trim(),
        comment: (messageInput && messageInput.value ? messageInput.value : '').trim(),
        session: getSession(),
        page: location.pathname,
        history: []
      };

      if (button) {
        button.disabled = true;
        button.textContent = 'Отправляю…';
      }
      setStatus('Отправляем…');

      fetch(LEAD_API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data || !data.ok) throw new Error('не сохранилось');
          form.reset();
          if (button) {
            button.textContent = 'Заявка отправлена';
            button.disabled = true;
          }
          setStatus('Заявка отправлена. Напишем в рабочее время: пн–пт, 09:00–18:00 (UTC+6). Срочно — WhatsApp', 'ok', {
            href: 'https://wa.me/996700712212',
            text: '+996 700 712 212'
          });
        })
        .catch(function () {
          if (button) {
            button.disabled = false;
            button.textContent = label;
          }
          setStatus('Не получилось отправить. Напишите, пожалуйста, в WhatsApp или Telegram', 'error', {
            href: 'https://wa.me/996700712212',
            text: 'WhatsApp'
          });
        });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
