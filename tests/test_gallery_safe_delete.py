"""Тесты безопасного удаления файлов галереи.

Проверяют контракт API без production-сервера: usage-check, обязательную
блокировку используемых и Git-отслеживаемых файлов, а также happy path для
нового (untracked) файла.
"""

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from admin import main as gallery_main


KEY = "test-gallery-key"
HEADERS = {"X-Gallery-Key": KEY}


@pytest.fixture(autouse=True)
def _isolate_directus_token(monkeypatch):
    """Не зависеть от JNN_DIRECTUS_TOKEN в окружении разработчика/CI."""
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("JNN_GALLERY_KEY", KEY)
    return TestClient(gallery_main.app)


@pytest.fixture()
def assets(tmp_path, monkeypatch):
    directory = tmp_path / "assets"
    directory.mkdir()
    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(directory))
    monkeypatch.setattr(gallery_main, "GALLERY_FOLDERS_FILE", str(tmp_path / "gallery_folders.json"))
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "")
    return directory


def make_file(assets: Path, name: str = "photo.jpg", content: bytes = b"photo") -> Path:
    path = assets / name
    path.write_bytes(content)
    return path


def no_usage(name, file_id=""):
    return {
        "available": True,
        "error": "",
        "products": [],
        "files": [],
        "in_use": False,
    }


def used_by_product(name, file_id=""):
    return {
        "available": True,
        "error": "",
        "products": ["Velvet Suit [velvet-suit]"],
        "files": [],
        "in_use": True,
    }


def test_existing_name_rejects_traversal():
    assert gallery_main._existing_name("photo.jpg") == "photo.jpg"
    assert gallery_main._existing_name("photo (1).jpg") == "photo (1).jpg"
    assert gallery_main._existing_name("../photo.jpg") == ""
    assert gallery_main._existing_name("dir/photo.jpg") == ""
    assert gallery_main._existing_name("dir\\photo.jpg") == ""
    assert gallery_main._existing_name("..") == ""


def test_usage_check_requires_key(client, assets):
    make_file(assets)
    response = client.get("/gallery-api/usage-check", params={"file": "photo.jpg"})
    assert response.status_code == 401


