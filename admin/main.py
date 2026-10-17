import datetime, json, os, re, shutil, uuid
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Body, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="JNN Factory Enterprise Engine")
DATA_FILE = "/var/www/jnnfactory/admin/site_data.json"
ADMIN_HTML = "/var/www/jnnfactory/admin/index.html"
INDEX_FILE = "/var/www/jnnfactory/index.html"
ASSETS_DIR = "/var/www/jnnfactory/assets"

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
    ext = os.path.splitext(file.filename)[1].lower()
    allowed = (".jpg", ".jpeg", ".png", ".webp")
    if ext not in allowed:
        return {"error": "Only jpg/png/webp allowed"}
    target_dir = "/var/www/jnnfactory/assets/images"
    os.makedirs(target_dir, exist_ok=True)
    clean_name = file.filename.replace(" ", "_")
    target_path = os.path.join(target_dir, clean_name)
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
GALLERY_HTML = os.path.join(os.path.dirname(ASSETS_DIR), "gallery.html")


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
    if not key or key != actual:
        raise HTTPException(status_code=401, detail="Неверный ключ доступа")


def _safe_name(name: str) -> str:
    name = (name or "").strip().replace("\\", "/").split("/")[-1]
    name = name.replace(" ", "-")
    name = re.sub(r"[^\w.\-]", "", name, flags=re.UNICODE)
    return name.lstrip(".")


@app.get("/gallery-api/list")
async def gallery_list():
    items = []
    if os.path.isdir(ASSETS_DIR):
        for f in sorted(os.listdir(ASSETS_DIR)):
            p = os.path.join(ASSETS_DIR, f)
            if not os.path.isfile(p):
                continue
            if os.path.splitext(f)[1].lower() not in GALLERY_EXTS:
                continue
            st = os.stat(p)
            items.append({
                "name": f,
                "size": st.st_size,
                "mtime": int(st.st_mtime * 1000),
                "url": "/assets/" + f,
            })
    return {"count": len(items), "files": items}


@app.get("/gallery-api/key")
async def gallery_key_status():
    return {"configured": bool(_gallery_key())}


@app.post("/gallery-api/upload")
async def gallery_upload(files: List[UploadFile] = File(...), x_gallery_key: str = Header(default="")):
    _check_key(x_gallery_key)
    os.makedirs(ASSETS_DIR, exist_ok=True)
    uploaded, skipped, errors = [], [], []
    for f in files:
        name = _safe_name(f.filename)
        ext = os.path.splitext(name)[1].lower()
        if not name or ext not in GALLERY_EXTS:
            errors.append({"name": f.filename, "reason": "формат не поддерживается (нужен jpg, png, webp, avif, gif, svg)"})
            continue
        target = os.path.join(ASSETS_DIR, name)
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
        try:
            with open(target, "wb") as buf:
                buf.write(content)
            uploaded.append({"name": name, "url": "/assets/" + name, "size": len(content)})
        except Exception as e:
            errors.append({"name": name, "reason": str(e)})
    return {"uploaded": uploaded, "skipped": skipped, "errors": errors}


@app.delete("/gallery-api/delete")
@app.post("/gallery-api/delete")
async def gallery_delete(file: str = "", x_gallery_key: str = Header(default="")):
    _check_key(x_gallery_key)
    name = _safe_name(file)
    if not name:
        raise HTTPException(status_code=400, detail="Не указано имя файла")
    target = os.path.join(ASSETS_DIR, name)
    base = os.path.realpath(ASSETS_DIR)
    real = os.path.realpath(target)
    if not real.startswith(base + os.sep):
        raise HTTPException(status_code=400, detail="Недопустимое имя файла")
    if not os.path.isfile(real):
        raise HTTPException(status_code=404, detail="Файл не найден")
    os.remove(real)
    return {"deleted": name}


