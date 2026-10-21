"""Тесты второго этапа: force-операции, Directus media, папки и автоимена."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from admin import main as gallery_main


KEY = "test-gallery-key"
HEADERS = {"X-Gallery-Key": KEY}
MEDIA_ID = "12345678-1234-1234-1234-123456789abc"
TEST_ADMIN = {"id": "test-admin", "email": "admin@example.test", "name": "Test Admin"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(gallery_main, "_authenticate_admin", lambda request: {
        "type": "test", "user": TEST_ADMIN,
    })
    return TestClient(gallery_main.app)


@pytest.fixture()
def anon_client(monkeypatch):
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


def no_usage(name="", file_id=""):
    return {"available": True, "error": "", "products": [], "files": [], "in_use": False}


def used_by_product(name="", file_id=""):
    return {
        "available": True,
        "error": "",
        "products": ["Velvet Suit [velvet-suit]"],
        "files": [],
        "in_use": True,
    }


PRODUCT = {
    "id": 7,
    "slug": "velvet-suit",
    "name": "Velvet Suit",
    "label": "Velvet Suit [velvet-suit]",
}


def quiet_list(monkeypatch):
    monkeypatch.setattr(gallery_main, "_directus_images", lambda: [])
    monkeypatch.setattr(gallery_main, "_git_tracked_assets", lambda: set())
    monkeypatch.setattr(gallery_main, "_directus_product_records", lambda: ([], None))


def test_next_auto_name_adds_free_suffix():
    assert gallery_main._next_auto_name("velvet-suit", "x.jpg", set()) == "velvet-suit.jpg"
    assert gallery_main._next_auto_name("velvet-suit", "x.jpg", {"velvet-suit.jpg"}) == "velvet-suit1.jpg"
    assert gallery_main._next_auto_name(
        "velvet-suit", "x.jpg", {"velvet-suit.jpg", "velvet-suit1.jpg"}
    ) == "velvet-suit2.jpg"
    assert gallery_main._next_auto_name("Платье", "x.jpeg", set()) == "product.jpg"


def test_directus_file_rows_paginates(monkeypatch):
    offsets = []

    def fake_request(method, path, payload=None, timeout=0, write=False):
        query = path.split("?", 1)[1]
        params = dict(part.split("=", 1) for part in query.split("&"))
        offset = int(params["offset"])
        offsets.append(offset)
        size = 100 if offset == 0 else 1
        return {"data": [{"filename_download": "f%d.jpg" % (offset + i)} for i in range(size)]}

    monkeypatch.setattr(gallery_main, "_directus_request", fake_request)
    rows = gallery_main._directus_file_rows("filename_download")

    assert len(rows) == 101
    assert offsets == [0, 100]


def test_attach_product_appends_without_becoming_main_photo(monkeypatch):
    calls = []

    def fake_request(method, path, payload=None, timeout=0, write=False):
        calls.append((method, path, payload))
        if method == "GET":
            return {"data": [{"sort": 1}, {"sort": 4}]}
        return {}

    monkeypatch.setattr(gallery_main, "_directus_request", fake_request)
    gallery_main._directus_attach_product("7", MEDIA_ID)

    assert calls[0][0] == "GET"
    assert "products_files" in calls[0][1]
    assert calls[1][0] == "POST"
    assert calls[1][2] == {
        "products_id": "7",
        "directus_files_id": MEDIA_ID,
        "sort": 5,
    }


def test_upload_product_local_autonames_and_does_not_overwrite(client, assets, monkeypatch):
    make_file(assets, "velvet-suit.jpg", b"old")
    monkeypatch.setattr(gallery_main, "_directus_product_records", lambda: ([PRODUCT], None))
    monkeypatch.setattr(gallery_main, "_directus_existing_names", lambda: set())

    first = client.post(
        "/gallery-api/upload-product",
        data={"product": "7", "target": "local"},
        files={"file": ("phone.jpg", b"new-1", "image/jpeg")},
        headers=HEADERS,
    )
    second = client.post(
        "/gallery-api/upload-product",
        data={"product": "velvet-suit", "target": "local"},
        files={"file": ("phone.jpg", b"new-2", "image/jpeg")},
        headers=HEADERS,
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["name"] == "velvet-suit1.jpg"
    assert second.json()["name"] == "velvet-suit2.jpg"
    assert (assets / "velvet-suit.jpg").read_bytes() == b"old"
    assert (assets / "velvet-suit1.jpg").read_bytes() == b"new-1"
    assert (assets / "velvet-suit2.jpg").read_bytes() == b"new-2"


def test_upload_product_directus_autonames_and_attaches(client, assets, monkeypatch):
    calls = {}
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "test-token")
    monkeypatch.setattr(gallery_main, "_directus_product_records", lambda: ([PRODUCT], None))
    monkeypatch.setattr(gallery_main, "_directus_existing_names", lambda: {"velvet-suit.jpg"})

    def upload(filename, content, content_type=""):
        calls["upload"] = (filename, content, content_type)
        return MEDIA_ID

    def patch(uid, name):
        calls["patch"] = (uid, name)

    def attach(product_id, file_id):
        calls["attach"] = (product_id, file_id)

    monkeypatch.setattr(gallery_main, "_directus_upload_media", upload)
    monkeypatch.setattr(gallery_main, "_directus_patch_name", patch)
    monkeypatch.setattr(gallery_main, "_directus_attach_product", attach)

    response = client.post(
        "/gallery-api/upload-product",
        data={"product": "velvet-suit", "target": "directus", "attach": "1"},
        files={"file": ("phone.jpg", b"new-photo", "image/jpeg")},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "velvet-suit1.jpg"
    assert body["url"] == "/assets/" + MEDIA_ID
    assert body["attached"] is True
    assert calls["upload"][0] == "velvet-suit1.jpg"
    assert calls["patch"] == (MEDIA_ID, "velvet-suit1.jpg")
    assert calls["attach"] == ("7", MEDIA_ID)


def test_upload_product_requires_admin_session(anon_client, assets, monkeypatch):
    monkeypatch.setattr(gallery_main, "_directus_product_records", lambda: ([PRODUCT], None))
    response = anon_client.post(
        "/gallery-api/upload-product",
        data={"product": "7", "target": "local"},
        files={"file": ("phone.jpg", b"new", "image/jpeg")},
    )
    assert response.status_code == 401


def test_force_delete_used_file(client, assets, monkeypatch):
    path = make_file(assets)
    monkeypatch.setattr(gallery_main, "_usage_report", used_by_product)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "photo.jpg", "force": "true"},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert response.json()["forced"] is True
    assert not path.exists()


def test_delete_existing_name_with_spaces_and_parentheses(client, assets, monkeypatch):
    path = make_file(assets, "photo (1).jpg")
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "photo (1).jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert not path.exists()


def test_rename_existing_name_with_spaces_and_parentheses(client, assets, monkeypatch):
    old = make_file(assets, "photo (1).jpg")
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)

    response = client.post(
        "/gallery-api/rename",
        json={"old": "photo (1).jpg", "new": "photo (2).jpg"},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert not old.exists()
    assert (assets / "photo (2).jpg").read_bytes() == b"photo"


def test_force_delete_tracked_calls_git_rm(client, assets, monkeypatch):
    path = make_file(assets)
    called = []
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: True)
    monkeypatch.setattr(
        gallery_main,
        "_git_remove_tracked",
        lambda name: (called.append(name) is None and path.unlink() is None, ""),
    )

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "photo.jpg", "force": "true"},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert called == ["photo.jpg"]
    assert response.json()["git_commit_required"] is True
    assert not path.exists()


def test_force_delete_tracked_uses_real_git_rm(client, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    assets_dir = repo / "assets"
    assets_dir.mkdir(parents=True)
    path = assets_dir / "tracked.jpg"
    path.write_bytes(b"tracked")

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo)] + list(args),
            capture_output=True,
            text=True,
            check=True,
        )

    git("init")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Gallery Test")
    git("add", "assets/tracked.jpg")
    git("commit", "-m", "tracked")

    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(assets_dir))
    monkeypatch.setattr(gallery_main, "GALLERY_FOLDERS_FILE", str(tmp_path / "folders.json"))
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "")
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "tracked.jpg", "force": "true"},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert not path.exists()
    status = git("status", "--porcelain", "--", "assets").stdout
    assert status.startswith("D  assets/tracked.jpg"), status


def test_force_rename_tracked_uses_real_git_mv(client, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    assets_dir = repo / "assets"
    assets_dir.mkdir(parents=True)
    old = assets_dir / "old.jpg"
    old.write_bytes(b"tracked")
    new = assets_dir / "new.jpg"

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(repo)] + list(args),
            capture_output=True,
            text=True,
            check=True,
        )

    git("init")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Gallery Test")
    git("add", "assets/old.jpg")
    git("commit", "-m", "tracked")

    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(assets_dir))
    monkeypatch.setattr(gallery_main, "GALLERY_FOLDERS_FILE", str(tmp_path / "folders.json"))
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "")
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)

    response = client.post(
        "/gallery-api/rename",
        json={"old": "old.jpg", "new": "new.jpg", "force": True},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert not old.exists()
    assert new.read_bytes() == b"tracked"
    status = git("status", "--porcelain", "--", "assets").stdout
    assert status.startswith("R  assets/old.jpg -> assets/new.jpg"), status


def test_force_rename_tracked_calls_git_mv(client, assets, monkeypatch):
    old = make_file(assets, "old.jpg")
    new = assets / "new.jpg"
    monkeypatch.setattr(gallery_main, "_usage_report", used_by_product)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: name == "old.jpg")
    monkeypatch.setattr(
        gallery_main,
        "_git_move_tracked",
        lambda a, b: (os.rename(str(old), str(new)) is None, ""),
    )

    response = client.post(
        "/gallery-api/rename",
        json={"old": "old.jpg", "new": "new.jpg", "force": True},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert response.json()["git_commit_required"] is True
    assert not old.exists()
    assert new.exists()


def test_force_delete_symlink_does_not_touch_target(client, assets, monkeypatch):
    target = make_file(assets, "real.jpg")
    link = assets / "alias.jpg"
    try:
        link.symlink_to(target.name)
    except OSError:
        pytest.skip("symlink creation is not available")
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)

    response = client.delete(
        "/gallery-api/delete",
        params={"file": "alias.jpg", "force": "true"},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert not link.exists()
    assert target.exists()


def test_media_rename_force(client, monkeypatch):
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "test-token")
    monkeypatch.setattr(
        gallery_main,
        "_directus_file_info",
        lambda uid: {"id": uid, "name": "old.jpg", "type": "image/jpeg", "size": 1},
    )
    monkeypatch.setattr(gallery_main, "_media_usage_report", used_by_product)
    calls = []
    monkeypatch.setattr(gallery_main, "_directus_patch_name", lambda uid, name: calls.append((uid, name)))

    response = client.post(
        "/gallery-api/media/rename",
        json={"id": MEDIA_ID, "new": "new.jpg", "force": True},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert response.json()["forced"] is True
    assert calls == [(MEDIA_ID, "new.jpg")]


def test_media_delete_force(client, monkeypatch):
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "test-token")
    monkeypatch.setattr(
        gallery_main,
        "_directus_file_info",
        lambda uid: {"id": uid, "name": "old.jpg", "type": "image/jpeg", "size": 1},
    )
    monkeypatch.setattr(gallery_main, "_media_usage_report", used_by_product)
    called = []
    monkeypatch.setattr(gallery_main, "_directus_delete_file", lambda uid: called.append(uid))

    response = client.delete(
        "/gallery-api/media/" + MEDIA_ID,
        params={"force": "true"},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert response.json()["forced"] is True
    assert called == [MEDIA_ID]


def test_media_delete_without_token_is_503(client, monkeypatch):
    monkeypatch.setattr(
        gallery_main,
        "_directus_file_info",
        lambda uid: {"id": uid, "name": "old.jpg", "type": "image/jpeg", "size": 1},
    )
    monkeypatch.setattr(gallery_main, "_media_usage_report", no_usage)

    response = client.delete(
        "/gallery-api/media/" + MEDIA_ID,
        params={"force": "true"},
        headers=HEADERS,
    )

    assert response.status_code == 503


def test_folder_create_and_move_local_file(client, assets, monkeypatch):
    path = make_file(assets)
    quiet_list(monkeypatch)
    created = client.post(
        "/gallery-api/folders",
        json={"name": "Летучки"},
        headers=HEADERS,
    )
    assert created.status_code == 200, created.text
    folder_id = created.json()["folder"]["id"]

    moved = client.post(
        "/gallery-api/folders/move",
        json={"source": "local", "key": path.name, "folder_id": folder_id},
        headers=HEADERS,
    )
    assert moved.status_code == 200, moved.text

    listing = client.get("/gallery-api/list").json()
    assert listing["folders_ok"] is True
    assert listing["folders"][0]["name"] == "Летучки"
    item = {f["name"]: f for f in listing["files"]}[path.name]
    assert item["folder_id"] == folder_id


def test_nested_folder_and_directus_media_move(client, assets, monkeypatch):
    quiet_list(monkeypatch)
    parent = client.post(
        "/gallery-api/folders",
        json={"name": "Родитель"},
        headers=HEADERS,
    ).json()["folder"]
    child = client.post(
        "/gallery-api/folders",
        json={"name": "Дочерняя", "parent": parent["id"]},
        headers=HEADERS,
    ).json()["folder"]
    monkeypatch.setattr(
        gallery_main,
        "_directus_file_info",
        lambda uid: {"id": uid, "name": "media.jpg", "type": "image/jpeg", "size": 1},
    )

    response = client.post(
        "/gallery-api/folders/move",
        json={"source": "directus", "key": MEDIA_ID, "folder_id": child["id"]},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    listing = client.get("/gallery-api/list").json()
    assert listing["folders"][1]["parent"] == parent["id"]
    manifest = json.loads(Path(gallery_main.GALLERY_FOLDERS_FILE).read_text(encoding="utf-8"))
    assert manifest["files"]["directus:" + MEDIA_ID] == child["id"]


def test_upload_into_folder_sets_folder_id(client, assets, monkeypatch):
    quiet_list(monkeypatch)
    created = client.post("/gallery-api/folders", json={"name": "Новинки"}, headers=HEADERS)
    folder_id = created.json()["folder"]["id"]

    response = client.post(
        "/gallery-api/upload",
        data={"folder_id": folder_id},
        files={"files": ("inside.jpg", b"inside", "image/jpeg")},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    assert response.json()["uploaded"][0]["folder_id"] == folder_id

    listing = client.get("/gallery-api/list").json()
    item = {f["name"]: f for f in listing["files"]}["inside.jpg"]
    assert item["folder_id"] == folder_id


def test_corrupt_folder_manifest_blocks_writes_but_not_listing(client, assets, monkeypatch):
    path = Path(gallery_main.GALLERY_FOLDERS_FILE)
    path.write_text("{broken", encoding="utf-8")
    quiet_list(monkeypatch)

    response = client.post("/gallery-api/folders", json={"name": "Папка"}, headers=HEADERS)
    assert response.status_code == 503

    listing = client.get("/gallery-api/list")
    assert listing.status_code == 200
    assert listing.json()["folders_ok"] is False


def test_media_auto_name(client, monkeypatch):
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "test-token")
    monkeypatch.setattr(
        gallery_main,
        "_directus_file_info",
        lambda uid: {"id": uid, "name": "random.jpg", "type": "image/jpeg", "size": 1},
    )
    monkeypatch.setattr(gallery_main, "_directus_product_records", lambda: ([PRODUCT], None))
    monkeypatch.setattr(
        gallery_main,
        "_directus_existing_names",
        lambda: {"velvet-suit.jpg", "velvet-suit1.jpg"},
    )
    monkeypatch.setattr(gallery_main, "_media_usage_report", no_usage)
    calls = []
    monkeypatch.setattr(gallery_main, "_directus_patch_name", lambda uid, name: calls.append((uid, name)))

    response = client.post(
        "/gallery-api/media/auto-name",
        json={"id": MEDIA_ID, "product": "7"},
        headers=HEADERS,
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "velvet-suit2.jpg"
    assert calls == [(MEDIA_ID, "velvet-suit2.jpg")]


def test_list_exposes_product_catalog_and_media_write_state(client, assets, monkeypatch):
    make_file(assets, "local.jpg")
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "test-token")
    monkeypatch.setattr(gallery_main, "_git_tracked_assets", lambda: set())
    monkeypatch.setattr(
        gallery_main,
        "_directus_images",
        lambda: [{
            "id": MEDIA_ID,
            "name": "media.jpg",
            "size": 10,
            "mtime": 1,
            "url": "/assets/" + MEDIA_ID,
            "hash": "",
        }],
    )
    monkeypatch.setattr(gallery_main, "_directus_product_records", lambda: ([PRODUCT], None))

    response = client.get("/gallery-api/list")
    assert response.status_code == 200
    body = response.json()
    assert body["media_writable"] is True
    assert body["product_catalog"][0]["slug"] == "velvet-suit"
    assert body["directus"][0]["deletable"] is True
    assert body["folders"] == []
