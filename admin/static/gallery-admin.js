/* Галерея JNN: файлы сайта + медиатека Directus + виртуальные папки.
 * Папки хранятся в manifest и не меняют URL /assets/<file>, поэтому
 * существующие страницы и Git-деплой не ломаются.
 */
(function () {
  'use strict';

  var API = '/gallery-api';
  var AUTH = '/gallery-auth';
  var ADMIN_URL = 'https://admin.jnnfactory.online';
  var DEFAULT_SITE_ORIGIN = 'https://jnnfactory.online';
  var siteOrigin = DEFAULT_SITE_ORIGIN;
  var IMG_RE = /\.(jpe?g|jfif|png|webp|avif|gif|svg)$/i;
  var UPLOAD_RE = /\.(jpe?g|jfif|png|webp|avif|gif|svg)$/i;
  var ROOT = '';
  var ALL = '__all__';

  var files = [];
  var media = [];
  var folders = [];
  var productCatalog = [];
  var currentFolder = ALL;
  var mediaWritable = false;
  var foldersOk = true;
  var modalCleanup = null;
  var loadSeq = 0;
  var session = null;
  var selected = {};
  var visibleKeys = [];

  var $ = function (s) { return document.querySelector(s); };
  var grid = $('#grid');
  var empty = $('#empty');
  var count = $('#count');
  var userState = $('#userState');
  var batchBar = $('#batchBar');
  var batchFolder = $('#batchFolder');
  var selCount = $('#selCount');
  var folderBar = $('#folderBar');
  var folderPath = $('#folderPath');
  var dropTarget = $('#dropTarget');
  var productSelect = $('#productSelect');
  var productTarget = $('#productTarget');
  var productAttach = $('#productAttach');
  var productFile = $('#productFile');
  var productFileName = $('#productFileName');
  var productUploadBtn = $('#productUploadBtn');

  function toast(msg, isErr, ms) {
    var d = document.createElement('div');
    if (isErr) d.className = 'err';
    d.textContent = msg;
    $('#toast').appendChild(d);
    setTimeout(function () { d.remove(); }, ms || 4500);
  }

  function cookieValue(name) {
    var parts = document.cookie ? document.cookie.split(';') : [];
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].trim();
      if (p.indexOf(name + '=') === 0) return decodeURIComponent(p.slice(name.length + 1));
    }
    return '';
  }

  function csrfToken() { return cookieValue('jnn_gallery_csrf'); }

  function authHeaders(extra) {
    var h = {};
    if (extra) Object.keys(extra).forEach(function (k) { h[k] = extra[k]; });
    var token = csrfToken();
    if (token) h['X-CSRF-Token'] = token;
    return h;
  }

  function setUser(user) {
    session = user || null;
    if (user) {
      userState.textContent = user.name || user.email || 'администратор';
      userState.className = 'state on';
    } else {
      userState.textContent = 'не авторизован';
      userState.className = 'state';
    }
  }

  function showLogin(message) {
    var screen = $('#loginScreen');
    if (!screen) return;
    screen.hidden = false;
    if (message) $('#loginError').textContent = message;
    setUser(null);
    setTimeout(function () { var e = $('#loginEmail'); if (e) e.focus(); }, 30);
  }

  function hideLogin() {
    var screen = $('#loginScreen');
    if (screen) screen.hidden = true;
    var err = $('#loginError');
    if (err) err.textContent = '';
  }

  function apiFetch(url, options) {
    options = options || {};
    options.credentials = 'same-origin';
    var method = String(options.method || 'GET').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
      options.headers = authHeaders(options.headers || {});
    }
    return fetch(url, options).then(function (r) {
      return r.text().then(function (text) {
        var j = {};
        if (text) {
          try { j = JSON.parse(text); } catch (e) { j = { detail: text.slice(0, 300) }; }
        }
        if (r.status === 401) showLogin('Сессия истекла. Войдите заново.');
        return { status: r.status, ok: r.ok, j: j };
      });
    });
  }

  function checkSession() {
    return fetch(AUTH + '/me', { credentials: 'same-origin' }).then(function (r) {
      return r.text().then(function (text) {
        var j = {};
        if (text) { try { j = JSON.parse(text); } catch (e) { j = {}; } }
        if (!r.ok) throw new Error((j && j.detail) || 'Нужна авторизация');
        return j;
      });
    });
  }

  function login(email, password) {
    return fetch(AUTH + '/login', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, password: password })
    }).then(function (r) {
      return r.text().then(function (text) {
        var j = {};
        if (text) { try { j = JSON.parse(text); } catch (e) { j = { detail: text.slice(0, 300) }; } }
        if (!r.ok) throw new Error((j && j.detail) || 'Не удалось войти');
        return j;
      });
    });
  }

  function logout() {
    return fetch(AUTH + '/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: '{}'
    }).then(function () {
      setUser(null);
      files = []; media = []; selected = {};
      render();
      showLogin('Вы вышли из галереи.');
    });
  }

  function fmtSize(b) {
    if (b == null) return '';
    if (b < 1024) return b + ' Б';
    if (b < 1048576) return (b / 1024).toFixed(0) + ' КБ';
    return (b / 1048576).toFixed(1) + ' МБ';
  }

  function fmtDate(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    return d.toLocaleDateString('ru-RU') + ' ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  }

  function copyUrl(url) {
    var done = function () { toast('Скопировано: ' + url); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done, function () { fallback(url, done); });
    } else { fallback(url, done); }
  }

  function fallback(text, cb) {
    var ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); cb(); } catch (e) { toast('Не удалось скопировать', true); }
    ta.remove();
  }

  function usageParts(u) {
    var used = [];
    if (u && u.products && u.products.length) used.push('товары: ' + u.products.map(productTitle).join(', '));
    if (u && u.files && u.files.length) used.push('страницы: ' + u.files.slice(0, 6).join(', '));
    return used;
  }

  function usageText(u) {
    var used = usageParts(u);
    return used.length ? used.join('; ') : ((u && u.detail) || 'активная связь');
  }

  function productAdminUrl(p) {
    return p && p.id
      ? ADMIN_URL + '/admin/content/products/' + encodeURIComponent(String(p.id))
      : ADMIN_URL + '/admin/content/products';
  }

  function fileAdminUrl(id) {
    return ADMIN_URL + '/admin/files/' + encodeURIComponent(String(id));
  }

  function productTitle(p) {
    if (typeof p === 'string') return p || 'товар';
    return (p && (p.name || p.slug || p.label)) || 'товар';
  }

  function resolveProducts(j, f) {
    var known = (f && f.products) || [];
    if (!j || !Object.prototype.hasOwnProperty.call(j, 'products')) return known;
    var fresh = Array.isArray(j.products) ? j.products : [];
    return fresh.map(function (item) {
      if (item && typeof item === 'object') return item;
      var label = String(item || '');
      var hit = known.find(function (p) {
        return p && (p.label === label || p.name === label || p.slug === label);
      });
      return hit || { label: label };
    });
  }

  function appendText(body, text) {
    var p = document.createElement('p');
    p.textContent = text;
    body.appendChild(p);
    return p;
  }

  function appendProductLinks(body, products, prefix) {
    if (!products || !products.length) return;
    var label = document.createElement('p');
    label.textContent = prefix || 'Используется в товарах:';
    body.appendChild(label);
    var list = document.createElement('ul');
    list.className = 'modal-list';
    products.forEach(function (item) {
      var li = document.createElement('li');
      if (item && item.id) {
        var a = document.createElement('a');
        a.href = productAdminUrl(item);
        a.target = '_blank';
        a.rel = 'noopener';
        a.textContent = productTitle(item);
        li.appendChild(a);
      } else {
        li.textContent = productTitle(item);
      }
      if (item && item.slug) {
        var s = document.createElement('span');
        s.className = 'muted';
        s.textContent = ' · ' + item.slug;
        li.appendChild(s);
      }
      list.appendChild(li);
    });
    body.appendChild(list);
  }

  function appendDirectusLink(body, f, label) {
    var id = f && (f.source === 'directus' ? f.id : f.media_id);
    if (!id) return;
    var p = document.createElement('p');
    var a = document.createElement('a');
    a.href = fileAdminUrl(id);
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = label || 'Открыть файл в Directus';
    p.appendChild(a);
    body.appendChild(p);
  }

  function appendUsage(body, j, f) {
    var products = resolveProducts(j, f);
    if (products.length) appendProductLinks(body, products, 'Товары:');
    if (j && j.files && j.files.length) {
      appendText(body, 'Страницы: ' + j.files.slice(0, 8).join(', '));
    }
  }

  function showModal(title, build, buttons) {
    if (modalCleanup) {
      modalCleanup();
      modalCleanup = null;
    }
    var old = document.getElementById('modal');
    if (old) old.remove();
    var previousFocus = document.activeElement;
    var oldOverflow = document.body.style.overflow;
    var overlay = document.createElement('div');
    overlay.id = 'modal';
    overlay.className = 'modal';
    var box = document.createElement('div');
    box.className = 'modal-box';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-labelledby', 'modalTitle');
    var h = document.createElement('h3');
    h.id = 'modalTitle';
    h.textContent = title;
    var body = document.createElement('div');
    body.className = 'modal-body';
    build(body);

    var actions = document.createElement('div');
    actions.className = 'modal-actions';
    var defs = (buttons && buttons.length) ? buttons : [{ label: 'Закрыть', primary: true }];
    var actionNodes = [];
    defs.forEach(function (def) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'small' + (def.primary ? ' primary' : '') + (def.danger ? ' danger' : '');
      b.textContent = def.label;
      b.addEventListener('click', function () {
        if (def.close !== false) closeModal();
        if (def.onClick) def.onClick();
      });
      actions.appendChild(b);
      actionNodes.push(b);
    });

    box.appendChild(h);
    box.appendChild(body);
    box.appendChild(actions);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';

    function onKey(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeModal();
        return;
      }
      if (e.key !== 'Tab') return;
      var focusable = Array.prototype.slice.call(overlay.querySelectorAll(
        'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'
      ));
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    function closeModal() {
      document.removeEventListener('keydown', onKey);
      overlay.remove();
      document.body.style.overflow = oldOverflow;
      if (previousFocus && document.contains(previousFocus) && previousFocus.focus) {
        previousFocus.focus();
      }
      if (modalCleanup === closeModal) modalCleanup = null;
    }

    modalCleanup = closeModal;
    overlay.addEventListener('click', function (e) { if (e.target === overlay) closeModal(); });
    document.addEventListener('keydown', onKey);
    if (actionNodes.length) actionNodes[0].focus();
  }

  function showInfoModal(title, text, f) {
    showModal(title, function (body) {
      appendText(body, text);
      if (f) appendDirectusLink(body, f);
    });
  }

  function showErrorModal(title, j, f) {
    showModal(title, function (body) {
      appendText(body, (j && j.detail) || (j && j.error) || 'Операция недоступна.');
      appendUsage(body, j, f);
      if (f) appendDirectusLink(body, f);
      if (j && j.reason === 'git_unavailable') {
        appendText(body, 'Git недоступен: действие заблокировано, чтобы деплой не вернул файл.');
      }
    });
  }

  function forceComment(f, j, verb) {
    var lines = [];
    if (f && f.source === 'directus') {
      lines.push('Это файл медиатеки Directus. Действие изменит или удалит его в Directus.');
    } else if (f && f.in_media) {
      lines.push('Это локальная копия. Файл в медиатеке Directus останется.');
    }
    if (f && f.git_tracked === true) {
      lines.push('Файл отслеживается Git: будет выполнен git rm/git mv. Удаление/переименование попадёт в Git index; нужен commit, иначе деплой заблокируется.');
    } else if (f && f.git_tracked === null) {
      lines.push('Состояние Git неизвестно: принудительное действие недоступно.');
    }
    if (f && f.symlink) {
      lines.push('Это символическая ссылка: действие затронет только саму ссылку, не её цель.');
    }
    lines.push('Если файл используется, ссылки на него могут сломаться. Продолжайте только если это осознанное решение.');
    return lines;
  }

  function forceModal(f, j, actionLabel, onForce) {
    var canForce = !j || j.can_force !== false;
    var buttons = [{ label: 'Отмена', close: true }];
    if (canForce) {
      buttons.push({
        label: actionLabel,
        danger: true,
        onClick: function () { onForce(true); }
      });
    }
    showModal('Нужно подтверждение', function (body) {
      appendText(body, (j && j.detail) || 'У файла есть активные связи.');
      appendUsage(body, j, f);
      forceComment(f, j).forEach(function (line) { appendText(body, line); });
      if (!canForce) appendText(body, 'Принудительное действие сейчас недоступно.');
      if (f) appendDirectusLink(body, f);
    }, buttons);
  }

  function showGitCommitModal(name, action) {
    showInfoModal(
      'Git: нужен commit',
      (action === 'rename' ? 'Переименование' : 'Удаление') + ' файла «' + name + '» добавлено в Git index. ' +
      'Пока изменения не закоммичены и не отправлены, деплой будет заблокирован, чтобы файл не вернулся. ' +
      'Выполните commit и push из репозитория.'
    );
  }

  function folderById(id) {
    for (var i = 0; i < folders.length; i++) {
      if (folders[i].id === id) return folders[i];
    }
    return null;
  }

  function folderPathText(id) {
    if (!id) return 'Без папки';
    var parts = [];
    var seen = {};
    var cur = id;
    while (cur && !seen[cur] && parts.length < 30) {
      seen[cur] = true;
      var item = folderById(cur);
      if (!item) break;
      parts.push(item.name);
      cur = item.parent || '';
    }
    return parts.length ? parts.reverse().join(' / ') : 'Папка';
  }

  function folderCounts() {
    var counts = {};
    files.concat(media).forEach(function (f) {
      var id = f.folder_id || '';
      counts[id] = (counts[id] || 0) + 1;
    });
    return counts;
  }

  function folderChildren(parentId) {
    var parent = parentId || '';
    return folders.filter(function (f) { return (f.parent || '') === parent; });
  }

  function folderFileCount(id) {
    return files.concat(media).filter(function (f) { return (f.folder_id || '') === id; }).length;
  }

  function itemKey(f) {
    return (f.source === 'directus' ? 'directus:' : 'local:') + (f.id || f.name);
  }

  function previewUrl(f) {
    var url = (f && f.url) || ('/assets/' + encodeURIComponent((f && (f.id || f.name)) || ''));
    if (f && f.source === 'directus') return url;
    if (/^(?:https?:)?\/\//i.test(url) || /^data:/i.test(url)) return url;
    return siteOrigin + (url.charAt(0) === '/' ? url : '/' + url);
  }

  function selectedItems() {
    var out = [];
    files.concat(media).forEach(function (f) {
      if (selected[itemKey(f)]) out.push(f);
    });
    return out;
  }

  function updateBatchBar() {
    if (!batchBar) return;
    var items = selectedItems();
    batchBar.hidden = items.length === 0;
    if (selCount) selCount.textContent = 'Выбрано: ' + items.length;
    if (batchFolder) {
      var current = batchFolder.value;
      batchFolder.innerHTML = '';
      var root = document.createElement('option');
      root.value = '';
      root.textContent = 'Без папки (корень)';
      batchFolder.appendChild(root);
      folders.forEach(function (f) {
        var o = document.createElement('option');
        o.value = f.id;
        o.textContent = folderPathText(f.id);
        batchFolder.appendChild(o);
      });
      batchFolder.value = current || '';
    }
    var all = $('#selectAll');
    if (all) {
      var visible = visibleKeys.filter(function (k) { return !!selected[k]; }).length;
      all.checked = visibleKeys.length > 0 && visible === visibleKeys.length;
      all.indeterminate = visible > 0 && visible < visibleKeys.length;
    }
  }

  function addFolderCard(name, id, countValue) {
    var card = document.createElement('div');
    card.className = 'folder-card';
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    var icon = document.createElement('div');
    icon.className = 'ficon';
    icon.textContent = '📁';
    var title = document.createElement('div');
    title.className = 'fname';
    title.textContent = name;
    var note = document.createElement('div');
    note.className = 'fcount';
    note.textContent = countValue + ' файл(ов)';
    card.appendChild(icon);
    card.appendChild(title);
    card.appendChild(note);
    var open = function () { setFolder(id); };
    card.addEventListener('click', open);
    card.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    grid.appendChild(card);
  }

  function addFolderChip(label, id, countValue, active) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip' + (active ? ' active' : '');
    b.textContent = label;
    var c = document.createElement('span');
    c.className = 'cnt';
    c.textContent = String(countValue || 0);
    b.appendChild(c);
    b.addEventListener('click', function () { setFolder(id); });
    folderBar.appendChild(b);
  }

  function renderFolderBar() {
    folderBar.innerHTML = '';
    var counts = folderCounts();
    addFolderChip('Все файлы', ALL, files.length + media.length, currentFolder === ALL);
    addFolderChip('Без папки', ROOT, counts[ROOT] || 0, currentFolder === ROOT);
    if (currentFolder !== ALL && currentFolder !== ROOT) {
      var back = document.createElement('button');
      back.type = 'button';
      back.className = 'chip';
      back.textContent = '← Наверх';
      back.addEventListener('click', function () {
        var item = folderById(currentFolder);
        setFolder(item && item.parent ? item.parent : ALL);
      });
      folderBar.appendChild(back);
    }
    var parent = (currentFolder === ALL || currentFolder === ROOT) ? '' : currentFolder;
    folderChildren(parent).forEach(function (f) {
      addFolderChip(f.name, f.id, counts[f.id] || 0, false);
    });
    if (currentFolder === ALL) folderPath.textContent = 'Показаны все файлы; папки — в корне галереи';
    else if (currentFolder === ROOT) folderPath.textContent = 'Показаны файлы без папки';
    else folderPath.textContent = 'Папка: ' + folderPathText(currentFolder);
    if (dropTarget) {
      dropTarget.textContent = currentFolder === ALL || currentFolder === ROOT
        ? 'В корень галереи'
        : 'В папку «' + folderPathText(currentFolder) + '»';
    }
  }

  function setFolder(id) {
    if (id !== ALL && id !== ROOT && !folderById(id)) id = ALL;
    currentFolder = id;
    render();
  }

  function currentFolderForUpload() {
    return (currentFolder && currentFolder !== ALL) ? currentFolder : '';
  }

  function folderBadge(f) {
    if (!f.folder_id) return null;
    var b = document.createElement('span');
    b.className = 'badge folder';
    b.textContent = 'папка: ' + folderPathText(f.folder_id);
    return b;
  }

  function createFolder() {
    var name = prompt('Название новой папки:');
    if (!name || !name.trim()) return;
    var parent = (currentFolder && currentFolder !== ALL && currentFolder !== ROOT) ? currentFolder : '';
    apiFetch(API + '/folders', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ name: name.trim(), parent: parent })
    }).then(function (res) {
      if (!res.ok) throw new Error((res.j && res.j.detail) || 'ошибка');
      toast('Папка создана: ' + res.j.folder.name);
      return load().then(function () { setFolder(res.j.folder.id); });
    }).catch(function (e) { toast('Не удалось создать папку: ' + e.message, true); });
  }

  function moveFile(f) {
    var select = document.createElement('select');
    select.className = 'move-select';
    var root = document.createElement('option');
    root.value = '';
    root.textContent = 'Без папки';
    select.appendChild(root);
    folders.forEach(function (item) {
      var o = document.createElement('option');
      o.value = item.id;
      o.textContent = folderPathText(item.id);
      select.appendChild(o);
    });
    select.value = f.folder_id || '';
    showModal('Переместить файл', function (body) {
      appendText(body, 'Файл: ' + f.name + '. Физический путь /assets не меняется — перемещение только в структуре галереи.');
      body.appendChild(select);
    }, [
      { label: 'Отмена', close: true },
      {
        label: 'Переместить',
        primary: true,
        onClick: function () {
          var source = f.source === 'directus' ? 'directus' : 'local';
          var key = source === 'directus' ? f.id : f.name;
          apiFetch(API + '/folders/move', {
            method: 'POST',
            headers: authHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ source: source, key: key, folder_id: select.value })
          }).then(function (res) {
            if (!res.ok) throw new Error((res.j && res.j.detail) || 'ошибка');
            toast('Перемещено: ' + f.name);
            load();
          }).catch(function (e) { toast('Не удалось переместить: ' + e.message, true); });
        }
      }
    ]);
  }

  function usageUrl(f) {
    return f.source === 'directus'
      ? API + '/usage-check?id=' + encodeURIComponent(f.id)
      : API + '/usage-check?file=' + encodeURIComponent(f.name);
  }

  function performDelete(f, force) {
    var url = f.source === 'directus'
      ? API + '/media/' + encodeURIComponent(f.id) + '?force=' + (force ? 'true' : 'false')
      : API + '/delete?file=' + encodeURIComponent(f.name) + '&force=' + (force ? 'true' : 'false');
    apiFetch(url, { method: 'DELETE', headers: authHeaders() }).then(function (res) {
      if (!res.ok) {
        if (res.status === 409 && res.j && res.j.can_force && !force) {
          forceModal(f, res.j, 'Удалить принудительно', function () { performDelete(f, true); });
          return;
        }
        showErrorModal('Не удалось удалить', res.j, f);
        return;
      }
      toast('Удалено: ' + f.name);
      if (res.j && res.j.git_commit_required) showGitCommitModal(f.name, 'delete');
      load();
    }).catch(function (e) { toast('Не удалось удалить: ' + e.message, true); });
  }

  function deleteFile(f) {
    apiFetch(usageUrl(f), { headers: authHeaders() }).then(function (res) {
      var j = res.j || {};
      if (res.status === 503 || j.available === false) {
        showErrorModal('Не удалось проверить файл', j, f);
        return;
      }
      if (!res.ok && res.status !== 409) {
        showErrorModal('Не удалось проверить файл', j, f);
        return;
      }
      if (res.status === 409 || j.force_required || j.deletable === false) {
        if (j.can_force) {
          forceModal(f, j, 'Удалить принудительно', function (force) { performDelete(f, force); });
        } else {
          showErrorModal('Удаление недоступно', j, f);
        }
        return;
      }
      var extra = f.source === 'directus'
        ? 'Файл будет удалён из медиатеки Directus.'
        : 'Файл не используется и не отслеживается Git.';
      if (!confirm('Удалить файл ' + f.name + '?\n\n' + extra)) return;
      performDelete(f, false);
    }).catch(function (e) { toast('Не удалось проверить файл: ' + e.message, true); });
  }

  function batchTargets(items) {
    return items.map(function (f) {
      return {
        source: f.source === 'directus' ? 'directus' : 'local',
        key: f.source === 'directus' ? f.id : f.name
      };
    });
  }

  function runBatchDelete(items, force) {
    apiFetch(API + '/batch/delete', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ items: batchTargets(items), force: !!force })
    }).then(function (res) {
      if (res.status === 409 && res.j && res.j.can_force && !force) {
        var blocked = res.j.blocked || [];
        var text = blocked.slice(0, 8).map(function (x) { return x.name || x.key; }).join('\n');
        if (confirm('Эти файлы используются или отслеживаются Git:\n\n' + text +
          '\n\nУдалить принудительно? Действие нельзя отменить.')) {
          runBatchDelete(items, true);
        }
        return;
      }
      if (!res.ok) {
        toast('Массовое удаление: ' + ((res.j && res.j.detail) || ('HTTP ' + res.status)), true);
        return;
      }
      var deleted = (res.j && res.j.deleted) || [];
      var failed = (res.j && res.j.failed) || [];
      toast('Удалено: ' + deleted.length + (failed.length ? ', ошибок: ' + failed.length : ''), failed.length > 0);
      if (res.j && res.j.git_commit_required) showGitCommitModal('выбранные файлы', 'delete');
      selected = {};
      load();
    }).catch(function (e) { toast('Массовое удаление: ' + e.message, true); });
  }

  function batchDelete() {
    var items = selectedItems();
    if (!items.length) { toast('Ничего не выбрано', true); return; }
    if (!confirm('Удалить выбранные файлы (' + items.length + ')? Сначала будет проверено использование и Git.')) return;
    runBatchDelete(items, false);
  }

  function batchMove() {
    var items = selectedItems();
    if (!items.length) { toast('Ничего не выбрано', true); return; }
    var folderId = batchFolder ? batchFolder.value : '';
    var label = folderId ? folderPathText(folderId) : 'корень (без папки)';
    if (!confirm('Переместить выбранные файлы (' + items.length + ') в «' + label + '»?')) return;
    apiFetch(API + '/batch/move', {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ items: batchTargets(items), folder_id: folderId })
    }).then(function (res) {
      if (!res.ok) throw new Error((res.j && res.j.detail) || ('HTTP ' + res.status));
      toast('Перемещено файлов: ' + (res.j.moved || items.length));
      selected = {};
      load();
    }).catch(function (e) { toast('Не удалось переместить: ' + e.message, true); });
  }

  function performRename(f, next, force) {
    var url = f.source === 'directus' ? API + '/media/rename' : API + '/rename';
    var payload = f.source === 'directus'
      ? { id: f.id, new: next, force: !!force }
      : { old: f.name, new: next, force: !!force };
    apiFetch(url, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(payload)
    }).then(function (res) {
      if (!res.ok) {
        if (res.status === 409 && res.j && res.j.can_force && !force) {
          forceModal(f, res.j, 'Переименовать принудительно', function () { performRename(f, next, true); });
          return;
        }
        showErrorModal('Не удалось переименовать', res.j, f);
        return;
      }
      toast('Переименовано: ' + (res.j.old || f.name) + ' -> ' + res.j.name);
      if (res.j && res.j.git_commit_required) showGitCommitModal(res.j.name, 'rename');
      load();
    }).catch(function (e) { toast('Не удалось переименовать: ' + e.message, true); });
  }

  function renameFile(f) {
    var next = prompt('Новое имя файла (с расширением):', f.name);
    if (!next || next.trim() === f.name) return;
    next = next.trim();
    apiFetch(usageUrl(f), { headers: authHeaders() }).then(function (res) {
      var j = res.j || {};
      if (res.status === 503 || j.available === false) {
        showErrorModal('Не удалось проверить файл', j, f);
        return;
      }
      if (!res.ok && res.status !== 409) {
        showErrorModal('Не удалось проверить файл', j, f);
        return;
      }
      if (res.status === 409 || j.force_required || j.deletable === false) {
        if (j.can_force) {
          forceModal(f, j, 'Переименовать принудительно', function (force) { performRename(f, next, force); });
        } else {
          showErrorModal('Переименование недоступно', j, f);
        }
        return;
      }
      performRename(f, next, false);
    }).catch(function (e) { toast('Не удалось проверить файл: ' + e.message, true); });
  }

  function autoNameMedia(f) {
    if (!f.products || !f.products.length) {
      toast('Сначала привяжите файл к товару в Directus', true);
      return;
    }
    var product = f.products[0];
    var productValue = (product && typeof product === 'object')
      ? (product.id || product.slug || product.name || product.label)
      : String(product || '');
    function run(force) {
      apiFetch(API + '/media/auto-name', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ id: f.id, product: productValue, force: !!force })
      }).then(function (res) {
        if (!res.ok) {
          if (res.status === 409 && res.j && res.j.can_force && !force) {
            forceModal(f, res.j, 'Переименовать принудительно', function () { run(true); });
            return;
          }
          showErrorModal('Не удалось задать SEO-имя', res.j, f);
          return;
        }
        toast(res.j.renamed ? 'Имя: ' + res.j.name : 'Имя уже соответствует товару: ' + res.j.name);
        load();
      }).catch(function (e) { toast('Не удалось задать SEO-имя: ' + e.message, true); });
    }
    run(false);
  }

  function usageToast(f) {
    var url = f.source === 'directus'
      ? API + '/usage?id=' + encodeURIComponent(f.id)
      : API + '/usage?file=' + encodeURIComponent(f.name);
    apiFetch(url, { headers: authHeaders() }).then(function (res) {
      if (!res.ok) {
        toast('Не удалось проверить: ' + ((res.j && res.j.detail) || ('HTTP ' + res.status)), true);
        return;
      }
      var u = res.j || {};
      if (u.available === false) {
        toast('Не удалось проверить: ' + (u.error || 'Directus недоступен'), true);
        return;
      }
      var used = usageParts(u);
      toast(used.length ? 'Используется: ' + used.join(' · ') : 'Нигде не используется');
    }).catch(function (e) { toast('Не удалось проверить: ' + e.message, true); });
  }

  function addProductLine(body, f) {
    if (!f.products || !f.products.length) return;
    var line = document.createElement('div');
    line.className = 'used';
    var label = document.createElement('span');
    label.textContent = 'В товарах: ';
    line.appendChild(label);
    f.products.slice(0, 4).forEach(function (p, idx) {
      if (idx) line.appendChild(document.createTextNode(', '));
      var a = document.createElement('a');
      a.href = productAdminUrl(p);
      a.target = '_blank';
      a.rel = 'noopener';
      a.textContent = productTitle(p);
      a.title = 'Открыть товар в Directus';
      line.appendChild(a);
    });
    if (f.products.length > 4) {
      var more = document.createElement('button');
      more.type = 'button';
      more.className = 'more linklike';
      more.textContent = ' +' + (f.products.length - 4);
      more.title = 'Показать все товары';
      more.addEventListener('click', function () {
        showModal('Товары, где используется файл', function (b) {
          appendProductLinks(b, f.products, 'Товары:');
        });
      });
      line.appendChild(more);
    }
    body.appendChild(line);
  }

  function renderProductSelect() {
    var previous = productSelect.value;
    productSelect.innerHTML = '';
    if (!productCatalog.length) {
      var none = document.createElement('option');
      none.value = '';
      none.textContent = productCatalog.length ? 'Выберите товар' : 'Товары не загружены';
      productSelect.appendChild(none);
      productSelect.disabled = true;
      return;
    }
    productSelect.disabled = false;
    productCatalog.forEach(function (p) {
      var o = document.createElement('option');
      o.value = p.id || p.slug || p.name || '';
      o.textContent = p.label || p.name || p.slug || String(p.id);
      productSelect.appendChild(o);
    });
    if (previous) {
      for (var i = 0; i < productSelect.options.length; i++) {
        if (productSelect.options[i].value === previous) {
          productSelect.value = previous;
          break;
        }
      }
    }
  }

  function uploadProduct() {
    if (productUploadBtn.disabled) return;
    var file = productFile.files && productFile.files[0];
    if (!file) { toast('Выберите файл', true); return; }
    var product = productSelect.value;
    if (!product) { toast('Выберите товар', true); return; }
    var target = productTarget.value;
    var attach = target === 'directus' && productAttach.checked;
    var fd = new FormData();
    fd.append('file', file, file.name);
    fd.append('product', product);
    fd.append('target', target);
    fd.append('attach', attach ? '1' : '0');
    var folderId = currentFolderForUpload();
    if (folderId) fd.append('folder_id', folderId);
    toast('Загрузка фото товара...');
    productUploadBtn.disabled = true;
    apiFetch(API + '/upload-product', {
      method: 'POST',
      headers: authHeaders(),
      body: fd
    }).then(function (res) {
      productUploadBtn.disabled = false;
      if (!res.ok) {
        showErrorModal('Не удалось загрузить фото товара', res.j, null);
        return;
      }
      toast('Фото товара: ' + res.j.name);
      productFile.value = '';
      productFileName.textContent = 'файл не выбран';
      load();
    }).catch(function (e) {
      productUploadBtn.disabled = false;
      toast('Ошибка загрузки: ' + e.message, true);
    });
  }

  function upload(list) {
    var items = [], bad = [];
    Array.prototype.forEach.call(list, function (f) {
      if (!f) return;
      if (UPLOAD_RE.test(f.name || '')) items.push(f);
      else bad.push(f.name || 'без имени');
    });
    if (bad.length) toast('Не картинки, пропущено: ' + bad.join(', '), true);
    if (!items.length) { toast('Нужны файлы изображений (jpg, png, webp, avif, gif, svg)', true); return; }
    var big = items.filter(function (f) { return f.size > 50 * 1024 * 1024; });
    if (big.length) {
      items = items.filter(function (f) { return f.size <= 50 * 1024 * 1024; });
      toast('Больше 50 МБ, пропущено: ' + big.map(function (f) { return f.name; }).join(', '), true);
      if (!items.length) return;
    }
    var fd = new FormData();
    items.forEach(function (f) { fd.append('files', f, f.name); });
    var folderId = currentFolderForUpload();
    if (folderId) fd.append('folder_id', folderId);
    toast('Загрузка: ' + items.length + ' файл(ов)...');
    fetch(API + '/upload', { method: 'POST', headers: authHeaders(), body: fd })
      .then(function (r) {
        if (r.status === 413) throw new Error('файл слишком большой для сервера (лимит 64 МБ на запрос)');
        return r.json().then(function (j) { return { ok: r.ok, j: j }; });
      })
      .then(function (res) {
        if (!res.ok) throw new Error((res.j && res.j.detail) || 'ошибка');
        var up = (res.j.uploaded || []).length;
        var sk = (res.j.skipped || []).length;
        var errs = res.j.errors || [];
        toast('Загружено: ' + up + (sk ? ', пропущено: ' + sk : '') + (errs.length ? ', ошибок: ' + errs.length : ''));
        errs.concat(res.j.skipped || []).slice(0, 4).forEach(function (e) {
          toast(e.name + ': ' + e.reason, true);
        });
        load();
      })
      .catch(function (e) { toast('Ошибка загрузки: ' + e.message, true); });
  }

  function inCurrentFolder(f) {
    if (currentFolder === ALL) return true;
    if (currentFolder === ROOT) return !f.folder_id;
    return f.folder_id === currentFolder;
  }

  function render() {
    var q = $('#search').value.trim().toLowerCase();
    var sort = $('#sort').value;
    var all = files.concat(media);
    var scoped = all.filter(inCurrentFolder);
    var list = scoped.filter(function (f) { return !q || f.name.toLowerCase().indexOf(q) >= 0; });
    list.sort(function (a, b) {
      if (sort === 'date') return (b.mtime || 0) - (a.mtime || 0);
      if (sort === 'size') return (b.size || 0) - (a.size || 0);
      return a.name.localeCompare(b.name, 'ru');
    });

    var parent = (currentFolder === ALL || currentFolder === ROOT) ? '' : currentFolder;
    var childFolders = q ? [] : folderChildren(parent);
    grid.innerHTML = '';
    visibleKeys = list.map(itemKey);
    count.textContent = 'файлов: ' + list.length + ' из ' + all.length +
      (media.length ? ' · медиатека: ' + media.length : '') +
      (mediaWritable ? ' · Directus: токен задан' : ' · Directus только чтение');
    renderFolderBar();
    childFolders.forEach(function (folder) {
      addFolderCard(folder.name, folder.id, folderFileCount(folder.id));
    });

    if (!list.length && !childFolders.length) {
      empty.hidden = false;
      empty.textContent = currentFolder === ALL || currentFolder === ROOT
        ? 'Здесь пока нет файлов. Создайте папку или загрузите изображения.'
        : 'В папке «' + folderPathText(currentFolder) + '» пока нет файлов.';
      updateBatchBar();
      return;
    }
    empty.hidden = true;

    list.forEach(function (f) {
      var isMedia = f.source === 'directus';
      var card = document.createElement('div');
      card.className = 'card' + (selected[itemKey(f)] ? ' selected' : '');

      var pick = document.createElement('label');
      pick.className = 'pick';
      pick.title = 'Выбрать для массового действия';
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !!selected[itemKey(f)];
      cb.setAttribute('aria-label', 'Выбрать ' + f.name);
      cb.addEventListener('click', function (e) { e.stopPropagation(); });
      cb.addEventListener('change', function () {
        if (cb.checked) selected[itemKey(f)] = true;
        else delete selected[itemKey(f)];
        card.classList.toggle('selected', cb.checked);
        updateBatchBar();
      });
      pick.appendChild(cb);
      card.appendChild(pick);

      var thumb = document.createElement('div');
      thumb.className = 'thumb';
      var fallback = document.createElement('span');
      fallback.className = 'thumb-fallback';
      fallback.textContent = 'Нет превью';
      fallback.hidden = true;
      var img = document.createElement('img');
      img.loading = 'lazy';
      img.decoding = 'async';
      img.alt = f.name;
      img.onerror = function () {
        this.hidden = true;
        fallback.hidden = false;
        thumb.classList.add('thumb-missing');
      };
      img.src = previewUrl(f);
      thumb.appendChild(img);
      thumb.appendChild(fallback);

      var body = document.createElement('div');
      body.className = 'body';

      var nm = document.createElement('div');
      nm.className = 'name';
      nm.textContent = f.name;
      if (isMedia) {
        var bm = document.createElement('span');
        bm.className = 'badge media';
        bm.textContent = 'медиатека';
        bm.title = 'Файл из медиатеки Directus';
        nm.appendChild(bm);
      } else if (f.in_media) {
        var bc = document.createElement('span');
        bc.className = 'badge';
        bc.textContent = 'копия в медиатеке';
        bc.title = 'Такое же фото есть в медиатеке Directus';
        nm.appendChild(bc);
      }
      if (!isMedia && f.git_tracked === true) {
        var bg = document.createElement('span');
        bg.className = 'badge git';
        bg.textContent = 'Git';
        bg.title = 'Файл отслеживается Git. Принудительное действие стагируется через git rm/git mv.';
        nm.appendChild(bg);
      } else if (!isMedia && f.git_tracked === null) {
        var bgq = document.createElement('span');
        bgq.className = 'badge git';
        bgq.textContent = 'Git?';
        bgq.title = 'Не удалось проверить Git: действия будут заблокированы.';
        nm.appendChild(bgq);
      }
      if (f.symlink) {
        var bs = document.createElement('span');
        bs.className = 'badge git';
        bs.textContent = 'symlink';
        nm.appendChild(bs);
      }
      if (f.dup) {
        var bd = document.createElement('span');
        bd.className = 'badge dup';
        bd.textContent = 'ещё копий: ' + f.dup;
        nm.appendChild(bd);
      }
      if (f.products && f.products.length) {
        var bp = document.createElement('span');
        bp.className = 'badge product';
        bp.textContent = 'в товаре';
        bp.title = 'Используется в товарах: ' + f.products.map(productTitle).join(', ');
        nm.appendChild(bp);
      }
      var fb = folderBadge(f);
      if (fb) nm.appendChild(fb);

      var sub = document.createElement('div');
      sub.className = 'sub';
      sub.textContent = fmtSize(f.size) + ' · ' + fmtDate(f.mtime);

      var btns = document.createElement('div');
      btns.className = 'btns';

      var bCopy = document.createElement('button');
      bCopy.className = 'small primary';
      bCopy.textContent = isMedia ? 'Копировать URL' : 'Копировать путь';
      bCopy.addEventListener('click', function () { copyUrl(f.url || ('/assets/' + f.name)); });
      btns.appendChild(bCopy);

      if (isMedia) {
        var bOpen = document.createElement('button');
        bOpen.className = 'small';
        bOpen.textContent = 'Открыть';
        bOpen.addEventListener('click', function () { window.open(f.url, '_blank', 'noopener'); });
        btns.appendChild(bOpen);
      }

      var bUse = document.createElement('button');
      bUse.className = 'small';
      bUse.textContent = 'Использование';
      bUse.addEventListener('click', function () { usageToast(f); });
      btns.appendChild(bUse);

      if (isMedia) {
        var bFileAdmin = document.createElement('a');
        bFileAdmin.className = 'small btnlink';
        bFileAdmin.textContent = 'В Directus';
        bFileAdmin.href = fileAdminUrl(f.id);
        bFileAdmin.target = '_blank';
        bFileAdmin.rel = 'noopener';
        btns.appendChild(bFileAdmin);
      } else if (f.media_id) {
        var bMediaAdmin = document.createElement('a');
        bMediaAdmin.className = 'small btnlink';
        bMediaAdmin.textContent = 'Файл в Directus';
        bMediaAdmin.href = fileAdminUrl(f.media_id);
        bMediaAdmin.target = '_blank';
        bMediaAdmin.rel = 'noopener';
        btns.appendChild(bMediaAdmin);
      }

      var bMove = document.createElement('button');
      bMove.className = 'small';
      bMove.textContent = 'Переместить';
      bMove.addEventListener('click', function () { moveFile(f); });
      btns.appendChild(bMove);

      if (isMedia && mediaWritable && f.products && f.products.length) {
        var bSeo = document.createElement('button');
        bSeo.className = 'small';
        bSeo.textContent = 'SEO-имя';
        bSeo.title = 'Переименовать в slug товара: ' + (f.products[0].slug || f.products[0].name || f.products[0].label || '');
        bSeo.addEventListener('click', function () { autoNameMedia(f); });
        btns.appendChild(bSeo);
      }

      var bRen = document.createElement('button');
      bRen.className = 'small';
      bRen.textContent = 'Переименовать';
      bRen.addEventListener('click', function () { renameFile(f); });
      btns.appendChild(bRen);

      var bDel = document.createElement('button');
      bDel.className = 'small danger';
      bDel.textContent = 'Удалить';
      bDel.addEventListener('click', function () { deleteFile(f); });
      btns.appendChild(bDel);

      body.appendChild(nm);
      body.appendChild(sub);
      addProductLine(body, f);
      body.appendChild(btns);
      card.appendChild(thumb);
      card.appendChild(body);
      grid.appendChild(card);
    });
    updateBatchBar();
  }

  function load() {
    var seq = ++loadSeq;
    return apiFetch(API + '/list').then(function (res) {
      if (seq !== loadSeq) return;
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var j = res.j || {};
      siteOrigin = String(j.site_origin || DEFAULT_SITE_ORIGIN).replace(/\/+$/, '');
      files = (j.files || []).filter(function (f) { return IMG_RE.test(f.name); });
      media = j.directus || [];
      folders = j.folders || [];
      foldersOk = j.folders_ok !== false;
      mediaWritable = j.media_writable === true;
      productCatalog = j.product_catalog || [];
      if (currentFolder !== ALL && currentFolder !== ROOT && !folderById(currentFolder)) {
        currentFolder = ALL;
      }
      var live = {};
      files.concat(media).forEach(function (f) { live[itemKey(f)] = true; });
      Object.keys(selected).forEach(function (key) {
        if (!live[key]) delete selected[key];
      });
      renderProductSelect();
      render();
      if (j.media_ok === false) toast('Медиатека Directus сейчас недоступна — показаны только файлы сайта', true);
      if (j.products_ok === false) toast('Не удалось получить привязки к товарам: ' + (j.products_error || 'Directus недоступен'), true);
      if (!foldersOk) toast('Папки недоступны: ' + (j.folders_error || 'ошибка manifest'), true);
    }).catch(function (e) {
      if (seq !== loadSeq) return;
      toast('Не удалось получить список: ' + e.message, true);
      count.textContent = 'ошибка';
    });
  }

  // События
  $('#refreshBtn').addEventListener('click', load);
  $('#search').addEventListener('input', render);
  $('#sort').addEventListener('change', render);
  $('#createFolderBtn').addEventListener('click', createFolder);
  $('#allFilesBtn').addEventListener('click', function () { setFolder(ALL); });
  $('#rootFilesBtn').addEventListener('click', function () { setFolder(ROOT); });

  $('#loginForm').addEventListener('submit', function (e) {
    e.preventDefault();
    var email = $('#loginEmail').value.trim();
    var password = $('#loginPassword').value;
    var btn = $('#loginBtn');
    var err = $('#loginError');
    err.textContent = '';
    btn.disabled = true;
    btn.textContent = 'Проверка…';
    login(email, password).then(function (res) {
      setUser(res.user);
      hideLogin();
      toast('Вы вошли как ' + (res.user.name || res.user.email));
      return load();
    }).catch(function (ex) {
      err.textContent = ex.message || 'Не удалось войти';
    }).then(function () {
      btn.disabled = false;
      btn.textContent = 'Войти';
    });
  });

  $('#logoutBtn').addEventListener('click', logout);
  $('#batchDeleteBtn').addEventListener('click', batchDelete);
  $('#batchMoveBtn').addEventListener('click', batchMove);
  $('#batchClearBtn').addEventListener('click', function () {
    selected = {};
    render();
  });
  $('#selectAll').addEventListener('change', function (e) {
    var on = e.target.checked;
    visibleKeys.forEach(function (key) {
      if (on) selected[key] = true;
      else delete selected[key];
    });
    render();
  });

  productTarget.addEventListener('change', function () {
    var local = productTarget.value === 'local';
    productAttach.disabled = local;
    if (local) productAttach.checked = false;
  });
  productFile.addEventListener('change', function () {
    var picked = productFile.files && productFile.files[0];
    productFileName.textContent = picked ? picked.name : 'файл не выбран';
  });
  productUploadBtn.addEventListener('click', uploadProduct);

  var drop = $('#drop'), fileInput = $('#fileInput');
  drop.addEventListener('click', function () { fileInput.click(); });
  fileInput.addEventListener('change', function () { upload(fileInput.files); fileInput.value = ''; });
  ['dragenter', 'dragover'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('hot'); });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('hot'); });
  });
  drop.addEventListener('drop', function (e) {
    if (e.dataTransfer && e.dataTransfer.files) upload(e.dataTransfer.files);
  });
  document.addEventListener('paste', function (e) {
    if (!e.clipboardData || !e.clipboardData.files || !e.clipboardData.files.length) return;
    upload(e.clipboardData.files);
  });

  function bootstrap() {
    checkSession().then(function (res) {
      setUser(res.user);
      hideLogin();
      return load();
    }).catch(function () {
      showLogin('Войдите под аккаунтом администратора Directus.');
    });
  }

  bootstrap();
})();