def test_usage_check_returns_409_with_products(client, assets, monkeypatch):
    make_file(assets)
    monkeypatch.setattr(gallery_main, "_usage_report", used_by_product)

    response = client.get(
        "/gallery-api/usage-check",
        params={"file": "photo.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 409
    body = response.json()
    assert body["reason"] == "in_use"
    assert body["products"] == ["Velvet Suit [velvet-suit]"]
    assert body["deletable"] is False


def test_delete_linked_file_is_blocked_and_kept(client, assets, monkeypatch):
    path = make_file(assets)
    monkeypatch.setattr(gallery_main, "_usage_report", used_by_product)

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "photo.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["products"] == ["Velvet Suit [velvet-suit]"]
    assert path.exists(), "используемый файл нельзя удалять"


def test_delete_blocks_git_tracked_file(client, assets, monkeypatch):
    path = make_file(assets)
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: True)

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "photo.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["reason"] == "git_tracked"
    assert path.exists(), "tracked-файл нельзя удалять: git pull вернёт его"


def test_delete_untracked_unused_file_succeeds(client, assets, monkeypatch):
    path = make_file(assets)
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "photo.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["deleted"] == "photo.jpg"
    assert not path.exists()


def test_delete_fails_closed_when_usage_is_unavailable(client, assets, monkeypatch):
    path = make_file(assets)

    def unavailable(name, file_id=""):
        return {
            "available": False,
            "error": "Directus недоступен",
            "products": [],
            "files": [],
            "in_use": None,
        }

    monkeypatch.setattr(gallery_main, "_usage_report", unavailable)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "photo.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 503
    assert response.json()["reason"] == "usage_unavailable"
    assert path.exists()


def test_usage_check_marks_tracked_file_not_deletable(client, assets, monkeypatch):
    make_file(assets)
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: True)

    response = client.get(
        "/gallery-api/usage-check",
        params={"file": "photo.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deletable"] is False
    assert body["git_tracked"] is True
    assert body["reason"] == "git_tracked"


def test_usage_check_directus_media_allows_management_with_token(client, monkeypatch):
    media_id = "12345678-1234-1234-1234-123456789abc"
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "test-token")
    monkeypatch.setattr(
        gallery_main,
        "_directus_file_info",
        lambda uid: {"id": uid, "name": "photo.jpg", "type": "image/jpeg", "size": 5},
    )
    monkeypatch.setattr(gallery_main, "_media_usage_report", no_usage)

    response = client.get(
        "/gallery-api/usage-check",
        params={"id": media_id},
        headers=HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deletable"] is True
    assert body["can_force"] is True
    assert body["reason"] == "directus_media"


def test_usage_check_directus_media_without_token_is_not_writable(client, monkeypatch):
    media_id = "12345678-1234-1234-1234-123456789abc"
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "")
    monkeypatch.setattr(
        gallery_main,
        "_directus_file_info",
        lambda uid: {"id": uid, "name": "photo.jpg", "type": "image/jpeg", "size": 5},
    )
    monkeypatch.setattr(gallery_main, "_media_usage_report", no_usage)

    response = client.get(
        "/gallery-api/usage-check",
        params={"id": media_id},
        headers=HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deletable"] is False
    assert body["can_force"] is False
    assert body["reason"] == "directus_write_unavailable"


def test_list_marks_git_tracked_and_new_files(client, assets, monkeypatch):
    make_file(assets, "tracked.jpg")
    make_file(assets, "new.jpg")
    monkeypatch.setattr(gallery_main, "_directus_images", lambda: [])
    monkeypatch.setattr(gallery_main, "_git_tracked_assets", lambda: {"tracked.jpg"})
    monkeypatch.setattr(
        gallery_main,
        "_directus_product_records",
        lambda: ([], None),
    )

    response = client.get("/gallery-api/list")

    assert response.status_code == 200
    files = {item["name"]: item for item in response.json()["files"]}
    assert files["tracked.jpg"]["git_tracked"] is True
    assert files["tracked.jpg"]["deletable"] is False
    assert files["new.jpg"]["git_tracked"] is False
    assert files["new.jpg"]["deletable"] is True


def test_list_attaches_product_links_for_cards(client, assets, monkeypatch):
    make_file(assets, "used.jpg")
    make_file(assets, "free.jpg")
    records = [{
        "id": 7,
        "slug": "velvet-suit",
        "name": "Velvet Suit",
        "label": "Velvet Suit [velvet-suit]",
        "blob": '["/assets/used.jpg"]',
    }]
    monkeypatch.setattr(gallery_main, "_directus_images", lambda: [])
    monkeypatch.setattr(gallery_main, "_git_tracked_assets", lambda: {"used.jpg"})
    monkeypatch.setattr(gallery_main, "_directus_product_records", lambda: (records, None))

    response = client.get("/gallery-api/list")

    assert response.status_code == 200
    body = response.json()
    files = {item["name"]: item for item in body["files"]}
    assert files["used.jpg"]["products"] == [{
        "id": 7,
        "slug": "velvet-suit",
        "name": "Velvet Suit",
        "label": "Velvet Suit [velvet-suit]",
    }]
    assert files["free.jpg"]["products"] == []
    assert body["products_ok"] is True


def test_list_links_local_twin_to_directus_media(client, assets, monkeypatch):
    content = b"photo"
    make_file(assets, "twin.jpg", content)
    media_id = "12345678-1234-1234-1234-123456789abc"
    record = {
        "id": 5,
        "slug": "men-longsleeve",
        "name": "Men Longsleeve",
        "label": "Men Longsleeve [men-longsleeve]",
        "tokens": {media_id},
    }
    monkeypatch.setattr(gallery_main, "_directus_images", lambda: [{
        "id": media_id,
        "hash": hashlib.sha256(content).hexdigest(),
        "name": "directus-name.jpg",
        "size": len(content),
        "mtime": 0,
        "url": "/assets/" + media_id,
    }])
    monkeypatch.setattr(gallery_main, "_git_tracked_assets", lambda: set())
    monkeypatch.setattr(gallery_main, "_directus_product_records", lambda: ([record], None))

    response = client.get("/gallery-api/list")

    assert response.status_code == 200
    body = response.json()
    twin = {item["name"]: item for item in body["files"]}["twin.jpg"]
    assert twin["in_media"] is True
    assert twin["media_id"] == media_id
    assert twin["products"] == [{
        "id": 5,
        "slug": "men-longsleeve",
        "name": "Men Longsleeve",
        "label": "Men Longsleeve [men-longsleeve]",
    }]
    assert body["directus"] == []


def test_product_refs_match_file_name_and_directus_id():
    records = [{
        "id": 1,
        "slug": "one",
        "name": "One",
        "label": "One [one]",
        "tokens": {"a.jpg", "12345678-1234-1234-1234-123456789abc"},
    }]

    assert [p["id"] for p in gallery_main._product_refs(records, "a.jpg")] == [1]
    assert [p["id"] for p in gallery_main._product_refs(
        records, "12345678-1234-1234-1234-123456789abc"
    )] == [1]
    assert gallery_main._product_refs(records, "other.jpg") == []


def test_product_refs_do_not_match_filename_substrings():
    records = [{
        "id": 1,
        "slug": "hoodie",
        "name": "Hoodie",
        "label": "Hoodie [hoodie]",
        "tokens": {"women-hoodies1.webp", "letuchka_1.jpg"},
    }]

    assert gallery_main._product_refs(records, "1.webp") == []
    assert gallery_main._product_refs(records, "1.jpg") == []
    assert [p["id"] for p in gallery_main._product_refs(records, "letuchka_1.jpg")] == [1]


def test_media_tokens_extract_exact_basename_and_uuid():
    tokens = gallery_main._media_tokens([
        "/assets/women-hoodies1.webp?x=1",
        ["https://cdn.example/letuchka_1.jpg", "12345678-1234-1234-1234-123456789abc"],
    ])

    assert "women-hoodies1.webp" in tokens
    assert "letuchka_1.jpg" in tokens
    assert "12345678-1234-1234-1234-123456789abc" in tokens
    assert "1.webp" not in tokens
    assert "1.jpg" not in tokens


def test_files_usage_requires_filename_boundary(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "other.html").write_text('<img src="/assets/women-hoodies1.webp">', encoding="utf-8")
    (tmp_path / "exact.html").write_text('<img src="/assets/1.webp">', encoding="utf-8")
    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(assets))

    assert gallery_main._files_usage("1.webp") == ["exact.html"]


