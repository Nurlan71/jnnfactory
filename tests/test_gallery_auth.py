"""Тесты админ-сессии Directus для управления галереей.

Directus здесь подменяется: проверяем контракт нашего API — без сессии 401,
не-админ 403, cookie HttpOnly + CSRF, Bearer-токен и logout.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from admin import main as gallery_main


ADMIN_USER = {
    "id": "admin-id",
    "email": "admin@example.test",
    "first_name": "Админ",
    "last_name": "Directus",
    "role": {"id": "admin-role", "name": "Administrator"},
}
EDITOR_USER = {
    "id": "editor-id",
    "email": "editor@example.test",
    "role": {"id": "editor-role", "name": "Editor"},
}


@pytest.fixture()
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setattr(gallery_main, "_COOKIE_SECURE", False)
    monkeypatch.setattr(gallery_main, "GALLERY_FOLDERS_FILE", str(tmp_path / "folders.json"))
    monkeypatch.setattr(gallery_main, "_ADMIN_SESSIONS", {})
    monkeypatch.setattr(gallery_main, "_LOGIN_FAILS", {})

    def fake_login(email, password):
        if email == "admin@example.test" and password == "correct":
            return {"access_token": "admin-token", "refresh_token": "refresh-token", "expires": 900000}
        if email == "editor@example.test" and password == "correct":
            return {"access_token": "editor-token", "refresh_token": "editor-refresh", "expires": 900000}
        raise gallery_main._DirectusAuthError(401, "Invalid credentials")

    def fake_me(token):
        if token == "admin-token":
            return ADMIN_USER
        if token == "editor-token":
            return EDITOR_USER
        raise gallery_main._DirectusAuthError(401, "Invalid token")

    monkeypatch.setattr(gallery_main, "_directus_login", fake_login)
    monkeypatch.setattr(gallery_main, "_directus_me", fake_me)
    monkeypatch.setattr(gallery_main, "_directus_refresh", lambda token: {
        "access_token": "admin-token", "refresh_token": "refresh-token", "expires": 900000,
    })
    return TestClient(gallery_main.app)


@pytest.fixture()
def anon_client(tmp_path, monkeypatch):
    monkeypatch.setattr(gallery_main, "_COOKIE_SECURE", False)
    monkeypatch.setattr(gallery_main, "GALLERY_FOLDERS_FILE", str(tmp_path / "folders.json"))
    monkeypatch.setattr(gallery_main, "_ADMIN_SESSIONS", {})
    monkeypatch.setattr(gallery_main, "_LOGIN_FAILS", {})
    return TestClient(gallery_main.app)


def test_gallery_api_without_session_is_401(anon_client):
    response = anon_client.get("/gallery-api/folders")
    assert response.status_code == 401
    assert "авторизация" in response.json()["detail"].lower()


def test_login_rejects_non_admin(auth_client):
    response = auth_client.post(
        "/gallery-auth/login",
        json={"email": "editor@example.test", "password": "correct"},
    )
    assert response.status_code == 403
    assert "администратор" in response.json()["detail"].lower()
    assert "jnn_gallery_sid" not in auth_client.cookies


def test_login_rejects_foreign_origin(auth_client):
    response = auth_client.post(
        "/gallery-auth/login",
        json={"email": "admin@example.test", "password": "correct"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_login_rejects_wrong_password(auth_client):
    response = auth_client.post(
        "/gallery-auth/login",
        json={"email": "admin@example.test", "password": "wrong"},
    )
    assert response.status_code == 401


def test_login_set_httponly_cookie_and_me_works(auth_client):
    response = auth_client.post(
        "/gallery-auth/login",
        json={"email": "admin@example.test", "password": "correct"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "admin@example.test"
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("jnn_gallery_sid="))
    csrf_cookie = next(c for c in cookies if c.startswith("jnn_gallery_csrf="))
    assert "httponly" in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()
    assert auth_client.get("/gallery-auth/me").status_code == 200
    assert auth_client.get("/gallery-api/folders").status_code == 200


def test_cookie_mutation_requires_csrf_and_allowed_origin(auth_client):
    auth_client.post(
        "/gallery-auth/login",
        json={"email": "admin@example.test", "password": "correct"},
    )
    assert auth_client.post("/gallery-api/folders", json={"name": "Без CSRF"}).status_code == 403

    csrf = auth_client.cookies.get("jnn_gallery_csrf")
    allowed = auth_client.post(
        "/gallery-api/folders",
        json={"name": "Корень"},
        headers={"X-CSRF-Token": csrf, "Origin": "https://admin.jnnfactory.online"},
    )
    assert allowed.status_code == 200

    evil = auth_client.post(
        "/gallery-api/folders",
        json={"name": "Чужой origin"},
        headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"},
    )
    assert evil.status_code == 403


def test_bearer_admin_token_works_without_cookie(anon_client, monkeypatch):
    monkeypatch.setattr(gallery_main, "_directus_me", lambda token: ADMIN_USER if token == "admin-token" else (_ for _ in ()).throw(
        gallery_main._DirectusAuthError(401, "bad")
    ))
    response = anon_client.get(
        "/gallery-api/folders",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200


def test_bearer_editor_token_is_403(anon_client, monkeypatch):
    monkeypatch.setattr(gallery_main, "_directus_me", lambda token: EDITOR_USER)
    response = anon_client.get(
        "/gallery-api/folders",
        headers={"Authorization": "Bearer editor-token"},
    )
    assert response.status_code == 403


def test_logout_invalidates_session(auth_client):
    auth_client.post(
        "/gallery-auth/login",
        json={"email": "admin@example.test", "password": "correct"},
    )
    csrf = auth_client.cookies.get("jnn_gallery_csrf")
    response = auth_client.post(
        "/gallery-auth/logout",
        headers={"X-CSRF-Token": csrf, "Origin": "https://admin.jnnfactory.online"},
    )
    assert response.status_code == 200
    assert auth_client.get("/gallery-api/folders").status_code == 401


def test_gallery_page_is_served_without_management_data(auth_client):
    response = auth_client.get("/gallery")
    assert response.status_code == 200
    assert "Вход администратора" in response.text
    assert "gallery/static/gallery-admin.js" in response.text
    assert "X-Gallery-Key" not in response.text


def test_public_gallery_paths_do_not_exist(auth_client):
    assert auth_client.get("/gallery.html").status_code == 404
    assert auth_client.post("/gallery-api/publish", json={"slug": "x"}).status_code == 401


def test_publish_webhook_requires_its_own_secret(anon_client, monkeypatch):
    monkeypatch.setattr(gallery_main, "PUBLISH_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setattr(gallery_main._publish, "api_publish", lambda payload: {"ok": True})

    assert anon_client.post("/webhooks/directus/publish", json={"slug": "x"}).status_code == 401
    assert anon_client.post(
        "/webhooks/directus/publish",
        json={"slug": "x"},
        headers={"X-Webhook-Secret": "wrong"},
    ).status_code == 401
    ok = anon_client.post(
        "/webhooks/directus/publish",
        json={"slug": "x"},
        headers={"X-Webhook-Secret": "webhook-secret"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"ok": True}