def _product_usage(name: str):
    """Ищет имя файла в товарах: главное фото (image), M2M-галерея (gallery)
    и старое текстовое поле gallery_urls."""
    hits = []
    try:
        import urllib.request
        base = "http://127.0.0.1:8055/items/products?limit=200&fields="

        def pull(fields):
            with urllib.request.urlopen(base + fields, timeout=5) as r:
                return json.load(r)

        try:
            data = pull("name,image,gallery_urls,gallery.directus_files_id.filename_download")
        except Exception:
            data = pull("name,image,gallery")
        for p in data.get("data", []):
            blob = json.dumps(
                [p.get("image"), p.get("gallery_urls"), p.get("gallery"), p.get("gallery_files")],
                ensure_ascii=False,
            )
            if name in blob:
                hits.append(p.get("name") or "")
    except Exception as e:
        hits.append("Directus недоступен: " + str(e))
    return hits


def _files_usage(name: str):
    hits = []
    root = os.path.dirname(ASSETS_DIR)
    skip = {".git", "node_modules", "_scripts", "reports", "backups", "assets", "dist", "venv"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            if not fn.lower().endswith((".html", ".txt", ".js")):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                    if name in fh.read():
                        hits.append(os.path.relpath(fp, root).replace("\\", "/"))
            except Exception:
                pass
    return hits


@app.get("/gallery-api/usage")
async def gallery_usage(file: str = ""):
    name = _safe_name(file)
    if not name:
        raise HTTPException(status_code=400, detail="Не указано имя файла")
    return {"file": name, "products": _product_usage(name), "files": _files_usage(name)}


@app.post("/gallery-api/rename")
async def gallery_rename(payload: dict = Body(...), x_gallery_key: str = Header(default="")):
    _check_key(x_gallery_key)
    old = _safe_name(payload.get("old", ""))
    new = _safe_name(payload.get("new", ""))
    if not old or not new:
        raise HTTPException(status_code=400, detail="Нужны оба имени файла")
    if os.path.splitext(new)[1].lower() not in GALLERY_EXTS:
        new = new + os.path.splitext(old)[1].lower()
    src = os.path.join(ASSETS_DIR, old)
    dst = os.path.join(ASSETS_DIR, new)
    if not os.path.isfile(src):
        raise HTTPException(status_code=404, detail="Исходный файл не найден")
    if os.path.exists(dst):
        raise HTTPException(status_code=409, detail="Файл с таким именем уже существует")
    os.rename(src, dst)
    return {"old": old, "name": new, "url": "/assets/" + new}


@app.get("/gallery")
async def gallery_page():
    if not os.path.exists(GALLERY_HTML):
        raise HTTPException(status_code=404, detail="gallery.html не найден")
    return FileResponse(GALLERY_HTML)


# ---------------------------------------------------------------------------
# Публикация товаров: Directus -> страница + sitemap.xml + llms.txt
# Тот же ключ, что у галереи (JNN_GALLERY_KEY или admin/.gallery_key).
# Вебхук Directus дергает POST /gallery-api/publish (nginx проксирует префикс).
# ---------------------------------------------------------------------------
import admin.publish_product as _publish  # noqa: E402


@app.get("/gallery-api/publish/status")
def publish_status():
    try:
        return _publish.status()
    except _publish.PublishError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/gallery-api/publish/log")
def publish_log(limit: int = 20):
    return {"ok": True, "log": _publish.read_log(limit)}


@app.post("/gallery-api/publish")
async def publish_post(request: Request, x_gallery_key: str = Header(default="")):
    _check_key(x_gallery_key)
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
    try:
        return _publish.api_publish(payload)
    except _publish.PublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/gallery-api/unpublish")
def unpublish_post(payload: dict = Body(...), x_gallery_key: str = Header(default="")):
    _check_key(x_gallery_key)
    try:
        return _publish.unpublish(
            str(payload.get("slug") or "").strip(),
            force=bool(payload.get("force")),
            dry=bool(payload.get("dry")),
        )
    except _publish.PublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
