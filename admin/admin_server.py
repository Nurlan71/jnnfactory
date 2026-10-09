import os, json, subprocess
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DATA_DIR = "/var/www/jnnfactory"
BACKUP_DIR = os.path.join(DATA_DIR, "admin/backups")

@app.route('/pages')
def get_pages():
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('.html')]
    result = [{"name": f.replace('.html',''), "url": "/" + f} for f in files]
    return jsonify(result)

@app.route('/media')
def get_media():
    media_dir = os.path.join(DATA_DIR, "assets")
    if not os.path.exists(media_dir):
        return jsonify([])
    result = [{"name": f, "url": "/assets/" + f} for f in os.listdir(media_dir) if os.path.isfile(os.path.join(media_dir, f))]
    return jsonify(result)

@app.route('/edit', methods=['GET', 'POST'])
def edit_file():
    fname = request.args.get('file')
    if not fname or ".." in fname:
        return jsonify({"error": "Invalid file"}), 400
    fpath = os.path.join(DATA_DIR, fname)
    if request.method == 'GET':
        if not os.path.exists(fpath): return jsonify({"error": "404"}), 404
        with open(fpath, 'r', encoding='utf-8') as f:
            return jsonify({"filename": fname, "content": f.read()})
    if request.method == 'POST':
        content = request.json.get('content') if request.is_json else None
        if content is None and 'content' not in (request.form or {}):
            content = request.form.get('content')
        if content is None:
            return jsonify({"error": "Missing content"}), 400
        os.makedirs(BACKUP_DIR, exist_ok=True)
        if os.path.exists(fpath):
            subprocess.run(f"cp {fpath} {BACKUP_DIR}/{fname}.bak", shell=True)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        return jsonify({"status": "saved"})

@app.route('/settings', methods=['GET', 'POST'])
def get_settings():
    path = os.path.join(DATA_DIR, 'admin/settings.json')
    if request.method == 'POST':
        data = request.get_json(force=True, silent=True) or {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                current = json.load(f)
            current['site_name'] = data.get('site_name', current.get('site_name', ''))
            current['email'] = data.get('email', current.get('email', ''))
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
            return jsonify({"status":"saved"})
        except Exception as e:
            return jsonify({"error":str(e)}), 500
    else:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except Exception as e:
            return jsonify({"site_name":"JNN Factory","description":"","email":"","logo":"","whatsapp":""})

SITE_DATA = os.path.join(DATA_DIR, "admin", "site_data.json")

def init_site_data():
    if not os.path.exists(SITE_DATA):
        default = {
            "seo":{"title":"JNN Factory","description":""},
            "meta_tags":{"keywords":"","author":""},
            "contacts":{"phone":"","email":""},
            "catalog":[{"id":1,"name":"Товар","price":100.0,"image":"assets/"}],
            "media":{"banner":"assets/","gallery":[]}
        }
        with open(SITE_DATA,"w") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)

@app.route('/api/content', methods=['GET','POST'])
def api_content():
    init_site_data()
    if request.method == 'GET':
        with open(SITE_DATA) as f:
            return jsonify(json.load(f))
    payload = request.get_json(force=True, silent=True) or {}
    assert isinstance(payload.get("seo"), dict) and isinstance(payload.get("seo").get("title"), str)
    assert isinstance(payload.get("contacts"), dict) and isinstance(payload.get("contacts").get("phone"), str)
    assert isinstance(payload.get("catalog"), list) and len(payload.get("catalog")) >= 1
    for item in payload.get("catalog", []):
        assert isinstance(item.get("price"), (int, float))
    with open(SITE_DATA, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return jsonify({"status":"saved","sections":list(payload.keys())})

@app.route('/api/catalog')
def get_catalog():
    return jsonify({"items": ["Производство одежды", "Шелкография", "СТМ бренды"]})

@app.route('/api/categories')
def get_cats():
    return jsonify(["Производство одежды", "Шелкография", "СТМ бренды"])

if __name__ == '__main__':
    subprocess.run("fuser -k 5000/tcp", shell=True)
    app.run(host='127.0.0.1', port=5000)
