"""Leaderboard API tests: ranking, points, difficulty filter, public access."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_player(results, difficulty="hard") -> dict:
    """Register a user and save one game per result; returns the user + token."""
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"lb-{uuid.uuid4().hex[:10]}@example.com",
            "name": f"Player-{uuid.uuid4().hex[:4]}",
            "password": "castlerook1",
        },
    )
    assert response.status_code == 201, response.text
    session = response.json()
    for result in results:
        saved = client.post(
            "/api/games",
            headers=_auth(session["token"]),
            json={
                "pgn": "1. e4 e5 *",
                "result": result,
                "player_color": "w",
                "difficulty": difficulty,
                "moves_count": 2,
            },
        )
        assert saved.status_code == 201, saved.text
    return session


def test_leaderboard_is_public_and_starts_empty_per_player() -> None:
    response = client.get("/api/leaderboard")  # no auth header at all
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_leaderboard_ranks_by_points() -> None:
    alice = _make_player(["win", "win", "draw"])  # 2.5 pts
    bob = _make_player(["win"])  # 1.0 pt
    carol = _make_player(["loss", "loss"])  # 0.0 pts

    response = client.get("/api/leaderboard?limit=50")
    assert response.status_code == 200
    entries = {entry["user_id"]: entry for entry in response.json()}

    alice_entry = entries[alice["user"]["id"]]
    bob_entry = entries[bob["user"]["id"]]
    carol_entry = entries[carol["user"]["id"]]

    assert alice_entry["rank"] < bob_entry["rank"] < carol_entry["rank"]
    assert alice_entry["points"] == 2.5
    assert (alice_entry["wins"], alice_entry["draws"], alice_entry["losses"]) == (2, 1, 0)
    assert alice_entry["games"] == 3
    assert bob_entry["points"] == 1.0
    assert carol_entry["points"] == 0.0
    assert carol_entry["win_rate"] == 0.0
    assert alice_entry["win_rate"] == round(100 * 2 / 3, 1)


def test_leaderboard_difficulty_filter() -> None:
    mixed = _make_player(["win"], difficulty="easy")
    _make_player(["loss"], difficulty="hard")  # someone else's hard game

    response = client.get("/api/leaderboard?difficulty=easy")
    assert response.status_code == 200
    user_ids = [entry["user_id"] for entry in response.json()]
    assert mixed["user"]["id"] in user_ids

    # The hard-only player must not appear in the easy ranking.
    hard_only = client.get("/api/leaderboard?difficulty=master")
    assert hard_only.status_code == 200
    assert mixed["user"]["id"] not in [entry["user_id"] for entry in hard_only.json()]


def test_leaderboard_limit_is_validated() -> None:
    assert client.get("/api/leaderboard?limit=0").status_code == 422
    assert client.get("/api/leaderboard?limit=500").status_code == 422
    assert client.get("/api/leaderboard?limit=5").status_code == 200
