import base64, datetime, hashlib, hmac, json, mimetypes, os, re, secrets, shutil, subprocess, threading, time, urllib.error, urllib.parse, urllib.request, uuid
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Body, Request, Form, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="JNN Factory Enterprise Engine")
DATA_FILE = "/var/www/jnnfactory/admin/site_data.json"
ADMIN_HTML = "/var/www/jnnfactory/admin/index.html"
INDEX_FILE = "/var/www/jnnfactory/index.html"
ASSETS_DIR = os.environ.get("JNN_ASSETS_DIR") or "/var/www/jnnfactory/assets"

if os.path.exists(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

# ИИ-чат на сайте: /api/chat, /api/chat/lead, /api/chat/health, /api/chat/leads.
# Импорт в try/except, чтобы сбой чата не уронил админку.
try:
    from admin import chat_api as _chat  # noqa: E402

    app.include_router(_chat.router)
except Exception as _chat_exc:  # noqa: BLE001
    print(f"[chat] модуль чата не подключён: {_chat_exc}", flush=True)


@app.get("/")
async def root():
    return FileResponse(ADMIN_HTML)
@app.get("/api/content")
async def get_content():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

@app.post("/api/content")
async def update_content(payload: dict, x_gallery_key: str = Header(default="")):
    _check_key(x_gallery_key)  # этап 2: запись только с ключом (как у gallery-маршрутов)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    
    # Синхронизация hero и контактов в index.html
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            desc = payload.get("hero", {}).get("desc", "")
            if desc and 'id="jnn-hero-desc"' in content:
                start_m = 'id="jnn-hero-desc">'
                p1 = content.find(start_m)
                p2 = content.find('</p>', p1)
                if p1 != -1 and p2 != -1:
                    content = content[:p1 + len(start_m)] + desc + content[p2:]
            phone = payload.get("contacts", {}).get("phone", "")
            if phone:
                import re
                content = re.sub(r'tel:[+0-9\s-]+', f'tel:{phone}', content)
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            print(f"Sync error: {e}")
    return {"status": "success"}

@app.post("/api/upload")
async def upload_asset(file: UploadFile = File(...), x_gallery_key: str = Header(default="")):
    _check_key(x_gallery_key)  # этап 2: загрузка файлов только с ключом
    clean_name = os.path.basename(
        (file.filename or "").replace("\\", "/")
    ).replace(" ", "_").lstrip(".")
    ext = os.path.splitext(clean_name)[1].lower()
    allowed = (".jpg", ".jpeg", ".png", ".webp")
    if not clean_name or ext not in allowed:
        return {"error": "Only jpg/png/webp allowed"}
    target_dir = "/var/www/jnnfactory/assets/images"
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, clean_name)
    if os.path.islink(target_path):
        return {"error": "Symlinks are not allowed"}
    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"url": f"/assets/images/{clean_name}"}

@app.get("/pages")
async def get_pages():
    files = [f for f in os.listdir("/var/www/jnnfactory") if f.endswith('.html')]
    return [{"name": f.replace('.html',''), "url": "/" + f} for f in files]

@app.get("/media")
async def get_media():
    media_dir = "/var/www/jnnfactory/assets"
    if not os.path.exists(media_dir):
        return []
    return [{"name": f, "url": "/assets/" + f} for f in os.listdir(media_dir) if os.path.isfile(os.path.join(media_dir, f))]

@app.get("/edit")
async def edit_file():
    return {"status":"edit endpoint active"}

@app.post("/edit")
async def edit_post(x_gallery_key: str = Header(default="")):
    _check_key(x_gallery_key)  # этап 2: задел на будущее
    return {"status":"edit saved"}

@app.get("/settings")
async def get_settings():
    path = "/var/www/jnnfactory/admin/settings.json"
    if not os.path.exists(path):
        return {"site_name":"JNN Factory","email":"","logo":"","whatsapp":""}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

@app.post("/settings")
async def post_settings(x_gallery_key: str = Header(default="")):
    _check_key(x_gallery_key)  # этап 2: задел на будущее
    path = "/var/www/jnnfactory/admin/settings.json"
    data = {}
    return {"status":"saved"}

@app.get("/api/categories")
async def get_cats():
    return ["Производство одежды", "Шелкография", "СТМ бренды"]

@app.get("/api/catalog")
async def get_catalog():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("products", [])
    return []

@app.post("/api/catalog")
async def update_catalog(payload: dict, x_gallery_key: str = Header(default="")):
    _check_key(x_gallery_key)  # этап 2: запись каталога только с ключом
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    data["products"] = payload.get("products", [])
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"status": "saved"}


# ---------------------------------------------------------------------------
# Галерея изображений: список, загрузка, переименование (/gallery-api/...)
# Ключ доступа: переменная окружения JNN_GALLERY_KEY или файл admin/.gallery_key
# ---------------------------------------------------------------------------
GALLERY_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".gallery_key")
GALLERY_EXTS = {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".avif", ".gif", ".svg"}
GALLERY_MAX_FILE = 50 * 1024 * 1024  # 50 МБ на файл
GALLERY_ADMIN_DIR = os.path.dirname(os.path.abspath(__file__))
GALLERY_HTML = os.path.join(GALLERY_ADMIN_DIR, "gallery.html")
GALLERY_STATIC_DIR = os.path.join(GALLERY_ADMIN_DIR, "static")

# Медиатека Directus: фото, загруженные через админку. Только чтение, без секретов:
# список берётся из публичного /files (localhost), хэши — из storage-файлов.
DIRECTUS_API = os.environ.get("JNN_DIRECTUS_API", "http://127.0.0.1:8055")
DIRECTUS_UPLOADS = os.environ.get("JNN_DIRECTUS_UPLOADS", "/opt/directus/uploads")
# Токен нужен только для записи в Directus (переименование/удаление/загрузка).
# Чтение медиатеки работает без него. Секрет не хранится в репозитории.
DIRECTUS_TOKEN = (
    os.environ.get("JNN_DIRECTUS_TOKEN")
    or os.environ.get("DIRECTUS_TOKEN")
    or ""
).strip()
DIRECTUS_WRITE_TIMEOUT = 25
GALLERY_FOLDERS_FILE = os.environ.get("JNN_GALLERY_FOLDERS_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".gallery_folders.json"
)
_FOLDERS_LOCK = threading.RLock()
_HASH_CACHE = {}  # путь -> (размер, mtime, sha256)


class _DirectusFieldError(Exception):
    """Directus отклонил набор полей; это не transient-сбой."""


class _DirectusWriteError(Exception):
    """Ошибка записи в Directus с HTTP-статусом и человеческим текстом."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = int(status or 502)
        self.detail = detail or "Ошибка Directus"


def _gallery_key() -> str:
    key = (os.environ.get("JNN_GALLERY_KEY") or "").strip()
    if key:
        return key
    try:
        if os.path.exists(GALLERY_KEY_FILE):
            with open(GALLERY_KEY_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        key = uuid.uuid4().hex[:24]
        with open(GALLERY_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key)
        try:
            os.chmod(GALLERY_KEY_FILE, 0o600)
        except Exception:
            pass
        return key
    except Exception:
        return ""


def _check_key(key: Optional[str]) -> None:
    actual = _gallery_key()
    if not actual:
        raise HTTPException(status_code=503, detail="Ключ галереи не настроен на сервере")
    if not key or not hmac.compare_digest(key.encode("utf-8"), actual.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Неверный ключ доступа")


# ---------------------------------------------------------------------------
# Админ-сессия Directus для /gallery-api/*
#
# Публичной галереи больше нет: страница управления живёт на
# admin.jnnfactory.online/gallery и требует логин Directus с правами
# администратора. Пароль проверяет Directus (/auth/login), а не этот сервис.
# В браузере хранится только непрозрачный HttpOnly session-id; access/refresh
# токены Directus остаются в памяти процесса.
# ---------------------------------------------------------------------------
ADMIN_ORIGIN = (os.environ.get("JNN_ADMIN_ORIGIN") or "https://admin.jnnfactory.online").rstrip("/")
SITE_ORIGIN = (os.environ.get("JNN_SITE_URL") or "https://jnnfactory.online").rstrip("/")
SESSION_COOKIE = "jnn_gallery_sid"
CSRF_COOKIE = "jnn_gallery_csrf"
SESSION_IDLE = 8 * 3600
_COOKIE_SECURE = (os.environ.get("JNN_GALLERY_COOKIE_SECURE") or "1").strip().lower() not in {
    "0", "false", "no", "off",
}
_ADMIN_SESSIONS = {}
_ADMIN_SESSIONS_LOCK = threading.RLock()
_LOGIN_FAILS = {}
_LOGIN_FAILS_LOCK = threading.RLock()
_LOGIN_MAX_FAILS = 5
_LOGIN_WINDOW = 300
PUBLISH_WEBHOOK_SECRET = (os.environ.get("JNN_PUBLISH_WEBHOOK_SECRET") or "").strip()


class _DirectusAuthError(Exception):
    """Ошибка auth/me Directus; не путать с ошибкой записи файлов."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = int(status or 503)
        self.detail = detail or "Directus недоступен"


def _directus_data(response):
    if isinstance(response, dict) and isinstance(response.get("data"), (dict, list)):
        return response["data"]
    return response


def _directus_error_text(raw: bytes) -> str:
    try:
        data = json.loads((raw or b"").decode("utf-8", "replace"))
    except Exception:
        return "Ошибка Directus"
    if isinstance(data, dict):
        errors = data.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            return str(errors[0].get("message") or "Ошибка Directus")
        if data.get("error"):
            return str(data["error"])
        if data.get("message"):
            return str(data["message"])
    return "Ошибка Directus"


def _directus_auth_request(method: str, path: str, payload=None, token: str = "", timeout: int = 15):
    """Запрос к Directus от имени пользователя (login/me/refresh)."""
    url = DIRECTUS_API.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        raise _DirectusAuthError(exc.code, _directus_error_text(exc.read())) from None
    except Exception:
        raise _DirectusAuthError(503, "Directus недоступен") from None


def _directus_login(email: str, password: str) -> dict:
    data = _directus_data(_directus_auth_request(
        "POST", "/auth/login",
        {"email": email, "password": password, "mode": "json"},
    ))
    if not isinstance(data, dict) or not data.get("access_token"):
        raise _DirectusAuthError(502, "Directus не вернул access token")
    return data


def _directus_me(token: str) -> dict:
    fields = (
        "id,email,first_name,last_name,role.id,role.name,role.admin_access,"
        "policies.policy.id,policies.policy.name,policies.policy.admin_access"
    )
    try:
        data = _directus_data(_directus_auth_request(
            "GET", "/users/me?fields=" + urllib.parse.quote(fields, safe=",.*"), token=token,
        ))
    except _DirectusAuthError as exc:
        if exc.status != 400:
            raise
        data = _directus_data(_directus_auth_request("GET", "/users/me?fields=*", token=token))
    if not isinstance(data, dict):
        raise _DirectusAuthError(502, "Directus вернул неожиданный ответ /users/me")
    return data