def test_files_usage_matches_url_encoded_name(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "encoded.html").write_text(
        '<img src="/assets/photo%20one.jpg">', encoding="utf-8"
    )
    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(assets))

    assert gallery_main._asset_url("photo one.jpg") == "/assets/photo%20one.jpg"
    assert gallery_main._files_usage("photo one.jpg") == ["encoded.html"]


def test_folder_manifest_is_not_a_site_reference(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    admin = tmp_path / "admin"
    assets.mkdir()
    admin.mkdir()
    (admin / ".gallery_folders.json").write_text(
        '{"files": {"local:photo.jpg": "folder-1"}}', encoding="utf-8"
    )
    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(assets))

    assert gallery_main._files_usage("photo.jpg") == []


def test_custom_folder_manifest_path_is_not_a_site_reference(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    runtime = tmp_path / "runtime"
    assets.mkdir()
    runtime.mkdir()
    manifest = runtime / "folders.json"
    manifest.write_text(
        '{"files": {"local:photo.jpg": "folder-1"}}', encoding="utf-8"
    )
    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(assets))
    monkeypatch.setattr(gallery_main, "GALLERY_FOLDERS_FILE", str(manifest))

    assert gallery_main._files_usage("photo.jpg") == []


def test_product_records_merge_ids_and_filenames(monkeypatch):
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "")

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            import json
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(url, timeout=0):
        if "filename_download" in url:
            return Response({"data": [{
                "id": 1,
                "slug": "velvet-suit",
                "name": "Velvet Suit",
                "gallery_urls": ["/assets/velvet.jpg"],
                "gallery": [{"directus_files_id": {"filename_download": "velvet.jpg"}}],
            }]})
        return Response({"data": [{
            "id": 1,
            "slug": "velvet-suit",
            "name": "Velvet Suit",
            "image": "/assets/velvet.jpg",
            "gallery_urls": ["/assets/velvet.jpg"],
            "gallery": [{"id": 5, "directus_files_id": "12345678-1234-1234-1234-123456789abc"}],
        }]})

    monkeypatch.setattr(gallery_main.urllib.request, "urlopen", fake_urlopen)
    records, error = gallery_main._directus_product_records()

    assert error is None
    assert len(records) == 1
    record = records[0]
    assert record["id"] == 1
    assert record["label"] == "Velvet Suit [velvet-suit]"
    assert "/assets/velvet.jpg" in record["blob"]
    assert "12345678-1234-1234-1234-123456789abc" in record["blob"]


