import json, os, shutil
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="JNN Factory Enterprise Engine")
DATA_FILE = "/var/www/jnnfactory/admin/site_data.json"
ADMIN_HTML = "/var/www/jnnfactory/admin/index.html"
INDEX_FILE = "/var/www/jnnfactory/index.html"
ASSETS_DIR = "/var/www/jnnfactory/assets"

if os.path.exists(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

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
async def update_content(payload: dict):
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
async def upload_asset(file: UploadFile = File(...)):
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
async def edit_post():
    return {"status":"edit saved"}

@app.get("/settings")
async def get_settings():
    path = "/var/www/jnnfactory/admin/settings.json"
    if not os.path.exists(path):
        return {"site_name":"JNN Factory","email":"","logo":"","whatsapp":""}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

@app.post("/settings")
async def post_settings():
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
async def update_catalog(payload: dict):
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}
    data["products"] = payload.get("products", [])
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"status": "saved"}