def _directus_refresh(refresh_token: str) -> dict:
    data = _directus_data(_directus_auth_request(
        "POST", "/auth/refresh", {"refresh_token": refresh_token, "mode": "json"},
    ))
    if not isinstance(data, dict) or not data.get("access_token"):
        raise _DirectusAuthError(401, "Сессия Directus истекла")
    return data


def _jwt_claims(token: str) -> dict:
    """Читает payload уже проверенного Directus JWT (подпись проверяет Directus)."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _directus_is_admin(user: dict, token: str = "") -> bool:
    """Администратор Directus: admin_access в policy или роль Administrator."""
    claims = _jwt_claims(token) if token else {}
    if claims.get("admin_access") is True:
        return True

    def _policy_admin(value) -> bool:
        if isinstance(value, list):
            return any(_policy_admin(x) for x in value)
        if not isinstance(value, dict):
            return False
        if value.get("admin_access") is True:
            return True
        policy = value.get("policy")
        if isinstance(policy, dict) and policy.get("admin_access") is True:
            return True
        if isinstance(value.get("policies"), list):
            return any(_policy_admin(x) for x in value["policies"])
        return False

    if _policy_admin(user.get("policies")):
        return True
    role = user.get("role")
    if isinstance(role, dict):
        if role.get("admin_access") is True:
            return True
        if str(role.get("name") or "").strip().casefold() == "administrator":
            return True
    if isinstance(role, str) and role:
        # Некоторые политики Directus отдают role только идентификатором.
        try:
            role_data = _directus_data(_directus_auth_request(
                "GET", "/roles/" + urllib.parse.quote(role) + "?fields=id,name,admin_access", token=token,
            ))
            if isinstance(role_data, dict):
                if role_data.get("admin_access") is True:
                    return True
                if str(role_data.get("name") or "").strip().casefold() == "administrator":
                    return True
        except _DirectusAuthError:
            pass
    return False


def _public_user(user: dict) -> dict:
    name = " ".join(
        part for part in (str(user.get("first_name") or "").strip(), str(user.get("last_name") or "").strip())
        if part
    )
    return {
        "id": str(user.get("id") or ""),
        "email": str(user.get("email") or ""),
        "name": name or str(user.get("email") or "Администратор"),
    }


def _expires_at(auth: dict) -> float:
    raw = auth.get("expires")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 900000.0
    # Directus отдаёт миллисекунды; маленькие значения считаем секундами.
    seconds = value / 1000.0 if value > 3600 else value
    return time.time() + max(30.0, seconds - 30.0)


def _refresh_session(session: dict) -> None:
    refresh_token = session.get("refresh_token") or ""
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Сессия истекла. Войдите заново.")
    try:
        auth = _directus_refresh(refresh_token)
    except _DirectusAuthError as exc:
        raise HTTPException(status_code=401, detail="Сессия истекла. Войдите заново.") from exc
    session["access_token"] = auth["access_token"]
    session["refresh_token"] = auth.get("refresh_token") or refresh_token
    session["expires_at"] = _expires_at(auth)


def _validated_session_user(session: dict) -> dict:
    if time.time() >= session.get("expires_at", 0):
        _refresh_session(session)
    token = session.get("access_token") or ""
    try:
        user = _directus_me(token)
    except _DirectusAuthError as exc:
        if exc.status == 401:
            _refresh_session(session)
            token = session.get("access_token") or ""
            try:
                user = _directus_me(token)
            except _DirectusAuthError as exc2:
                raise HTTPException(status_code=401, detail="Сессия Directus истекла. Войдите заново.") from exc2
        elif exc.status == 503:
            raise HTTPException(status_code=503, detail="Directus недоступен") from exc
        else:
            raise HTTPException(status_code=401, detail="Сессия Directus недействительна") from exc
    if not _directus_is_admin(user, token):
        raise HTTPException(status_code=403, detail="Нужны права администратора Directus")
    session["user"] = _public_user(user)
    session["last_seen"] = time.time()
    return session["user"]


def _session_from_request(request: Request):
    sid = request.cookies.get(SESSION_COOKIE) or ""
    if not sid:
        return None, None
    with _ADMIN_SESSIONS_LOCK:
        session = _ADMIN_SESSIONS.get(sid)
    if not session:
        return None, None
    if time.time() - float(session.get("last_seen", 0)) > SESSION_IDLE:
        with _ADMIN_SESSIONS_LOCK:
            _ADMIN_SESSIONS.pop(sid, None)
        return None, None
    return sid, session


def _origin_allowed(value: str) -> bool:
    if not value:
        return True
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return False
    return (parsed.scheme + "://" + parsed.netloc).rstrip("/") == ADMIN_ORIGIN


def _csrf_ok(request: Request, session: dict) -> bool:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if not _origin_allowed(origin):
        return False
    supplied = request.headers.get("x-csrf-token") or ""
    expected = session.get("csrf") or ""
    return bool(supplied and expected and secrets.compare_digest(supplied, expected))


def _authenticate_admin(request: Request) -> dict:
    """Проверка администратора для всех /gallery-api/*."""
    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Нужна авторизация")
        try:
            user = _directus_me(token)
        except _DirectusAuthError as exc:
            if exc.status == 503:
                raise HTTPException(status_code=503, detail="Directus недоступен") from exc
            raise HTTPException(status_code=401, detail="Токен Directus недействителен") from exc
        if not _directus_is_admin(user, token):
            raise HTTPException(status_code=403, detail="Нужны права администратора Directus")
        return {"type": "bearer", "user": _public_user(user)}

    sid, session = _session_from_request(request)
    if not session:
        raise HTTPException(status_code=401, detail="Нужна авторизация администратора")
    user = _validated_session_user(session)
    if not _csrf_ok(request, session):
        raise HTTPException(status_code=403, detail="CSRF-проверка не пройдена")
    with _ADMIN_SESSIONS_LOCK:
        _ADMIN_SESSIONS[sid]["last_seen"] = time.time()
    return {"type": "session", "user": user}


def _client_ip(request: Request) -> str:
    for header in ("x-real-ip", "x-forwarded-for"):
        value = (request.headers.get(header) or "").strip()
        if value:
            return value.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _login_allowed(ip: str) -> bool:
    now = time.time()
    with _LOGIN_FAILS_LOCK:
        attempts = [t for t in _LOGIN_FAILS.get(ip, []) if now - t < _LOGIN_WINDOW]
        _LOGIN_FAILS[ip] = attempts
        return len(attempts) < _LOGIN_MAX_FAILS


def _login_failed(ip: str) -> None:
    with _LOGIN_FAILS_LOCK:
        _LOGIN_FAILS.setdefault(ip, []).append(time.time())


def _set_session_cookies(response: Response, sid: str, csrf: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, sid, max_age=SESSION_IDLE, httponly=True,
        secure=_COOKIE_SECURE, samesite="strict", path="/",
    )
    response.set_cookie(
        CSRF_COOKIE, csrf, max_age=SESSION_IDLE, httponly=False,
        secure=_COOKIE_SECURE, samesite="strict", path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=_COOKIE_SECURE, samesite="strict")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=_COOKIE_SECURE, samesite="strict")


def _new_admin_session(user: dict, auth: dict) -> tuple:
    sid = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    now = time.time()
    with _ADMIN_SESSIONS_LOCK:
        _ADMIN_SESSIONS[sid] = {
            "user": _public_user(user),
            "access_token": auth["access_token"],
            "refresh_token": auth.get("refresh_token") or "",
            "expires_at": _expires_at(auth),
            "csrf": csrf,
            "created": now,
            "last_seen": now,
        }
    return sid, csrf


@app.middleware("http")
async def _gallery_auth_middleware(request: Request, call_next):
    """Закрывает весь /gallery-api/*, включая будущие эндпоинты."""
    if request.url.path.startswith("/gallery-api/") and request.method != "OPTIONS":
        try:
            request.state.admin = _authenticate_admin(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.post("/gallery-auth/login")
async def gallery_login(request: Request, response: Response, payload: dict = Body(...)):
    origin = request.headers.get("origin") or ""
    if origin and not _origin_allowed(origin):
        raise HTTPException(status_code=403, detail="Запрос с чужого origin запрещён")
    ip = _client_ip(request)
    if not _login_allowed(ip):
        raise HTTPException(status_code=429, detail="Слишком много попыток входа. Повторите позже.")
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="Укажите email и пароль Directus")
    try:
        auth = await run_in_threadpool(_directus_login, email, password)
    except _DirectusAuthError as exc:
        _login_failed(ip)
        if exc.status in (401, 403):
            raise HTTPException(status_code=401, detail="Неверный email или пароль Directus") from exc
        if exc.status == 429:
            raise HTTPException(status_code=429, detail="Directus временно ограничил вход") from exc
        raise HTTPException(status_code=503, detail="Не удалось войти в Directus") from exc
    token = auth["access_token"]
    try:
        user = await run_in_threadpool(_directus_me, token)
    except _DirectusAuthError as exc:
        _login_failed(ip)
        raise HTTPException(status_code=401, detail="Не удалось проверить пользователя Directus") from exc
    if not _directus_is_admin(user, token):
        _login_failed(ip)
        raise HTTPException(status_code=403, detail="Нужны права администратора Directus")
    sid, csrf = _new_admin_session(user, auth)
    _set_session_cookies(response, sid, csrf)
    with _LOGIN_FAILS_LOCK:
        _LOGIN_FAILS.pop(ip, None)
    return {"ok": True, "user": _public_user(user)}


@app.get("/gallery-auth/me")
async def gallery_me(request: Request):
    admin = _authenticate_admin(request)
    return {"authenticated": True, "user": admin["user"], "type": admin["type"]}


@app.post("/gallery-auth/logout")
async def gallery_logout(request: Request, response: Response):
    sid = request.cookies.get(SESSION_COOKIE) or ""
    if sid:
        with _ADMIN_SESSIONS_LOCK:
            _ADMIN_SESSIONS.pop(sid, None)
    _clear_session_cookies(response)
    return {"ok": True}


def _safe_name(name: str) -> str:
    name = (name or "").strip().replace("\\", "/").split("/")[-1]
    name = name.replace(" ", "-")
    name = re.sub(r"[^\w.\-]", "", name, flags=re.UNICODE)
    return name.lstrip(".")


def _existing_name(value) -> str:
    """Имя уже существующего файла без нормализации.

    ``_safe_name`` нужен для новых загрузок, но он превращает ``photo (1).jpg``
    в ``photo-1.jpg``. Для удаления/переименования/папок нужно принимать
    реальное имя: иначе такие файлы невозможно обслужить из галереи.
    """
    name = str(value or "")
    if not name or name in (".", "..") or "\x00" in name:
        return ""
    if "/" in name or "\\" in name:
        return ""
    if os.path.basename(name) != name:
        return ""
    return name


def _assets_base() -> str:
    """Реальный путь assets: deploy может использовать релизный symlink."""
    return os.path.realpath(ASSETS_DIR)


def _media_id(value) -> str:
    uid = str(value or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", uid):
        raise ValueError("Неверный id файла")
    return uid


def _asset_url(name: str) -> str:
    """URL локального asset с экранированием пробелов/юникода/решётки."""
    return "/assets/" + urllib.parse.quote(name, safe="")


def _empty_folders() -> dict:
    return {"version": 1, "folders": [], "files": {}}


def _load_folders():
    """Читает виртуальные папки галереи.

    Папки не меняют физические пути: URL ``/assets/<file>`` и 13 статических
    страниц остаются прежними. Это важно, потому что перемещение реальных
    файлов по подкаталогам сломало бы ссылки и Git-деплой.

    Возвращает ``(data, error)``. При повреждённом manifest операции записи
    должны быть запрещены, а список файлов продолжает работать.
    """
    with _FOLDERS_LOCK:
        path = GALLERY_FOLDERS_FILE
        if not os.path.lexists(path):
            return _empty_folders(), None
        if os.path.islink(path):
            return _empty_folders(), "manifest папок является символической ссылкой"
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            return _empty_folders(), "не удалось прочитать manifest папок"
        if not isinstance(raw, dict):
            return _empty_folders(), "manifest папок повреждён"
        raw_folders = raw.get("folders")
        raw_files = raw.get("files")
        if not isinstance(raw_folders, list) or not isinstance(raw_files, dict):
            return _empty_folders(), "manifest папок повреждён"
        folders = []
        seen = set()
        for item in raw_folders:
            if not isinstance(item, dict):
                return _empty_folders(), "manifest папок повреждён"
            fid = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            parent = str(item.get("parent") or "").strip()
            if not fid or not name or fid in seen:
                return _empty_folders(), "manifest папок повреждён"
            seen.add(fid)
            folders.append({"id": fid, "name": name, "parent": parent})
        files = {}
        for key, fid in raw_files.items():
            if not isinstance(key, str) or not isinstance(fid, str):
                return _empty_folders(), "manifest папок повреждён"
            if key and fid:
                files[key] = fid
        return {"version": 1, "folders": folders, "files": files}, None


def _folders_strict() -> dict:
    data, error = _load_folders()
    if error:
        raise RuntimeError(error)
    return data


def _save_folders(data: dict) -> None:
    """Атомарно сохраняет manifest папок, не проходя через symlink."""
    with _FOLDERS_LOCK:
        path = GALLERY_FOLDERS_FILE
        parent = os.path.dirname(os.path.abspath(path)) or "."
        os.makedirs(parent, exist_ok=True)
        if os.path.islink(path):
            raise RuntimeError("manifest папок является символической ссылкой")
        tmp = os.path.join(parent, ".gallery_folders.%s.tmp" % uuid.uuid4().hex)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(tmp, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def _folder_ids(data: dict) -> set:
    return {str(f.get("id") or "") for f in data.get("folders", []) if f.get("id")}


def _folder_key(source: str, key: str) -> str:
    return ("%s:%s" % (source, key)).strip()


def _folder_assignment(data: dict, source: str, key: str) -> str:
    fid = str(data.get("files", {}).get(_folder_key(source, key)) or "")
    return fid if fid in _folder_ids(data) else ""


def _valid_folder_name(value) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    name = name.replace("/", "-").replace("\\", "-")
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    if not name or name in (".", ".."):
        raise ValueError("Укажите название папки")
    if len(name) > 80:
        raise ValueError("Название папки длиннее 80 символов")
    return name


def _create_folder(name: str, parent: str = "") -> dict:
    with _FOLDERS_LOCK:
        data = _folders_strict()
        if parent and parent not in _folder_ids(data):
            raise ValueError("Родительская папка не найдена")
        folded = name.casefold()
        for item in data["folders"]:
            if str(item.get("parent") or "") == parent and str(item.get("name") or "").casefold() == folded:
                raise FileExistsError("Папка с таким названием уже есть")
        folder = {"id": uuid.uuid4().hex, "name": name, "parent": parent}
        data["folders"].append(folder)
        _save_folders(data)
        return folder


def _set_folder_assignment(source: str, key: str, folder_id: str = "") -> None:
    with _FOLDERS_LOCK:
        data = _folders_strict()
        if folder_id and folder_id not in _folder_ids(data):
            raise ValueError("Папка не найдена")
        storage_key = _folder_key(source, key)
        if folder_id:
            data["files"][storage_key] = folder_id
        else:
            if storage_key not in data["files"]:
                return
            data["files"].pop(storage_key, None)
        _save_folders(data)


def _move_folder_assignment(source: str, key: str, folder_id: str) -> None:
    _set_folder_assignment(source, key, folder_id)


def _move_folder_assignments(items: list, folder_id: str) -> int:
    """Атомарно перемещает несколько файлов: один manifest, одна запись."""
    with _FOLDERS_LOCK:
        data = _folders_strict()
        if folder_id and folder_id not in _folder_ids(data):
            raise ValueError("Папка не найдена")
        keys = []
        for source, key in items:
            storage_key = _folder_key(source, key)
            if not storage_key:
                raise ValueError("Не указан файл")
            keys.append(storage_key)
        for storage_key in keys:
            if folder_id:
                data["files"][storage_key] = folder_id
            else:
                data["files"].pop(storage_key, None)
        _save_folders(data)
        return len(keys)


def _rename_folder_assignment(old: str, new: str) -> None:
    with _FOLDERS_LOCK:
        data = _folders_strict()
        old_key = _folder_key("local", old)
        new_key = _folder_key("local", new)
        fid = data["files"].pop(old_key, None)
        if fid:
            data["files"][new_key] = fid
            _save_folders(data)
        elif old_key in data["files"]:
            data["files"].pop(old_key, None)
            _save_folders(data)


def _drop_folder_assignment(source: str, key: str) -> None:
    try:
        _set_folder_assignment(source, key, "")
    except Exception:
        # Удаление файла не должно падать из-за необязательного manifest.
        pass


def _git_remove_tracked(name: str):
    """Удаляет tracked-файл через git rm, чтобы деплой не вернул его."""
    root = os.path.dirname(ASSETS_DIR)
    rel = "assets/" + name
    try:
        proc = subprocess.run(
            ["git", "-C", root, "rm", "-f", "--", rel],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, proc.stderr.decode("utf-8", "replace").strip() or "git rm завершился с ошибкой"
    return True, ""


def _git_move_tracked(old: str, new: str):
    """Переименовывает tracked-файл через git mv (rename staged)."""
    root = os.path.dirname(ASSETS_DIR)
    try:
        proc = subprocess.run(
            ["git", "-C", root, "mv", "--", "assets/" + old, "assets/" + new],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, proc.stderr.decode("utf-8", "replace").strip() or "git mv завершился с ошибкой"
    return True, ""


def _slug_base(value) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if len(base) > 100:
        base = base[:100].strip("-")
    return base or "product"


def _auto_extension(original: str) -> str:
    ext = os.path.splitext(str(original or ""))[1].lower()
    if ext in (".jpeg", ".jfif"):
        ext = ".jpg"
    if ext not in GALLERY_EXTS:
        ext = ".jpg"
    return ext


def _next_auto_name(slug: str, original: str, existing) -> str:
    """``slug.jpg``, ``slug1.jpg``, ``slug2.jpg`` без перезаписи."""
    base = _slug_base(slug)
    ext = _auto_extension(original)
    taken = {str(x or "").casefold() for x in existing}
    candidate = base + ext
    if candidate.casefold() not in taken:
        return candidate
    index = 1
    while True:
        candidate = "%s%d%s" % (base, index, ext)
        if candidate.casefold() not in taken:
            return candidate
        index += 1
        if index > 100000:
            raise RuntimeError("не удалось подобрать свободное имя файла")


def _local_asset_names() -> set:
    if not os.path.isdir(ASSETS_DIR):
        return set()
    names = set()
    try:
        for name in os.listdir(ASSETS_DIR):
            if os.path.isfile(os.path.join(ASSETS_DIR, name)) or os.path.islink(os.path.join(ASSETS_DIR, name)):
                names.add(name)
    except OSError:
        return set()
    return names


def _write_asset_bytes(name: str, content: bytes) -> str:
    base = _assets_base()
    os.makedirs(base, exist_ok=True)
    target = os.path.join(base, name)
    if os.path.commonpath([base, target]) != base:
        raise ValueError("Недопустимое имя файла")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags, 0o644)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
    except Exception:
        try:
            os.unlink(target)
        except OSError:
            pass
        raise
    return target


def _directus_headers(write: bool = False) -> dict:
    headers = {"Accept": "application/json", "User-Agent": "jnn-gallery/2"}
    token = (DIRECTUS_TOKEN or "").strip()
    if write and not token:
        raise _DirectusWriteError(
            503,
            "Directus: не задан JNN_DIRECTUS_TOKEN. Управление медиатекой доступно только на сервере с токеном.",
        )
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def _directus_error_detail(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace").strip()
    try:
        payload = json.loads(text)
        errors = payload.get("errors") or []
        if errors and isinstance(errors[0], dict):
            return str(errors[0].get("message") or text)
    except (TypeError, ValueError):
        pass
    return text[:400] or "Ошибка Directus"


def _directus_request(method: str, path: str, payload=None, timeout: int = DIRECTUS_WRITE_TIMEOUT, write: bool = False):
    headers = _directus_headers(write=write)
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        DIRECTUS_API.rstrip("/") + path,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = _directus_error_detail(exc.read())
        raise _DirectusWriteError(exc.code, detail)
    except Exception as exc:
        raise _DirectusWriteError(503, "Directus недоступен: " + str(exc))
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise _DirectusWriteError(502, "Directus вернул некорректный JSON")


def _directus_file_info(file_id: str) -> dict:
    uid = _media_id(file_id)
    data = _directus_request(
        "GET",
        "/files/" + uid + "?fields=id,filename_download,type,filesize",
        write=False,
    )
    item = data.get("data") if isinstance(data, dict) else None
    if not isinstance(item, dict):
        raise _DirectusWriteError(404, "Файл медиатеки не найден")
    return {
        "id": item.get("id") or uid,
        "name": item.get("filename_download") or uid,
        "type": item.get("type") or "",
        "size": item.get("filesize") or 0,
    }


def _directus_file_rows(fields: str, sort: str = "") -> list:
    """Читает все файлы Directus страницами.

    Не полагаемся на ``limit=5000``: в Directus лимит может быть ограничен
    настройкой сервера. Страница по 100 записей работает при любом лимите.
    """
    rows = []
    offset = 0
    page = 100
    while True:
        params = {"limit": page, "offset": offset, "fields": fields}
        if sort:
            params["sort"] = sort
        query = urllib.parse.urlencode(params)
        data = _directus_request("GET", "/files?" + query, write=False)
        batch = data.get("data") if isinstance(data, dict) else None
        if not isinstance(batch, list):
            raise _DirectusWriteError(503, "Directus недоступен: не удалось прочитать файлы")
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
        if offset > 100000:
            raise _DirectusWriteError(503, "Directus: слишком много файлов для проверки")
    return rows


def _directus_existing_names() -> set:
    rows = _directus_file_rows("filename_download")
    return {str(item.get("filename_download") or "") for item in rows if item.get("filename_download")}


def _directus_upload_media(filename: str, content: bytes, content_type: str = "") -> str:
    _directus_headers(write=True)
    boundary = "----jnn" + uuid.uuid4().hex
    ctype = (content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream").split(";")[0]
    safe = _safe_name(filename) or ("upload" + _auto_extension(filename))
    parts = [
        b"--" + boundary.encode("ascii") + b"\r\n",
        b'Content-Disposition: form-data; name="file"; filename="' + safe.encode("utf-8") + b'"\r\n',
        b"Content-Type: " + ctype.encode("ascii", "replace") + b"\r\n\r\n",
        content,
        b"\r\n--" + boundary.encode("ascii") + b"--\r\n",
    ]
    body = b"".join(parts)
    headers = _directus_headers(write=True)
    headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    req = urllib.request.Request(
        DIRECTUS_API.rstrip("/") + "/files",
        data=body,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=DIRECTUS_WRITE_TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise _DirectusWriteError(exc.code, _directus_error_detail(exc.read()))
    except Exception as exc:
        raise _DirectusWriteError(503, "Directus недоступен: " + str(exc))
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise _DirectusWriteError(502, "Directus вернул некорректный JSON")
    uid = str((data.get("data") or {}).get("id") or "")
    if not uid:
        raise _DirectusWriteError(502, "Directus не вернул id загруженного файла")
    return uid


def _directus_patch_name(file_id: str, name: str) -> dict:
    uid = _media_id(file_id)
    data = _directus_request("PATCH", "/files/" + uid, {"filename_download": name}, write=True)
    return data.get("data") if isinstance(data, dict) else {}


def _directus_delete_file(file_id: str) -> None:
    uid = _media_id(file_id)
    _directus_request("DELETE", "/files/" + uid, write=True)


def _directus_product_file_sort(product_id: str) -> int:
    """Следующий ``sort`` для галереи товара.

    Нельзя оставлять поле пустым: витрина приводит NULL к 0 и новое фото
    становится главным. Читаем текущие значения и ставим новое фото в конец.
    """
    rows = []
    offset = 0
    page = 100
    while True:
        query = urllib.parse.urlencode({
            "filter[products_id][_eq]": str(product_id),
            "fields": "sort",
            "limit": page,
            "offset": offset,
        })
        data = _directus_request("GET", "/items/products_files?" + query, write=False)
        batch = data.get("data") if isinstance(data, dict) else None
        if not isinstance(batch, list):
            raise _DirectusWriteError(503, "Directus: не удалось прочитать порядок фото товара")
        rows.extend(batch)
        if len(batch) < page:
            break
        offset += page
        if offset > 100000:
            raise _DirectusWriteError(503, "Directus: слишком много фото у товара")
    maximum = 0
    for row in rows:
        try:
            maximum = max(maximum, int(row.get("sort") or 0))
        except (TypeError, ValueError):
            continue
    return maximum + 1


def _directus_attach_product(product_id: str, file_id: str) -> None:
    _directus_request(
        "POST",
        "/items/products_files",
        {
            "products_id": product_id,
            "directus_files_id": file_id,
            "sort": _directus_product_file_sort(product_id),
        },
        write=True,
    )


def _product_catalog(records) -> List[dict]:
    items = []
    seen = set()
    for p in records or []:
        pid = str(p.get("id") or "")
        key = pid or str(p.get("slug") or p.get("name") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        items.append({
            "id": p.get("id") or "",
            "slug": p.get("slug") or "",
            "name": p.get("name") or "",
            "label": p.get("label") or p.get("name") or p.get("slug") or pid,
        })
    return items


def _find_product(records, value: str):
    needle = str(value or "").strip().casefold()
    if not needle:
        return None
    for p in records or []:
        if needle in {
            str(p.get("id") or "").casefold(),
            str(p.get("slug") or "").casefold(),
            str(p.get("name") or "").casefold(),
        }:
            return p
    return None


def _git_tracked_assets():
    """Имена файлов в assets/, которые отслеживаются Git.

    None означает, что проверка невозможна: в этом случае удаление
    блокируется, чтобы деплой не вернул файл из репозитория.
    """
    root = os.path.dirname(ASSETS_DIR)
    try:
        proc = subprocess.run(
            ["git", "-C", root, "ls-files", "-z", "--", "assets"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    tracked = set()
    prefix = "assets/"
    for raw in proc.stdout.decode("utf-8", "replace").split("\0"):
        if raw.startswith(prefix):
            tracked.add(raw[len(prefix):])
    return tracked


def _git_tracked(name: str):
    """True/False для конкретного файла, None — если Git недоступен."""
    root = os.path.dirname(ASSETS_DIR)
    rel = "assets/" + name
    try:
        proc = subprocess.run(
            ["git", "-C", root, "ls-files", "--error-unmatch", "--", rel],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


def _sha256(path: str) -> str:
    """sha256 файла с кэшем по (путь, размер, mtime), чтобы не хэшировать всё на каждый запрос."""
    try:
        st = os.stat(path)
    except OSError:
        return ""
    cached = _HASH_CACHE.get(path)
    if cached and cached[0] == st.st_size and cached[1] == int(st.st_mtime):
        return cached[2]
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    digest = h.hexdigest()
    _HASH_CACHE[path] = (st.st_size, int(st.st_mtime), digest)
    return digest


def _uploaded_ms(value) -> int:
    """uploaded_on из Directus (ISO, обычно UTC) -> миллисекунды."""
    if not value:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0


def _directus_images():
    """Изображения из медиатеки Directus. None — если Directus недоступен."""
    fields = "id,filename_download,filesize,type,filename_disk,uploaded_on"
    try:
        rows = _directus_file_rows(fields, "-uploaded_on,id")
    except Exception:
        return None
    out = []
    for f in rows:
        mime = (f.get("type") or "").lower()
        name = f.get("filename_download") or ""
        if not mime.startswith("image/") and os.path.splitext(name)[1].lower() not in GALLERY_EXTS:
            continue
        disk = os.path.basename(f.get("filename_disk") or "")
        path = os.path.join(DIRECTUS_UPLOADS, disk) if disk else ""
        out.append({
            "id": f.get("id") or "",
            "name": f.get("filename_download") or (f.get("id") or ""),
            "size": f.get("filesize") or 0,
            "mtime": _uploaded_ms(f.get("uploaded_on")),
            "url": "/assets/" + (f.get("id") or ""),
            "hash": _sha256(path) if path else "",
        })
    return out


@app.get("/gallery-api/list")
async def gallery_list():
    def build():
        items = []
        disk_by_hash = {}
        folders_data, folders_error = _load_folders()
        tracked = _git_tracked_assets()
        if os.path.isdir(ASSETS_DIR):
            for f in sorted(os.listdir(ASSETS_DIR)):
                p = os.path.join(ASSETS_DIR, f)
                if not os.path.isfile(p):
                    continue
                if os.path.splitext(f)[1].lower() not in GALLERY_EXTS:
                    continue
                is_link = os.path.islink(p)
                if is_link:
                    st = os.lstat(p)
                    h = ""
                else:
                    st = os.stat(p)
                    h = _sha256(p)
                is_tracked = (f in tracked) if tracked is not None else None
                item = {
                    "name": f,
                    "size": st.st_size,
                    "mtime": int(st.st_mtime * 1000),
                    "url": _asset_url(f),
                    "source": "disk",
                    "git_tracked": is_tracked,
                    "symlink": is_link,
                    "deletable": (is_tracked is False and not is_link),
                    "can_force": is_tracked is not None,
                    "folder_id": _folder_assignment(folders_data, "local", f),
                }
                items.append(item)
                if h:
                    disk_by_hash.setdefault(h, item)
        raw = _directus_images()
        media = []
        media_by_hash = {}
        media_writable = bool((DIRECTUS_TOKEN or "").strip())
        for d in raw or []:
            if d["hash"] and d["hash"] in disk_by_hash:
                # та же фотография уже есть на диске: одна карточка, помечаем копию в медиатеке
                twin = disk_by_hash[d["hash"]]
                twin["in_media"] = True
                twin["media_id"] = d["id"]
                continue
            if d["hash"] and d["hash"] in media_by_hash:
                kept = media_by_hash[d["hash"]]
                kept["dup"] = kept.get("dup", 0) + 1
                continue
            item = {
                "id": d["id"],
                "name": d["name"],
                "size": d["size"],
                "mtime": d["mtime"],
                "url": d["url"],
                "source": "directus",
                "deletable": media_writable,
                "can_force": media_writable,
                "folder_id": _folder_assignment(folders_data, "directus", d["id"]),
            }
            if d["hash"]:
                media_by_hash[d["hash"]] = item
            media.append(item)
        product_records, product_error = _directus_product_records()
        for item in items:
            item["products"] = _product_refs(
                product_records,
                item.get("name", ""),
                item.get("media_id", ""),
            )
        for item in media:
            item["products"] = _product_refs(
                product_records,
                item.get("id", ""),
                item.get("name", ""),
            )
        return {
            "count": len(items),
            "site_origin": SITE_ORIGIN,
            "files": items,
            "directus": media,
            "media_ok": raw is not None,
            "media_writable": media_writable,
            "products_ok": product_error is None,
            "products_error": product_error or "",
            "product_catalog": _product_catalog(product_records),
            "folders": folders_data.get("folders", []),
            "folders_ok": folders_error is None,
            "folders_error": folders_error or "",
            "total": len(items) + len(media),
        }

    return await run_in_threadpool(build)


@app.post("/gallery-api/upload")
async def gallery_upload(
    files: List[UploadFile] = File(...),
    folder_id: str = Form(""),
):
    folder_id = (folder_id or "").strip()
    if folder_id:
        try:
            folders_data = _folders_strict()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="Папки недоступны: " + str(exc))
        if folder_id not in _folder_ids(folders_data):
            raise HTTPException(status_code=400, detail="Папка не найдена")
    os.makedirs(ASSETS_DIR, exist_ok=True)
    uploaded, skipped, errors = [], [], []
    for f in files:
        name = _safe_name(f.filename)
        ext = os.path.splitext(name)[1].lower()
        if not name or ext not in GALLERY_EXTS:
            errors.append({"name": f.filename, "reason": "формат не поддерживается (нужен jpg, png, webp, avif, gif, svg)"})
            continue
        target = os.path.join(ASSETS_DIR, name)
        if os.path.islink(target):
            errors.append({"name": name, "reason": "символические ссылки не поддерживаются"})
            continue
        if os.path.exists(target):
            skipped.append({"name": name, "reason": "файл с таким именем уже есть"})
            continue
        try:
            content = await f.read()
        except Exception as e:
            errors.append({"name": name, "reason": "не удалось прочитать файл: " + str(e)})
            continue
        if not content:
            errors.append({"name": name, "reason": "пустой файл"})
            continue
        if len(content) > GALLERY_MAX_FILE:
            errors.append({
                "name": name,
                "reason": "файл больше 50 МБ (%.1f МБ)" % (len(content) / 1048576.0),
            })
            continue
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            # O_EXCL закрывает гонку между os.path.exists() и записью:
            # чужой файл/симлинк не будет перезаписан.
            fd = os.open(target, flags, 0o644)
        except FileExistsError:
            skipped.append({"name": name, "reason": "файл с таким именем уже есть"})
            continue
        except OSError as e:
            errors.append({"name": name, "reason": str(e)})
            continue
        try:
            with os.fdopen(fd, "wb") as buf:
                buf.write(content)
            if folder_id:
                _set_folder_assignment("local", name, folder_id)
            uploaded.append({
                "name": name,
                "url": _asset_url(name),
                "size": len(content),
                "folder_id": folder_id,
            })
        except HTTPException:
            raise
        except Exception as e:
            errors.append({"name": name, "reason": str(e)})
            try:
                os.unlink(target)
            except OSError:
                pass
    return {"uploaded": uploaded, "skipped": skipped, "errors": errors}


@app.get("/gallery-api/folders")
async def gallery_folders():
    data, error = _load_folders()
    return {
        "ok": error is None,
        "folders": data.get("folders", []),
        "error": error or "",
        "files": data.get("files", {}),
    }


@app.post("/gallery-api/folders")
async def gallery_folder_create(payload: dict = Body(...), ):
    try:
        name = _valid_folder_name(payload.get("name"))
        folder = _create_folder(name, str(payload.get("parent") or "").strip())
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Папки недоступны: " + str(exc))
    return {"ok": True, "folder": folder}


@app.post("/gallery-api/folders/move")
async def gallery_folder_move(payload: dict = Body(...), ):
    source = str(payload.get("source") or "").strip().lower()
    key = str(payload.get("key") or "").strip()
    folder_id = str(payload.get("folder_id") or "").strip()
    if source == "local":
        key = _existing_name(key)
        if not key or not os.path.lexists(os.path.join(_assets_base(), key)):
            raise HTTPException(status_code=404, detail="Файл не найден")
    elif source == "directus":
        try:
            key = _media_id(key)
            _directus_file_info(key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except _DirectusWriteError as exc:
            raise HTTPException(status_code=exc.status if exc.status in (404, 503) else 502, detail=exc.detail)
    else:
        raise HTTPException(status_code=400, detail="Источник должен быть local или directus")
    try:
        _move_folder_assignment(source, key, folder_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Папки недоступны: " + str(exc))
    return {"ok": True, "source": source, "key": key, "folder_id": folder_id}


@app.post("/gallery-api/upload-product")
async def gallery_upload_product(
    file: UploadFile = File(...),
    product: str = Form(""),
    target: str = Form("directus"),
    attach: bool = Form(False),
    folder_id: str = Form(""),
):
    """Загрузка фото товара с SEO-именем ``slug.jpg`` / ``slug1.jpg``.

    Directus — основной target. Локальный target оставлен для legacy-карточек,
    но не привязывает файл к товару (для этого нужен Directus file id).
    """
    target = (target or "directus").strip().lower()
    if target not in ("directus", "local"):
        raise HTTPException(status_code=400, detail="target должен быть directus или local")
    if target == "local" and attach:
        raise HTTPException(status_code=400, detail="Локальный файл нельзя привязать к товару Directus")
    folder_id = (folder_id or "").strip()
    if folder_id:
        try:
            folders_data = _folders_strict()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="Папки недоступны: " + str(exc))
        if folder_id not in _folder_ids(folders_data):
            raise HTTPException(status_code=400, detail="Папка не найдена")

    original = _safe_name(file.filename)
    ext = os.path.splitext(original)[1].lower()
    if not original or ext not in GALLERY_EXTS:
        raise HTTPException(status_code=400, detail="Формат не поддерживается (нужен jpg, png, webp, avif, gif, svg)")
    try:
        content = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Не удалось прочитать файл: " + str(exc))
    if not content:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(content) > GALLERY_MAX_FILE:
        raise HTTPException(status_code=413, detail="Файл больше 50 МБ")

    records, product_error = await run_in_threadpool(_directus_product_records)
    if product_error:
        raise HTTPException(status_code=503, detail="Не удалось проверить товар: " + product_error)
    record = _find_product(records, product)
    if not record:
        raise HTTPException(status_code=404, detail="Товар не найден")
    slug = record.get("slug") or record.get("name") or record.get("id")

    try:
        existing = await run_in_threadpool(_local_asset_names)
        existing |= await run_in_threadpool(_directus_existing_names)
    except _DirectusWriteError as exc:
        raise HTTPException(status_code=exc.status if exc.status in (404, 503) else 502, detail=exc.detail)
    name = _next_auto_name(slug, original, existing)

    if target == "directus":
        try:
            file_id = await run_in_threadpool(
                _directus_upload_media, name, content, file.content_type or ""
            )
        except _DirectusWriteError as exc:
            raise HTTPException(status_code=exc.status if exc.status in (401, 403, 503) else 502, detail=exc.detail)
        try:
            await run_in_threadpool(_directus_patch_name, file_id, name)
            if attach:
                await run_in_threadpool(_directus_attach_product, str(record.get("id") or ""), file_id)
        except _DirectusWriteError as exc:
            # Не оставляем «полузагруженный» файл, если не удалось задать имя/связь.
            try:
                await run_in_threadpool(_directus_delete_file, file_id)
            except Exception:
                pass
            raise HTTPException(status_code=exc.status if exc.status in (401, 403, 409, 503) else 502, detail=exc.detail)
        if folder_id:
            try:
                await run_in_threadpool(_set_folder_assignment, "directus", file_id, folder_id)
            except Exception as exc:
                raise HTTPException(status_code=500, detail="Файл загружен, но папка не сохранена: " + str(exc))
        return {
            "ok": True,
            "target": "directus",
            "id": file_id,
            "name": name,
            "url": "/assets/" + file_id,
            "product": {"id": record.get("id") or "", "slug": record.get("slug") or "", "name": record.get("name") or ""},
            "attached": bool(attach),
            "folder_id": folder_id,
            "auto_named": True,
        }

    # local: O_EXCL, при гонке подбираем следующий суффикс.
    for _ in range(20):
        try:
            await run_in_threadpool(_write_asset_bytes, name, content)
            break
        except FileExistsError:
            existing.add(name)
            name = _next_auto_name(slug, original, existing)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Не удалось сохранить файл: " + str(exc))
    else:
        raise HTTPException(status_code=409, detail="Не удалось подобрать свободное имя файла")
    if folder_id:
        try:
            await run_in_threadpool(_set_folder_assignment, "local", name, folder_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Файл сохранён, но папка не записана: " + str(exc))
    return {
        "ok": True,
        "target": "local",
        "name": name,
        "url": _asset_url(name),
        "product": {"id": record.get("id") or "", "slug": record.get("slug") or "", "name": record.get("name") or ""},
        "attached": False,
        "folder_id": folder_id,
        "auto_named": True,
    }


@app.delete("/gallery-api/delete")
@app.post("/gallery-api/delete")
async def gallery_delete(
    file: str = "",
    force: bool = False,
):
    name = _existing_name(file)
    if not name:
        raise HTTPException(status_code=400, detail="Не указано имя файла")
    base = _assets_base()
    target = os.path.join(base, name)
    if not os.path.lexists(target):
        raise HTTPException(status_code=404, detail="Файл не найден")
    is_link = os.path.islink(target)
    if is_link and not force:
        raise HTTPException(status_code=400, detail="Символические ссылки не поддерживаются")
    if not is_link and not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="Файл не найден")
    try:
        original = os.lstat(target) if is_link else os.stat(target)
    except OSError:
        raise HTTPException(status_code=404, detail="Файл не найден")

    # Проверка обязательна на бэкенде, а не только в интерфейсе.
    # force не отключает проверку: он лишь разрешает продолжить после
    # предупреждения и staging-удаления tracked-файла через git rm.
    report = await run_in_threadpool(_usage_report, name)
    if not report["available"]:
        return JSONResponse(status_code=503, content={
            "ok": False,
            "file": name,
            "reason": "usage_unavailable",
            "can_force": False,
            "detail": "Не удалось проверить использование файла. Удаление запрещено.",
        })
    if report["in_use"] and not force:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "file": name,
            "reason": "in_use",
            "in_use": True,
            "products": report["products"],
            "files": report["files"],
            "deletable": False,
            "can_force": True,
            "force_required": True,
            "detail": "Файл используется: " + _usage_list_text(report),
        })

    # Удалённый из рабочего дерева tracked-файл вернёт ближайший git pull.
    tracked = await run_in_threadpool(_git_tracked, name)
    if tracked is None:
        return JSONResponse(status_code=503, content={
            "ok": False,
            "file": name,
            "reason": "git_unavailable",
            "can_force": False,
            "detail": "Не удалось проверить состояние Git. Удаление запрещено, чтобы деплой не вернул файл.",
        })
    if tracked and not force:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "file": name,
            "reason": "git_tracked",
            "git_tracked": True,
            "deletable": False,
            "can_force": True,
            "force_required": True,
            "detail": "Файл отслеживается Git. Принудительное удаление выполнит git rm; затем нужен commit, иначе деплой будет заблокирован.",
        })

    try:
        current = os.lstat(target) if is_link else os.stat(target)
    except OSError:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "file": name,
            "reason": "file_changed",
            "detail": "Файл изменился во время проверки. Повторите удаление.",
        })
    if is_link != os.path.islink(target) or (
        original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns
    ) != (
        current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns
    ):
        return JSONResponse(status_code=409, content={
            "ok": False,
            "file": name,
            "reason": "file_changed",
            "detail": "Файл изменился во время проверки. Повторите удаление.",
        })

    if tracked:
        ok, error = await run_in_threadpool(_git_remove_tracked, name)
        if not ok:
            raise HTTPException(status_code=500, detail="git rm не выполнен: " + error)
    else:
        try:
            if is_link:
                os.unlink(target)
            else:
                os.remove(target)
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Не удалось удалить файл: " + str(exc))
    _drop_folder_assignment("local", name)
    return {
        "deleted": name,
        "forced": bool(force and (report["in_use"] or tracked or is_link)),
        "git_staged": bool(tracked),
        "git_commit_required": bool(tracked),
    }


def _media_tokens(values):
    """Точные токены media-полей: пути, basename, UUID, URL без query.

    Сравнение только на равенство. Это важно для коротких имён вроде
    ``1.jpg``: подстрока внутри ``letuchka_1.jpg`` не должна давать
    ложную привязку к чужому товару.
    """
    tokens = set()

    def add_text(raw):
        raw = (raw or "").strip()
        if not raw:
            return
        parts = {raw}
        for part in raw.split(","):
            part = part.strip()
            if part:
                parts.add(part)
        for part in list(parts):
            for text in (part, urllib.parse.unquote(part)):
                text = text.strip()
                if not text:
                    continue
                tokens.add(text)
                parsed = urllib.parse.urlsplit(text)
                path = parsed.path or text
                tokens.add(path)
                base = path.rsplit("/", 1)[-1]
                base = base.rsplit("\\", 1)[-1]
                if base:
                    tokens.add(base)

    def walk(value):
        if isinstance(value, str):
            add_text(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(values)
    tokens.discard("")
    tokens.discard("/")
    return tokens


def _directus_product_records():
    """Возвращает записи товаров с media-полями для проверки привязок.

    Запрос один раз используется и для usage-check, и для карточек галереи.
    Ошибка не маскируется: без полной проверки удаление/переименование
    должны быть запрещены.
    """
    try:
        def pull_all(fields):
            rows = []
            offset = 0
            page = 100
            while True:
                url = (
                    DIRECTUS_API
                    + "/items/products?fields=" + fields
                    + "&sort=id&limit=" + str(page)
                    + "&offset=" + str(offset)
                )
                try:
                    # Без токена оставляем простой URL: публичное чтение работает
                    # и на старых инсталляциях, где тесты/прокси ждут строку.
                    request = (
                        urllib.request.Request(url, headers=_directus_headers(write=False))
                        if (DIRECTUS_TOKEN or "").strip()
                        else url
                    )
                    with urllib.request.urlopen(request, timeout=5) as r:
                        data = json.load(r)
                except urllib.error.HTTPError as exc:
                    # 400/422 — скорее всего, поле отсутствует в этой схеме.
                    # 5xx/таймаут должны остаться ошибкой, а не fallback.
                    if exc.code in (400, 422):
                        raise _DirectusFieldError()
                    raise
                chunk = data.get("data") or []
                rows.extend(chunk)
                if len(chunk) < page:
                    break
                offset += page
                if offset >= 10000:
                    raise RuntimeError("слишком много товаров для проверки")
            return rows

        def pull_first(variants):
            last = None
            for fields in variants:
                try:
                    return pull_all(fields)
                except _DirectusFieldError as exc:
                    last = exc
            raise last or RuntimeError("нет подходящего набора полей Directus")

        ids_variants = [
            ("id,slug,name,image,gallery_urls,"
             "gallery.id,gallery.directus_files_id,"
             "gallery_files.id,gallery_files.directus_files_id"),
            ("id,slug,name,image,gallery_urls,"
             "gallery.id,gallery.directus_files_id"),
            ("id,slug,name,image,gallery_urls,"
             "gallery_files.id,gallery_files.directus_files_id"),
            "name,image,gallery_urls,gallery",
            "name,image,gallery_urls,gallery_files",
        ]
        names_variants = [
            ("id,slug,name,image.filename_download,gallery_urls,"
             "gallery.directus_files_id.filename_download,"
             "gallery_files.directus_files_id.filename_download"),
            ("id,slug,name,image.filename_download,gallery_urls,"
             "gallery.directus_files_id.filename_download"),
            ("id,slug,name,image.filename_download,gallery_urls,"
             "gallery_files.directus_files_id.filename_download"),
            "name,image.filename_download,gallery_urls,gallery",
            "name,image.filename_download,gallery_urls,gallery_files",
        ]

        ids_rows = pull_first(ids_variants)
        try:
            names_rows = pull_first(names_variants)
        except _DirectusFieldError:
            # Без имён нельзя безопасно проверять удаление по имени файла.
            return [], "Directus: не удалось проверить имена файлов"
        if ids_rows and not names_rows:
            return [], "Directus: не удалось проверить имена файлов"
    except Exception:
        return [], "Directus недоступен"

    merged = {}
    for p in ids_rows + names_rows:
        key = p.get("id") or p.get("name") or ""
        if not key:
            continue
        current = merged.setdefault(key, {
            "id": p.get("id") or "",
            "slug": p.get("slug") or "",
            "name": p.get("name") or "",
            "values": [],
        })
        current["values"].append(p)
        if not current["slug"] and p.get("slug"):
            current["slug"] = p.get("slug")
        if not current["name"] and p.get("name"):
            current["name"] = p.get("name")

    records = []
    for p in merged.values():
        # Только media-поля: name/slug/id товара не должны давать ложное совпадение.
        media_values = []
        for row in p["values"]:
            for key in ("image", "gallery", "gallery_files", "gallery_urls"):
                if key in row:
                    media_values.append(row[key])
        blob = json.dumps(media_values, ensure_ascii=False)
        label = p.get("name") or p.get("slug") or str(p.get("id") or "")
        slug = p.get("slug") or ""
        if label and slug and slug not in label:
            label = label + " [" + slug + "]"
        records.append({
            "id": p.get("id") or "",
            "slug": slug,
            "name": p.get("name") or "",
            "label": label,
            "blob": blob,
            "tokens": _media_tokens(media_values),
        })
    return records, None


def _record_tokens(p):
    tokens = p.get("tokens")
    if tokens is not None:
        return set(tokens)
    # Совместимость с записями, собранными вручную/старыми тестами.
    try:
        return _media_tokens(json.loads(p.get("blob") or "[]"))
    except (TypeError, ValueError):
        return set()


def _product_refs(records, *tokens):
    """Ссылки на товары, в media-полях которых есть точный токен."""
    candidates = {str(t) for t in tokens if t}
    if not candidates:
        return []
    refs = []
    seen = set()
    for p in records:
        if not candidates.intersection(_record_tokens(p)):
            continue
        key = str(p.get("id") or p.get("slug") or p.get("name") or "")
        if key in seen:
            continue
        seen.add(key)
        refs.append({
            "id": p.get("id") or "",
            "slug": p.get("slug") or "",
            "name": p.get("name") or "",
            "label": p.get("label") or "",
        })
    return refs


def _product_usage(name: str):
    """Ищет файл в товарах по точному имени/ID. Возвращает (товары, ошибка)."""
    records, error = _directus_product_records()
    if error:
        return [], error
    hits = []
    if not name:
        return hits, None
    for p in records:
        if name not in _record_tokens(p):
            continue
        if p["label"] and p["label"] not in hits:
            hits.append(p["label"])
    return hits, None


def _files_usage(name: str):
    hits = []
    errors = []
    root = os.path.dirname(ASSETS_DIR)
    manifest_path = os.path.abspath(GALLERY_FOLDERS_FILE)
    skip = {".git", "node_modules", "_scripts", "reports", "backups", "dist", "venv", "tests", ".pytest_cache"}
    # Границы не дают короткому 1.webp совпасть с women-hoodies1.webp.
    # Проверяем и сырое имя, и URL-экранированное (пробелы/юникод/#).
    patterns = [
        re.compile(r"(?<![A-Za-z0-9._-])" + re.escape(needle) + r"(?![A-Za-z0-9._-])")
        for needle in {name, urllib.parse.quote(name, safe="")}
        if needle
    ]

    def onerror(exc):
        errors.append(exc)

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            # Runtime-манифест папок содержит ключи «local:<имя>»; это не
            # ссылка сайта на файл, иначе любая папка блокировала бы удаление.
            if fn.startswith(".gallery_folders") or fn == ".gallery_key":
                continue
            fp = os.path.join(dirpath, fn)
            if os.path.abspath(fp) == manifest_path:
                continue
            if not fn.lower().endswith((".html", ".htm", ".txt", ".js", ".json", ".xml", ".css")):
                continue
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                    if any(p.search(content) for p in patterns):
                        hits.append(os.path.relpath(fp, root).replace("\\", "/"))
            except FileNotFoundError:
                # Файл исчез во время скана (деплой/checkout) — это не ссылка.
                continue
            except Exception as exc:
                errors.append(exc)
    if errors:
        raise RuntimeError("не удалось прочитать часть файлов сайта")
    return hits


def _usage_list_text(report: dict) -> str:
    parts = []
    if report.get("products"):
        parts.append("товары: " + ", ".join(report["products"]))
    if report.get("files"):
        parts.append("файлы: " + ", ".join(report["files"][:6]))
    return "; ".join(parts) if parts else "активная связь"


def _usage_report(name: str, file_id: str = ""):
    """Единая проверка для usage-check и delete. Fail-closed при ошибке Directus."""
    needle = file_id or name
    products, error = _product_usage(needle)
    if error:
        return {
            "available": False,
            "error": error,
            "products": [],
            "files": [],
            "in_use": None,
        }
    try:
        files = _files_usage(needle)
    except Exception:
        return {
            "available": False,
            "error": "Не удалось проверить ссылки на сайте",
            "products": [],
            "files": [],
            "in_use": None,
        }
    return {
        "available": True,
        "error": "",
        "products": products,
        "files": files,
        "in_use": bool(products or files),
    }


def _media_usage_report(file_id: str, media_name: str = ""):
    """Проверка использования файла Directus по id и (если есть) имени."""
    products, error = _product_usage(file_id)
    if error:
        return {"available": False, "error": error, "products": [], "files": [], "in_use": None}
    if media_name and media_name != file_id:
        extra, extra_error = _product_usage(media_name)
        if extra_error:
            return {"available": False, "error": extra_error, "products": [], "files": [], "in_use": None}
        for label in extra:
            if label not in products:
                products.append(label)
    try:
        files = _files_usage(file_id)
        if media_name and media_name != file_id:
            for path in _files_usage(media_name):
                if path not in files:
                    files.append(path)
    except Exception:
        return {
            "available": False,
            "error": "Не удалось проверить ссылки на сайте",
            "products": [],
            "files": [],
            "in_use": None,
        }
    return {
        "available": True,
        "error": "",
        "products": products,
        "files": files,
        "in_use": bool(products or files),
    }


@app.get("/gallery-api/usage")
async def gallery_usage(file: str = "", id: str = "", ):
    if id:
        try:
            uid = _media_id(id)
            info = await run_in_threadpool(_directus_file_info, uid)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except _DirectusWriteError as exc:
            raise HTTPException(status_code=exc.status if exc.status in (404, 503) else 502, detail=exc.detail)
        report = await run_in_threadpool(_media_usage_report, uid, info.get("name", ""))
        return {
            "file": uid,
            "name": info.get("name", ""),
            "available": report["available"],
            "error": report["error"],
            "products": report["products"],
            "files": report["files"],
            "in_use": bool(report["in_use"]),
            "deletable": bool((DIRECTUS_TOKEN or "").strip()),
            "can_force": bool((DIRECTUS_TOKEN or "").strip()),
        }
    name = _existing_name(file)
    if not name:
        raise HTTPException(status_code=400, detail="Не указано имя файла")
    report = await run_in_threadpool(_usage_report, name)
    return {
        "file": name,
        "available": report["available"],
        "error": report["error"],
        "products": report["products"],
        "files": report["files"],
        "in_use": bool(report["in_use"]),
    }


@app.get("/gallery-api/usage-check")
async def gallery_usage_check(file: str = "", id: str = "", ):
    """Проверка перед удалением/переименованием.

    Использование возвращает 409, но с ``can_force: true``: UI показывает
    предупреждение и может подтвердить принудительное действие. Git и symlink
    также можно обойти только явным force.
    """
    if id:
        try:
            uid = _media_id(id)
            info = await run_in_threadpool(_directus_file_info, uid)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except _DirectusWriteError as exc:
            raise HTTPException(status_code=exc.status if exc.status in (404, 503) else 502, detail=exc.detail)
        report = await run_in_threadpool(_media_usage_report, uid, info.get("name", ""))
        writable = bool((DIRECTUS_TOKEN or "").strip())
        if not report["available"]:
            return JSONResponse(status_code=503, content={
                "ok": False,
                "file": uid,
                "reason": "usage_unavailable",
                "can_force": False,
                "deletable": False,
                "detail": "Не удалось проверить использование файла. Действие запрещено.",
            })
        if report["in_use"]:
            detail = "Файл используется: " + _usage_list_text(report)
            if not writable:
                detail += ". Запись в Directus недоступна: не задан JNN_DIRECTUS_TOKEN."
            return JSONResponse(status_code=409, content={
                "ok": False,
                "file": uid,
                "name": info.get("name", ""),
                "reason": "in_use",
                "in_use": True,
                "products": report["products"],
                "files": report["files"],
                "deletable": writable,
                "can_force": writable,
                "force_required": True,
                "detail": detail,
            })
        return {
            "ok": True,
            "file": uid,
            "name": info.get("name", ""),
            "in_use": False,
            "products": report["products"],
            "files": report["files"],
            "deletable": writable,
            "can_force": writable,
            "reason": "directus_media" if writable else "directus_write_unavailable",
            "detail": (
                "Файл медиатеки можно переименовать или удалить; при использовании будет запрошено подтверждение."
                if writable else
                "Запись в Directus недоступна: не задан JNN_DIRECTUS_TOKEN."
            ),
        }

    name = _existing_name(file)
    if not name:
        raise HTTPException(status_code=400, detail="Не указано имя файла")
    base = _assets_base()
    target = os.path.join(base, name)
    if not os.path.lexists(target):
        raise HTTPException(status_code=404, detail="Файл не найден")
    is_link = os.path.islink(target)
    if not is_link and not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="Файл не найден")

    report = await run_in_threadpool(_usage_report, name)
    if not report["available"]:
        return JSONResponse(status_code=503, content={
            "ok": False,
            "file": name,
            "reason": "usage_unavailable",
            "can_force": False,
            "deletable": False,
            "detail": "Не удалось проверить использование файла. Действие запрещено.",
        })
    tracked = await run_in_threadpool(_git_tracked, name)
    can_force = tracked is not None
    if report["in_use"]:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "file": name,
            "reason": "in_use",
            "in_use": True,
            "products": report["products"],
            "files": report["files"],
            "deletable": False,
            "can_force": can_force,
            "force_required": True,
            "git_tracked": tracked,
            "symlink": is_link,
            "detail": "Файл используется: " + _usage_list_text(report),
        })
    if is_link:
        return {
            "ok": True,
            "file": name,
            "in_use": False,
            "products": report["products"],
            "files": report["files"],
            "deletable": False,
            "can_force": can_force,
            "git_tracked": tracked,
            "symlink": True,
            "reason": "symlink",
            "detail": "Символическая ссылка. Принудительное действие затронет только саму ссылку.",
        }
    if tracked is None:
        return {
            "ok": True,
            "file": name,
            "in_use": False,
            "products": report["products"],
            "files": report["files"],
            "deletable": False,
            "can_force": False,
            "git_tracked": None,
            "reason": "git_unavailable",
            "detail": "Не удалось проверить Git. Действие запрещено, чтобы деплой не вернул файл.",
        }
    if tracked:
        return {
            "ok": True,
            "file": name,
            "in_use": False,
            "products": report["products"],
            "files": report["files"],
            "deletable": False,
            "can_force": True,
            "git_tracked": True,
            "reason": "git_tracked",
            "detail": "Файл отслеживается Git. Принудительное действие выполнит git rm/git mv; затем нужен commit.",
        }
    return {
        "ok": True,
        "file": name,
        "in_use": False,
        "products": report["products"],
        "files": report["files"],
        "deletable": True,
        "can_force": True,
        "git_tracked": False,
        "reason": "",
        "detail": "Файл не используется и не отслеживается Git.",
    }


@app.post("/gallery-api/rename")
async def gallery_rename(payload: dict = Body(...), ):
    old = _existing_name(payload.get("old", ""))
    new = _existing_name(payload.get("new", ""))
    force = bool(payload.get("force"))
    if not old or not new:
        raise HTTPException(status_code=400, detail="Нужны оба имени файла")
    if old == new:
        raise HTTPException(status_code=400, detail="Новое имя совпадает со старым")
    if os.path.splitext(new)[1].lower() not in GALLERY_EXTS:
        new = new + os.path.splitext(old)[1].lower()
    base = _assets_base()
    src = os.path.join(base, old)
    dst = os.path.join(base, new)
    if not os.path.lexists(src):
        raise HTTPException(status_code=404, detail="Исходный файл не найден")
    is_link = os.path.islink(src)
    if is_link and not force:
        raise HTTPException(status_code=400, detail="Символические ссылки не поддерживаются")
    if not is_link and not os.path.isfile(src):
        raise HTTPException(status_code=404, detail="Исходный файл не найден")
    if os.path.lexists(dst):
        raise HTTPException(status_code=409, detail="Файл с таким именем уже существует")
    try:
        src_original = os.lstat(src) if is_link else os.stat(src)
    except OSError:
        raise HTTPException(status_code=404, detail="Исходный файл не найден")

    # Rename — это тоже удаление старого пути: проверяем использование и Git.
    report = await run_in_threadpool(_usage_report, old)
    if not report["available"]:
        return JSONResponse(status_code=503, content={
            "ok": False,
            "file": old,
            "reason": "usage_unavailable",
            "can_force": False,
            "detail": "Не удалось проверить использование файла. Переименование запрещено.",
        })
    if report["in_use"] and not force:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "file": old,
            "reason": "in_use",
            "products": report["products"],
            "files": report["files"],
            "can_force": True,
            "force_required": True,
            "detail": "Файл используется: " + _usage_list_text(report),
        })

    tracked = await run_in_threadpool(_git_tracked, old)
    if tracked is None:
        return JSONResponse(status_code=503, content={
            "ok": False,
            "file": old,
            "reason": "git_unavailable",
            "can_force": False,
            "detail": "Не удалось проверить состояние Git. Переименование запрещено.",
        })
    if tracked and not force:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "file": old,
            "reason": "git_tracked",
            "git_tracked": True,
            "can_force": True,
            "force_required": True,
            "detail": "Файл отслеживается Git. Принудительное переименование выполнит git mv; затем нужен commit.",
        })
    tracked_new = await run_in_threadpool(_git_tracked, new)
    if tracked_new is None:
        return JSONResponse(status_code=503, content={
            "ok": False,
            "file": new,
            "reason": "git_unavailable",
            "can_force": False,
            "detail": "Не удалось проверить состояние Git. Переименование запрещено.",
        })
    if tracked_new:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "file": new,
            "reason": "git_tracked",
            "detail": "Новое имя уже отслеживается Git. Переименование запрещено.",
        })

    # Не даём подменить src на symlink/другой файл во время проверок.
    if is_link != os.path.islink(src):
        raise HTTPException(status_code=409, detail="Исходный файл изменился во время проверки")
    try:
        src_current = os.lstat(src) if is_link else os.stat(src)
    except OSError:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "file": old,
            "reason": "file_changed",
            "detail": "Исходный файл изменился во время проверки. Повторите переименование.",
        })
    if (src_original.st_dev, src_original.st_ino, src_original.st_size, src_original.st_mtime_ns) != (
        src_current.st_dev, src_current.st_ino, src_current.st_size, src_current.st_mtime_ns
    ):
        return JSONResponse(status_code=409, content={
            "ok": False,
            "file": old,
            "reason": "file_changed",
            "detail": "Исходный файл изменился во время проверки. Повторите переименование.",
        })

    if tracked:
        ok, error = await run_in_threadpool(_git_move_tracked, old, new)
        if not ok:
            raise HTTPException(status_code=500, detail="git mv не выполнен: " + error)
    elif is_link:
        # Переименовываем саму ссылку, не следуя по ней.
        try:
            if os.name == "posix":
                os.link(src, dst, follow_symlinks=False)
                os.unlink(src)
            else:
                if os.path.lexists(dst):
                    raise FileExistsError(dst)
                os.rename(src, dst)
        except FileExistsError:
            raise HTTPException(status_code=409, detail="Файл с таким именем уже существует")
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Не удалось переименовать ссылку: " + str(exc))
    else:
        try:
            # link не перезаписывает существующий dst (в отличие от POSIX rename).
            if os.name == "posix":
                os.link(src, dst, follow_symlinks=False)
            else:
                os.link(src, dst)
        except FileExistsError:
            raise HTTPException(status_code=409, detail="Файл с таким именем уже существует")
        except OSError as exc:
            raise HTTPException(status_code=500, detail="Не удалось переименовать файл: " + str(exc))
        if os.path.islink(dst):
            try:
                os.unlink(dst)
            except OSError:
                pass
            raise HTTPException(status_code=409, detail="Исходный файл изменился во время проверки")
        try:
            os.unlink(src)
        except FileNotFoundError:
            pass
        except OSError as exc:
            if os.path.exists(src):
                try:
                    os.unlink(dst)
                except OSError:
                    pass
            raise HTTPException(status_code=500, detail="Не удалось удалить старое имя: " + str(exc))
    try:
        _rename_folder_assignment(old, new)
    except Exception:
        # Папка — необязательная метаданные; файл уже переименован.
        pass
    return {
        "old": old,
        "name": new,
        "url": _asset_url(new),
        "forced": bool(force and (report["in_use"] or tracked or is_link)),
        "git_staged": bool(tracked),
        "git_commit_required": bool(tracked),
    }


@app.post("/gallery-api/media/rename")
async def gallery_media_rename(payload: dict = Body(...), ):
    try:
        uid = _media_id(payload.get("id"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    new = _existing_name(payload.get("new", ""))
    force = bool(payload.get("force"))
    if not new:
        raise HTTPException(status_code=400, detail="Укажите новое имя файла")
    try:
        info = await run_in_threadpool(_directus_file_info, uid)
    except _DirectusWriteError as exc:
        raise HTTPException(status_code=exc.status if exc.status in (404, 503) else 502, detail=exc.detail)
    if os.path.splitext(new)[1].lower() not in GALLERY_EXTS:
        new += os.path.splitext(info.get("name", ""))[1].lower()
    if new == info.get("name"):
        raise HTTPException(status_code=400, detail="Новое имя совпадает со старым")
    report = await run_in_threadpool(_media_usage_report, uid, info.get("name", ""))
    if not report["available"]:
        return JSONResponse(status_code=503, content={
            "ok": False,
            "id": uid,
            "reason": "usage_unavailable",
            "can_force": False,
            "detail": "Не удалось проверить использование файла. Переименование запрещено.",
        })
    if report["in_use"] and not force:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "id": uid,
            "reason": "in_use",
            "products": report["products"],
            "files": report["files"],
            "can_force": bool((DIRECTUS_TOKEN or "").strip()),
            "force_required": True,
            "detail": "Файл используется: " + _usage_list_text(report),
        })
    if not (DIRECTUS_TOKEN or "").strip():
        raise HTTPException(status_code=503, detail="Directus: не задан JNN_DIRECTUS_TOKEN")
    try:
        await run_in_threadpool(_directus_patch_name, uid, new)
    except _DirectusWriteError as exc:
        raise HTTPException(status_code=exc.status if exc.status in (401, 403, 404, 409, 503) else 502, detail=exc.detail)
    return {
        "ok": True,
        "id": uid,
        "old": info.get("name", ""),
        "name": new,
        "url": "/assets/" + uid,
        "forced": bool(force and report["in_use"]),
    }


@app.post("/gallery-api/media/auto-name")
async def gallery_media_auto_name(payload: dict = Body(...), ):
    """Доводит имя уже загруженного в Directus файла до ``slug.jpg``.

    Нужен для файлов, загруженных через нативную админку Directus: перехватить
    такую загрузку без Directus-flow нельзя, но имя можно исправить одной кнопкой.
    """
    try:
        uid = _media_id(payload.get("id"))
        info = await run_in_threadpool(_directus_file_info, uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except _DirectusWriteError as exc:
        raise HTTPException(status_code=exc.status if exc.status in (404, 503) else 502, detail=exc.detail)
    records, product_error = await run_in_threadpool(_directus_product_records)
    if product_error:
        raise HTTPException(status_code=503, detail="Не удалось проверить товар: " + product_error)
    record = _find_product(records, str(payload.get("product") or ""))
    if not record:
        raise HTTPException(status_code=404, detail="Товар не найден")
    try:
        existing = await run_in_threadpool(_directus_existing_names)
    except _DirectusWriteError as exc:
        raise HTTPException(status_code=exc.status if exc.status in (404, 503) else 502, detail=exc.detail)
    existing.discard(info.get("name", ""))
    new = _next_auto_name(record.get("slug") or record.get("name") or record.get("id"), info.get("name", ""), existing)
    if new == info.get("name"):
        return {"ok": True, "id": uid, "name": new, "renamed": False}
    report = await run_in_threadpool(_media_usage_report, uid, info.get("name", ""))
    if not report["available"]:
        return JSONResponse(status_code=503, content={
            "ok": False, "id": uid, "reason": "usage_unavailable", "can_force": False,
            "detail": "Не удалось проверить использование файла. Переименование запрещено.",
        })
    if report["in_use"] and not bool(payload.get("force")):
        return JSONResponse(status_code=409, content={
            "ok": False, "id": uid, "reason": "in_use",
            "products": report["products"], "files": report["files"],
            "can_force": bool((DIRECTUS_TOKEN or "").strip()), "force_required": True,
            "detail": "Файл используется: " + _usage_list_text(report),
        })
    if not (DIRECTUS_TOKEN or "").strip():
        raise HTTPException(status_code=503, detail="Directus: не задан JNN_DIRECTUS_TOKEN")
    try:
        await run_in_threadpool(_directus_patch_name, uid, new)
    except _DirectusWriteError as exc:
        raise HTTPException(status_code=exc.status if exc.status in (401, 403, 404, 409, 503) else 502, detail=exc.detail)
    return {
        "ok": True, "id": uid, "old": info.get("name", ""), "name": new,
        "renamed": True, "forced": bool(report["in_use"]),
    }


@app.delete("/gallery-api/media/{file_id}")
async def gallery_media_delete(
    file_id: str,
    force: bool = False,
):
    try:
        uid = _media_id(file_id)
        info = await run_in_threadpool(_directus_file_info, uid)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except _DirectusWriteError as exc:
        raise HTTPException(status_code=exc.status if exc.status in (404, 503) else 502, detail=exc.detail)
    report = await run_in_threadpool(_media_usage_report, uid, info.get("name", ""))
    if not report["available"]:
        return JSONResponse(status_code=503, content={
            "ok": False,
            "id": uid,
            "reason": "usage_unavailable",
            "can_force": False,
            "detail": "Не удалось проверить использование файла. Удаление запрещено.",
        })
    if report["in_use"] and not force:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "id": uid,
            "name": info.get("name", ""),
            "reason": "in_use",
            "products": report["products"],
            "files": report["files"],
            "can_force": bool((DIRECTUS_TOKEN or "").strip()),
            "force_required": True,
            "detail": "Файл используется: " + _usage_list_text(report),
        })
    if not (DIRECTUS_TOKEN or "").strip():
        raise HTTPException(status_code=503, detail="Directus: не задан JNN_DIRECTUS_TOKEN")
    try:
        await run_in_threadpool(_directus_delete_file, uid)
    except _DirectusWriteError as exc:
        status = exc.status if exc.status in (401, 403, 404, 409, 503) else 502
        raise HTTPException(status_code=status, detail=exc.detail)
    _drop_folder_assignment("directus", uid)
    return {
        "ok": True,
        "deleted": uid,
        "name": info.get("name", ""),
        "forced": bool(force and report["in_use"]),
    }


def _batch_targets(payload: dict) -> list:
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="Не выбран ни один файл")
    if len(items) > 100:
        raise HTTPException(status_code=400, detail="За один раз можно обработать не более 100 файлов")
    targets = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Некорректный элемент списка")
        source = str(item.get("source") or "local").strip().lower()
        raw_key = item.get("key")
        if source == "local":
            key = _existing_name(raw_key)
        elif source == "directus":
            try:
                key = _media_id(raw_key)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            raise HTTPException(status_code=400, detail="Неизвестный источник файла")
        if not key:
            raise HTTPException(status_code=400, detail="Не указан файл")
        marker = (source, key)
        if marker in seen:
            continue
        seen.add(marker)
        targets.append((source, key))
    return targets


def _json_response_payload(response) -> tuple:
    if isinstance(response, JSONResponse):
        try:
            body = json.loads(response.body.decode("utf-8"))
        except Exception:
            body = {}
        return int(response.status_code), body
    return 200, response


@app.post("/gallery-api/batch/move")
async def gallery_batch_move(payload: dict = Body(...)):
    targets = _batch_targets(payload)
    folder_id = str(payload.get("folder_id") or "").strip()
    try:
        moved = await run_in_threadpool(_move_folder_assignments, targets, folder_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Папки недоступны: " + str(exc)) from exc
    return {"ok": True, "moved": moved, "folder_id": folder_id}


@app.post("/gallery-api/batch/delete")
async def gallery_batch_delete(payload: dict = Body(...)):
    targets = _batch_targets(payload)
    force = bool(payload.get("force"))

    # Сначала проверяем весь набор, чтобы не удалить половину и не упереться
    # в используемый файл. Проверки те же, что у одиночного удаления.
    checked = []
    blocked = []
    errors = []
    for source, key in targets:
        if source == "directus":
            result = await gallery_usage_check(id=key)
        else:
            result = await gallery_usage_check(file=key)
        status, body = _json_response_payload(result)
        body = dict(body or {})
        body.update({"source": source, "key": key})
        checked.append((source, key))

        reason = str(body.get("reason") or "")
        force_required = (
            status == 409
            or bool(body.get("force_required"))
            or (body.get("deletable") is False and body.get("can_force") is True)
        )
        if force_required:
            blocked.append(body)
            continue
        if status >= 400 or body.get("deletable") is not True:
            # git_unavailable/usage_unavailable приходят с HTTP 200, но
            # действие всё равно запрещено. Для UI это ошибка проверки, а не
            # повод показать force-подтверждение.
            error_status = status
            if error_status < 400:
                error_status = 503 if reason in ("git_unavailable", "usage_unavailable") else 400
            errors.append({"status": error_status, "item": body})
    if errors:
        return JSONResponse(status_code=503 if any(e["status"] == 503 for e in errors) else 400, content={
            "ok": False, "reason": "preflight_failed", "errors": errors, "blocked": blocked,
        })
    if blocked and not force:
        return JSONResponse(status_code=409, content={
            "ok": False, "reason": "force_required", "blocked": blocked,
            "can_force": any(bool(item.get("can_force")) for item in blocked),
            "detail": "Часть файлов используется, отслеживается Git или является ссылкой. Нужно подтверждение.",
        })
    if blocked and force and any(not bool(item.get("can_force")) for item in blocked):
        return JSONResponse(status_code=409, content={
            "ok": False, "reason": "force_unavailable", "blocked": blocked,
            "can_force": False,
            "detail": "Для части файлов принудительное действие недоступно: проверка Git или usage не пройдена.",
        })

    deleted = []
    failed = []
    for source, key in checked:
        try:
            if source == "directus":
                result = await gallery_media_delete(file_id=key, force=force)
            else:
                result = await gallery_delete(file=key, force=force)
            status, body = _json_response_payload(result)
        except HTTPException as exc:
            status, body = exc.status_code, {"detail": exc.detail}
        if status < 400:
            deleted.append({"source": source, "key": key, "result": body})
        else:
            failed.append({"source": source, "key": key, "status": status, "result": body})
    return {
        "ok": not failed,
        "deleted": deleted,
        "failed": failed,
        "git_commit_required": bool(any(
            item.get("result", {}).get("git_commit_required") for item in deleted
        )),
    }


@app.get("/gallery")
async def gallery_page():
    if not os.path.exists(GALLERY_HTML):
        raise HTTPException(status_code=404, detail="gallery.html не найден")
    return FileResponse(
        GALLERY_HTML,
        headers={
            "Cache-Control": "no-store",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        },
    )


if os.path.isdir(GALLERY_STATIC_DIR):
    app.mount("/gallery/static", StaticFiles(directory=GALLERY_STATIC_DIR), name="gallery-static")


# ---------------------------------------------------------------------------
# Публикация товаров: Directus -> страница + sitemap.xml + llms.txt
#
# Ручные вызовы под /gallery-api/* защищены админ-сессией Directus.
# Автоматический flow Directus ходит на отдельный /webhooks/directus/publish
# с секретом JNN_PUBLISH_WEBHOOK_SECRET (не с ключом галереи).
# ---------------------------------------------------------------------------
import admin.publish_product as _publish  # noqa: E402


async def _publish_payload(request: Request) -> dict:
    # Тело принимаем «как есть»: вебхук Directus может прислать JSON-строку внутри
    # JSON или нестандартный Content-Type — тогда разбираем вручную.
    raw = (await request.body()).decode("utf-8", "replace").strip()
    payload = None
    if raw:
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = None
    if not isinstance(payload, dict):
        _publish.log_event({"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                            "action": "webhook-parse", "raw": raw[:400]})
        payload = {}
    return payload


@app.get("/gallery-api/publish/status")
def publish_status():
    try:
        return _publish.status()
    except _publish.PublishError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/gallery-api/publish/log")
def publish_log(limit: int = 20):
    return {"ok": True, "log": _publish.read_log(limit)}


@app.post("/webhooks/directus/publish")
async def publish_webhook(request: Request):
    """Единственная точка для flow Directus; авторизация — отдельный секрет."""
    if not PUBLISH_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook-секрет не настроен")
    supplied = request.headers.get("x-webhook-secret") or ""
    if not supplied or not hmac.compare_digest(supplied, PUBLISH_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Неверный webhook-секрет")
    payload = await _publish_payload(request)
    try:
        return await run_in_threadpool(_publish.api_publish, payload)
    except _publish.PublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/gallery-api/publish")
async def publish_post(request: Request):
    payload = await _publish_payload(request)
    try:
        return await run_in_threadpool(_publish.api_publish, payload)
    except _publish.PublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/gallery-api/unpublish")
async def unpublish_post(payload: dict = Body(...)):
    try:
        return await run_in_threadpool(
            _publish.unpublish,
            str(payload.get("slug") or "").strip(),
            bool(payload.get("force")),
            bool(payload.get("dry")),
        )
    except _publish.PublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