def test_actual_git_tracking_helper(tmp_path, monkeypatch):
    if not shutil.which("git"):
        pytest.skip("git is not installed")
    assets = tmp_path / "assets"
    assets.mkdir()
    make_file(assets, "tracked.jpg")
    make_file(assets, "new.jpg")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "--", "assets/tracked.jpg"],
        check=True,
    )
    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(assets))

    assert gallery_main._git_tracked("tracked.jpg") is True
    assert gallery_main._git_tracked("new.jpg") is False
    assert gallery_main._git_tracked_assets() == {"tracked.jpg"}


def test_usage_report_blocks_static_page_references(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    make_file(assets, "photo.jpg")
    (tmp_path / "product.html").write_text(
        '<img src="/assets/photo.jpg">', encoding="utf-8"
    )
    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(assets))
    monkeypatch.setattr(gallery_main, "_product_usage", lambda name: ([], None))

    report = gallery_main._usage_report("photo.jpg")

    assert report["available"] is True
    assert report["in_use"] is True
    assert report["files"] == ["product.html"]

class _FakeResponse:
    def __init__(self, payload):
        import io
        import json
        self._stream = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self._stream

    def __exit__(self, exc_type, exc, tb):
        return False


def test_product_usage_matches_directus_id_and_returns_slug(monkeypatch):
    def fake_urlopen(url, timeout=5):
        if "filename_download" in url:
            return _FakeResponse({
                "data": [{
                    "id": "prod-1",
                    "slug": "velvet-suit",
                    "name": "Velvet Suit",
                    "gallery": [{"directus_files_id": {"filename_download": "photo.jpg"}}],
                }]
            })
        return _FakeResponse({
            "data": [{
                "id": "prod-1",
                "slug": "velvet-suit",
                "name": "Velvet Suit",
                "image": "file-uuid",
                "gallery": [{"directus_files_id": "file-uuid"}],
                "gallery_urls": "",
            }]
        })

    monkeypatch.setattr(gallery_main.urllib.request, "urlopen", fake_urlopen)
    hits, error = gallery_main._product_usage("file-uuid")
    assert error is None
    assert hits == ["Velvet Suit [velvet-suit]"]

def test_usage_endpoint_requires_key(client, monkeypatch):
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    response = client.get("/gallery-api/usage", params={"file": "photo.jpg"})
    assert response.status_code == 401


def test_delete_fails_closed_when_git_is_unavailable(client, assets, monkeypatch):
    path = make_file(assets)
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: None)

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "photo.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 503
    assert response.json()["reason"] == "git_unavailable"
    assert path.exists()


