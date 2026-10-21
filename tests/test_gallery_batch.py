"""Тесты папок и массовых операций галереи (без Directus-сервера)."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from admin import main as gallery_main


TEST_ADMIN = {"id": "test-admin", "email": "admin@example.test", "name": "Test Admin"}
MEDIA_ID = "12345678-1234-1234-1234-123456789abc"


def no_usage(name="", file_id=""):
    return {"available": True, "error": "", "products": [], "files": [], "in_use": False}


def used(name="", file_id=""):
    return {
        "available": True,
        "error": "",
        "products": ["Velvet Suit [velvet-suit]"],
        "files": [],
        "in_use": True,
    }


@pytest.fixture()
def client(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    assets.mkdir()
    monkeypatch.setattr(gallery_main, "_authenticate_admin", lambda request: {
        "type": "test", "user": TEST_ADMIN,
    })
    monkeypatch.setattr(gallery_main, "ASSETS_DIR", str(assets))
    monkeypatch.setattr(gallery_main, "GALLERY_FOLDERS_FILE", str(tmp_path / "folders.json"))
    monkeypatch.setattr(gallery_main, "DIRECTUS_TOKEN", "")
    monkeypatch.setattr(gallery_main, "_directus_images", lambda: [])
    monkeypatch.setattr(gallery_main, "_git_tracked_assets", lambda: set())
    monkeypatch.setattr(gallery_main, "_directus_product_records", lambda: ([], None))
    monkeypatch.setattr(gallery_main, "_usage_report", no_usage)
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: False)
    return TestClient(gallery_main.app), assets, tmp_path


def make_file(assets: Path, name: str) -> Path:
    path = assets / name
    path.write_bytes(b"image")
    return path


def test_folder_created_in_root_is_returned_for_root_list(client):
    api, assets, _ = client
    created = api.post("/gallery-api/folders", json={"name": "Всякое", "parent": ""})
    assert created.status_code == 200, created.text
    folder_id = created.json()["folder"]["id"]

    listing = api.get("/gallery-api/list")
    assert listing.status_code == 200
    assert listing.json()["folders"] == [
        {"id": folder_id, "name": "Всякое", "parent": ""}
    ]


def test_batch_move_moves_local_files_and_persists_manifest(client):
    api, assets, tmp_path = client
    make_file(assets, "one.jpg")
    make_file(assets, "two.jpg")
    folder = api.post("/gallery-api/folders", json={"name": "Каталог", "parent": ""}).json()["folder"]

    response = api.post("/gallery-api/batch/move", json={
        "items": [{"source": "local", "key": "one.jpg"}, {"source": "local", "key": "two.jpg"}],
        "folder_id": folder["id"],
    })
    assert response.status_code == 200, response.text
    assert response.json()["moved"] == 2

    listing = api.get("/gallery-api/list").json()
    assert {f["name"]: f["folder_id"] for f in listing["files"]} == {
        "one.jpg": folder["id"], "two.jpg": folder["id"],
    }
    manifest = json.loads((tmp_path / "folders.json").read_text(encoding="utf-8"))
    assert manifest["files"] == {
        "local:one.jpg": folder["id"], "local:two.jpg": folder["id"],
    }


def test_batch_delete_safe_files(client):
    api, assets, _ = client
    make_file(assets, "one.jpg")
    make_file(assets, "two.jpg")
    response = api.post("/gallery-api/batch/delete", json={
        "items": [{"source": "local", "key": "one.jpg"}, {"source": "local", "key": "two.jpg"}],
    })
    assert response.status_code == 200, response.text
    assert len(response.json()["deleted"]) == 2
    assert not (assets / "one.jpg").exists()
    assert not (assets / "two.jpg").exists()


def test_batch_delete_blocks_used_files_until_force(client, monkeypatch):
    api, assets, _ = client
    make_file(assets, "used.jpg")
    monkeypatch.setattr(gallery_main, "_usage_report", used)
    payload = {"items": [{"source": "local", "key": "used.jpg"}]}

    blocked = api.post("/gallery-api/batch/delete", json=payload)
    assert blocked.status_code == 409
    assert blocked.json()["can_force"] is True
    assert blocked.json()["blocked"][0]["reason"] == "in_use"
    assert (assets / "used.jpg").exists()

    forced = api.post("/gallery-api/batch/delete", json={**payload, "force": True})
    assert forced.status_code == 200, forced.text
    assert len(forced.json()["deleted"]) == 1
    assert not (assets / "used.jpg").exists()


def test_batch_delete_git_tracked_requires_force(client, monkeypatch):
    api, assets, _ = client
    make_file(assets, "tracked.jpg")
    removed = []
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: name == "tracked.jpg")
    monkeypatch.setattr(gallery_main, "_git_remove_tracked", lambda name: (removed.append(name) or True, ""))
    payload = {"items": [{"source": "local", "key": "tracked.jpg"}]}

    blocked = api.post("/gallery-api/batch/delete", json=payload)
    assert blocked.status_code == 409
    assert blocked.json()["blocked"][0]["reason"] == "git_tracked"
    assert blocked.json()["can_force"] is True
    assert removed == []

    forced = api.post("/gallery-api/batch/delete", json={**payload, "force": True})
    assert forced.status_code == 200, forced.text
    assert removed == ["tracked.jpg"]


def test_batch_delete_fails_closed_when_git_check_unavailable(client, monkeypatch):
    api, assets, _ = client
    make_file(assets, "unknown.jpg")
    monkeypatch.setattr(gallery_main, "_git_tracked", lambda name: None)

    response = api.post("/gallery-api/batch/delete", json={
        "items": [{"source": "local", "key": "unknown.jpg"}],
        "force": True,
    })
    assert response.status_code == 503
    assert response.json()["reason"] == "preflight_failed"
    assert (assets / "unknown.jpg").exists()


def test_batch_delete_deduplicates_or_rejects_invalid_items(client):
    api, assets, _ = client
    make_file(assets, "one.jpg")
    duplicate = api.post("/gallery-api/batch/delete", json={
        "items": [{"source": "local", "key": "one.jpg"}, {"source": "local", "key": "one.jpg"}],
    })
    assert duplicate.status_code == 200
    assert len(duplicate.json()["deleted"]) == 1

    invalid = api.post("/gallery-api/batch/delete", json={
        "items": [{"source": "local", "key": "../secret.jpg"}],
    })
    assert invalid.status_code == 400
