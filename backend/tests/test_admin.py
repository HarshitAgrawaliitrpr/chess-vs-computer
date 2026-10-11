"""Admin route: inert without ADMIN_TOKEN, guarded by it when set."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_admin_users_404_without_admin_token() -> None:
    os.environ.pop("ADMIN_TOKEN", None)  # normal operation: endpoint does not exist
    response = client.get("/api/admin/users", params={"token": "anything"})
    assert response.status_code == 404


def test_admin_users_403_with_wrong_token(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "sekrit")
    response = client.get("/api/admin/users", params={"token": "wrong"})
    assert response.status_code == 403


def test_admin_users_lists_accounts_with_correct_token(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "sekrit")
    response = client.get("/api/admin/users", params={"token": "sekrit"})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == len(body["users"])
    for user in body["users"]:
        assert set(user) == {"id", "name", "email", "provider", "created_at", "games"}
        assert "password_hash" not in user