def test_usage_check_fails_closed_when_directus_is_unavailable(client, assets, monkeypatch):
    make_file(assets)

    def unavailable(name, file_id=""):
        return {
            "available": False,
            "error": "Directus недоступен",
            "products": [],
            "files": [],
            "in_use": None,
        }

    monkeypatch.setattr(gallery_main, "_usage_report", unavailable)
    response = client.get(
        "/gallery-api/usage-check",
        params={"file": "photo.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 503
    assert response.json()["reason"] == "usage_unavailable"


def test_rename_blocks_used_file(client, assets, monkeypatch):
    source = make_file(assets, "old.jpg")
    monkeypatch.setattr(gallery_main, "_usage_report", used_by_product)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)

    response = client.post(
        "/gallery-api/rename",
        json={"old": "old.jpg", "new": "new.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 409
    assert source.exists()
    assert not (assets / "new.jpg").exists()


def test_rename_blocks_git_tracked_file(client, assets, monkeypatch):
    source = make_file(assets, "old.jpg")
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: True)

    response = client.post(
        "/gallery-api/rename",
        json={"old": "old.jpg", "new": "new.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["reason"] == "git_tracked"
    assert source.exists()


def test_rename_untracked_unused_file_succeeds(client, assets, monkeypatch):
    source = make_file(assets, "old.jpg")
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)

    response = client.post(
        "/gallery-api/rename",
        json={"old": "old.jpg", "new": "new.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert not source.exists()
    assert (assets / "new.jpg").exists()


def test_delete_through_symlinked_assets_dir(client, tmp_path, monkeypatch):
    real = tmp_path / "real-assets"
    real.mkdir()
    path = real / "photo.jpg"
    path.write_bytes(b"photo")
    link = tmp_path / "assets-link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not available")

    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(link))
    monkeypatch.setattr(gallery_main, "GALLERY_FOLDERS_FILE", str(tmp_path / "folders.json"))
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "photo.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert not path.exists()


def test_delete_blocks_symlink_to_tracked_file(client, assets, monkeypatch):
    target = make_file(assets, "tracked.jpg")
    link = assets / "alias.jpg"
    try:
        link.symlink_to(target.name)
    except OSError:
        pytest.skip("symlink creation is not available")

    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "alias.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 400
    assert target.exists()
    assert link.exists()


def test_files_usage_scans_assets_javascript(monkeypatch, tmp_path):
    assets = tmp_path / "assets"
    (assets / "js").mkdir(parents=True)
    make_file(assets, "photo.jpg")
    (assets / "js" / "app.js").write_text("img.src = '/assets/photo.jpg'", encoding="utf-8")
    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(assets))

    hits = gallery_main._files_usage("photo.jpg")

    assert hits == ["assets/js/app.js"]


def test_product_usage_supports_legacy_gallery_files(monkeypatch):
    def fake_urlopen(url, timeout=5):
        if "filename_download" in url:
            return _FakeResponse({
                "data": [{
                    "id": "prod-2",
                    "slug": "legacy-product",
                    "name": "Legacy Product",
                    "gallery_files": [{"directus_files_id": {"filename_download": "legacy.jpg"}}],
                }]
            })
        return _FakeResponse({
            "data": [{
                "id": "prod-2",
                "slug": "legacy-product",
                "name": "Legacy Product",
                "gallery_files": [{"directus_files_id": "legacy-uuid"}],
            }]
        })

    monkeypatch.setattr(gallery_main.urllib.request, "urlopen", fake_urlopen)
    hits, error = gallery_main._product_usage("legacy.jpg")
    assert error is None
    assert hits == ["Legacy Product [legacy-product]"]


def test_product_usage_merges_uuid_and_filename(monkeypatch):
    def fake_urlopen(url, timeout=5):
        if "filename_download" in url:
            return _FakeResponse({
                "data": [{
                    "id": "prod-3",
                    "slug": "merge-product",
                    "name": "Merge Product",
                    "image": {"filename_download": "photo.jpg"},
                }]
            })
        return _FakeResponse({
            "data": [{
                "id": "prod-3",
                "slug": "merge-product",
                "name": "Merge Product",
                "image": "photo-uuid",
            }]
        })

    monkeypatch.setattr(gallery_main.urllib.request, "urlopen", fake_urlopen)

    by_uuid, error = gallery_main._product_usage("photo-uuid")
    assert error is None
    assert by_uuid == ["Merge Product [merge-product]"]
    by_name, error = gallery_main._product_usage("photo.jpg")
    assert error is None
    assert by_name == ["Merge Product [merge-product]"]


def test_product_usage_fails_closed_when_filename_query_fails(monkeypatch):
    def fake_urlopen(url, timeout=5):
        if "filename_download" in url:
            raise OSError("directus fields unavailable")
        return _FakeResponse({"data": [{"id": "prod-4", "name": "Only UUID"}]})

    monkeypatch.setattr(gallery_main.urllib.request, "urlopen", fake_urlopen)
    hits, error = gallery_main._product_usage("photo.jpg")
    assert hits == []
    assert error

def test_legacy_schema_falls_back_to_gallery_files(monkeypatch):
    import io
    import urllib.error

    def fake_urlopen(url, timeout=5):
        if "gallery." in url:
            raise urllib.error.HTTPError(url, 400, "unknown field", {}, io.BytesIO(b""))
        return _FakeResponse({
            "data": [{
                "id": "legacy-1",
                "slug": "legacy-only",
                "name": "Legacy Only",
                "gallery_files": [{"directus_files_id": "legacy-file-uuid"}],
            }]
        })

    monkeypatch.setattr(gallery_main.urllib.request, "urlopen", fake_urlopen)
    hits, error = gallery_main._product_usage("legacy-file-uuid")
    assert error is None
    assert hits == ["Legacy Only [legacy-only]"]


def test_transient_directus_failure_is_not_masked(monkeypatch):
    def fake_urlopen(url, timeout=5):
        if "filename_download" in url:
            raise OSError("timeout")
        return _FakeResponse({"data": [{"id": "p", "name": "Product"}]})

    monkeypatch.setattr(gallery_main.urllib.request, "urlopen", fake_urlopen)
    hits, error = gallery_main._product_usage("photo.jpg")
    assert hits == []
    assert error


def test_delete_blocks_file_changed_during_checks(client, assets, monkeypatch):
    path = make_file(assets, "photo.jpg")
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)

    def change_file(name):
        path.write_bytes(b"changed during check")
        return False

    monkeypatch.setattr(gallery_main, "_git_tracked", change_file)
    response = client.delete(
        "/gallery-api/delete",
        params={"file": "photo.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["reason"] == "file_changed"
    assert path.exists()


def test_delete_requires_key(client, assets):
    make_file(assets)
    response = client.delete("/gallery-api/delete", params={"file": "photo.jpg"})
    assert response.status_code == 401


def test_rename_requires_key(client, assets):
    make_file(assets, "old.jpg")
    response = client.post(
        "/gallery-api/rename",
        json={"old": "old.jpg", "new": "new.jpg"},
    )
    assert response.status_code == 401

def test_rename_does_not_overwrite_destination_created_during_checks(client, assets, monkeypatch):
    source = make_file(assets, "old.jpg")
    destination = assets / "new.jpg"

    def create_destination(name, file_id=""):
        destination.write_bytes(b"concurrent file")
        return no_usage(name)

    monkeypatch.setattr(gallery_main, "_usage_report", create_destination)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)

    response = client.post(
        "/gallery-api/rename",
        json={"old": "old.jpg", "new": "new.jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 409
    assert source.exists()
    assert destination.read_bytes() == b"concurrent file"

def test_upload_creates_new_file(client, assets):
    response = client.post(
        "/gallery-api/upload",
        headers=HEADERS,
        files=[("files", ("new.jpg", b"photo bytes", "image/jpeg"))],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["uploaded"][0]["name"] == "new.jpg"
    assert (assets / "new.jpg").read_bytes() == b"photo bytes"


def test_upload_does_not_overwrite_existing_file(client, assets):
    path = make_file(assets, "new.jpg", b"old bytes")
    response = client.post(
        "/gallery-api/upload",
        headers=HEADERS,
        files=[("files", ("new.jpg", b"new bytes", "image/jpeg"))],
    )

    assert response.status_code == 200
    assert response.json()["skipped"]
    assert path.read_bytes() == b"old bytes"
