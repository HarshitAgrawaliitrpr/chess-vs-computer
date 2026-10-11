"""Auth + game-history API tests (email, guest, Google-config, saved games)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _unique_email() -> str:
    return f"player-{uuid.uuid4().hex[:10]}@example.com"


def _register(**overrides) -> dict:
    payload = {"email": _unique_email(), "name": "Mia", "password": "castlerook1", **overrides}
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_auth_config_reports_google_disabled_locally() -> None:
    response = client.get("/api/auth/config")
    assert response.status_code == 200
    body = response.json()
    assert body["google_enabled"] is False
    assert body["google_client_id"] is None


def test_google_login_unconfigured() -> None:
    response = client.post("/api/auth/google", json={"credential": "x" * 40})
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Email register / login
# ---------------------------------------------------------------------------


def test_register_returns_token_and_user() -> None:
    body = _register()
    assert body["token"]
    user = body["user"]
    assert user["email"].endswith("@example.com")
    assert user["provider"] == "email"

    me = client.get("/api/auth/me", headers=_auth(body["token"]))
    assert me.status_code == 200
    assert me.json()["id"] == user["id"]
    assert me.json()["email"] == user["email"]


def test_register_duplicate_email_conflicts() -> None:
    email = _unique_email()
    _register(email=email)
    response = client.post(
        "/api/auth/register",
        json={"email": email, "name": "Dup", "password": "castlerook1"},
    )
    assert response.status_code == 409


def test_register_rejects_short_password() -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": _unique_email(), "name": "Weak", "password": "short"},
    )
    assert response.status_code == 422


def test_register_rejects_invalid_email() -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "name": "Weird", "password": "castlerook1"},
    )
    assert response.status_code == 422


def test_login_round_trip() -> None:
    email = _unique_email()
    _register(email=email, password="correct-horse1")
    response = client.post(
        "/api/auth/login", json={"email": email, "password": "correct-horse1"}
    )
    assert response.status_code == 200
    assert response.json()["token"]
    assert response.json()["user"]["email"] == email


def test_login_wrong_password_rejected() -> None:
    email = _unique_email()
    _register(email=email)
    response = client.post(
        "/api/auth/login", json={"email": email, "password": "wrong-password1"}
    )
    assert response.status_code == 401


def test_login_unknown_email_rejected() -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": _unique_email(), "password": "whatever-123"},
    )
    assert response.status_code == 401


def test_me_requires_a_token() -> None:
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=_auth("not-a-token")).status_code == 401


# ---------------------------------------------------------------------------
# Guest
# ---------------------------------------------------------------------------


def test_guest_login_creates_guest_user() -> None:
    response = client.post("/api/auth/guest", json={})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["provider"] == "guest"
    assert body["user"]["name"].startswith("Guest-")
    assert body["user"]["email"] is None

    me = client.get("/api/auth/me", headers=_auth(body["token"]))
    assert me.status_code == 200
    assert me.json()["provider"] == "guest"


def test_guest_login_accepts_custom_name() -> None:
    response = client.post("/api/auth/guest", json={"name": "Midnight Owl"})
    assert response.status_code == 201
    assert response.json()["user"]["name"] == "Midnight Owl"


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


def test_games_require_authentication() -> None:
    assert client.get("/api/games").status_code == 401
    payload = {
        "pgn": '1. e4 e5 *',
        "result": "win",
        "player_color": "w",
        "difficulty": "easy",
        "moves_count": 2,
    }
    assert client.post("/api/games", json=payload).status_code == 401


def test_saved_games_are_listed_for_their_owner() -> None:
    body = _register()
    headers = _auth(body["token"])
    payload = {
        "pgn": '[Event "Test"]\n1. e4 e5 2. Qh5 Nc6 3. Qxf7# 1-0',
        "result": "win",
        "result_detail": "checkmate",
        "player_color": "w",
        "difficulty": "hard",
        "moves_count": 5,
    }
    response = client.post("/api/games", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["result"] == "win"
    assert saved["id"]

    listing = client.get("/api/games", headers=headers)
    assert listing.status_code == 200
    assert any(game["id"] == saved["id"] for game in listing.json())


def test_guests_can_save_games() -> None:
    guest = client.post("/api/auth/guest", json={}).json()
    headers = _auth(guest["token"])
    payload = {
        "pgn": "1. d4 d5 *",
        "result": "draw",
        "player_color": "b",
        "difficulty": "medium",
        "moves_count": 2,
    }
    response = client.post("/api/games", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    assert client.get("/api/games", headers=headers).json()


def test_game_result_validation() -> None:
    body = _register()
    headers = _auth(body["token"])
    payload = {
        "pgn": "x",
        "result": "banana",
        "player_color": "w",
        "difficulty": "easy",
        "moves_count": 1,
    }
    assert client.post("/api/games", json=payload, headers=headers).status_code == 422
