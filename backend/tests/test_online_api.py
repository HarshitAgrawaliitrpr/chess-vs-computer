"""Online multiplayer API tests: lobby, validation, results, access control."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(name: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"on-{uuid.uuid4().hex[:10]}@example.com",
            "name": name,
            "password": "castlerook1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create(token: str) -> dict:
    response = client.post("/api/online/games", headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()


def _create_and_join() -> tuple[dict, dict, dict]:
    """Two players + the waiting game (returned as creator, joiner, game state)."""
    alice = _register("Alice")
    bob = _register("Bob")
    created = _create(alice["token"])
    joined = client.post(
        "/api/online/games/join",
        headers=_auth(bob["token"]),
        json={"code": created["code"].lower()},  # codes are case-insensitive
    )
    assert joined.status_code == 200, joined.text
    return alice, bob, joined.json()


def _move(token: str, game_id: str, source: str, target: str) -> dict:
    return client.post(
        f"/api/online/games/{game_id}/move",
        headers=_auth(token),
        json={"from": source, "to": target},
    )


# ---------------------------------------------------------------------------
# lobby
# ---------------------------------------------------------------------------
def test_create_game_returns_waiting_state_for_white() -> None:
    session = _register("Creator")
    game = _create(session["token"])

    assert game["status"] == "waiting"
    assert len(game["code"]) == 6
    assert game["my_color"] == "w"
    assert game["white_name"] == "Creator"
    assert game["black_name"] is None
    assert game["turn"] == "w"
    assert game["moves"] == []
    assert game["result"] is None


def test_join_assigns_black_and_activates() -> None:
    alice, bob, game = _create_and_join()

    assert game["status"] == "active"
    assert game["my_color"] == "b"  # viewed from Bob (the joiner)
    assert game["black_name"] == "Bob"
    assert game["opponent_name"] == "Alice"

    # The creator sees the same game from the other side via polling.
    state = client.get(
        f"/api/online/games/{game['id']}", headers=_auth(alice["token"])
    ).json()
    assert state["my_color"] == "w"
    assert state["opponent_name"] == "Bob"
    assert state["status"] == "active"


def test_join_errors_unknown_own_and_full() -> None:
    session = _register("Solo")

    unknown = client.post(
        "/api/online/games/join", headers=_auth(session["token"]), json={"code": "ZZZZZZ"}
    )
    assert unknown.status_code == 404

    own = _create(session["token"])
    self_join = client.post(
        "/api/online/games/join", headers=_auth(session["token"]), json={"code": own["code"]}
    )
    assert self_join.status_code == 409

    _, _, started = _create_and_join()
    other = _register("Late")
    full = client.post(
        "/api/online/games/join",
        headers=_auth(other["token"]),
        json={"code": started["code"]},
    )
    assert full.status_code == 409

    too_short = client.post(
        "/api/online/games/join", headers=_auth(session["token"]), json={"code": "ABC"}
    )
    assert too_short.status_code == 422


# ---------------------------------------------------------------------------
# moves
# ---------------------------------------------------------------------------
def test_legal_move_updates_position_and_turn() -> None:
    alice, bob, game = _create_and_join()

    played = _move(alice["token"], game["id"], "e2", "e4")
    assert played.status_code == 200, played.text
    body = played.json()
    assert body["turn"] == "b"
    assert body["moves"] == ["e4"]
    assert body["last_move"] == "e2e4"
    assert "e4" in body["pgn"]
    assert body["fen"].startswith("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b")


def test_move_rejects_out_of_turn_illegal_and_strangers() -> None:
    alice, bob, game = _create_and_join()

    out_of_turn = _move(bob["token"], game["id"], "e7", "e5")  # white to move first
    assert out_of_turn.status_code == 409

    illegal = _move(alice["token"], game["id"], "e2", "e5")  # not a legal move
    assert illegal.status_code == 422

    stranger = _register("Stranger")
    no_access = _move(stranger["token"], game["id"], "e2", "e4")
    assert no_access.status_code == 404

    peek = client.get(f"/api/online/games/{game['id']}", headers=_auth(stranger["token"]))
    assert peek.status_code == 404


def test_fools_mate_finishes_and_records_for_both_players() -> None:
    alice, bob, game = _create_and_join()
    gid = game["id"]

    # 1. f3 e5 2. g4 Qh4#
    assert _move(alice["token"], gid, "f2", "f3").status_code == 200
    assert _move(bob["token"], gid, "e7", "e5").status_code == 200
    assert _move(alice["token"], gid, "g2", "g4").status_code == 200
    final = _move(bob["token"], gid, "d8", "h4")
    assert final.status_code == 200, final.text

    black_view = final.json()
    assert black_view["status"] == "over"
    assert black_view["winner"] == "b"
    assert black_view["result_detail"] == "checkmate"
    assert black_view["result"] == "win"  # Bob is black
    assert len(black_view["moves"]) == 4

    white_view = client.get(f"/api/online/games/{gid}", headers=_auth(alice["token"])).json()
    assert white_view["result"] == "loss"
    assert white_view["status"] == "over"

    # Both players now have the game in history as an 'online' match.
    for token, expected_result, expected_opponent in (
        (alice["token"], "loss", "Bob"),
        (bob["token"], "win", "Alice"),
    ):
        rows = client.get("/api/games", headers=_auth(token)).json()
        match = [row for row in rows if row["difficulty"] == "online"]
        assert match, "finished online game missing from history"
        assert match[0]["result"] == expected_result
        assert match[0]["opponent"] == expected_opponent
        assert match[0]["moves_count"] == 4
        assert match[0]["result_detail"] == "checkmate"

    # The finished game refuses further moves.
    assert _move(alice["token"], gid, "a2", "a3").status_code == 409


# ---------------------------------------------------------------------------
# resign / cancel
# ---------------------------------------------------------------------------
def test_resign_gives_the_win_to_the_opponent() -> None:
    alice, bob, game = _create_and_join()
    assert _move(alice["token"], game["id"], "e2", "e4").status_code == 200

    resigned = client.post(
        f"/api/online/games/{game['id']}/resign", headers=_auth(alice["token"])
    )
    assert resigned.status_code == 200, resigned.text
    body = resigned.json()
    assert body["status"] == "over"
    assert body["winner"] == "b"
    assert body["result_detail"] == "resignation"
    assert body["result"] == "loss"  # Alice resigned

    rows = client.get("/api/games", headers=_auth(bob["token"])).json()
    online = [row for row in rows if row["difficulty"] == "online"]
    assert online and online[0]["result"] == "win"
    assert online[0]["result_detail"] == "resignation"


def test_creator_can_cancel_only_while_waiting() -> None:
    alice = _register("Waiter")
    game = _create(alice["token"])

    cancelled = client.post(
        f"/api/online/games/{game['id']}/cancel", headers=_auth(alice["token"])
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # A cancelled game cannot be joined...
    other = _register("Joiner")
    join = client.post(
        "/api/online/games/join",
        headers=_auth(other["token"]),
        json={"code": game["code"]},
    )
    assert join.status_code == 409

    # ...and cancelling twice (or after start) is rejected.
    again = client.post(
        f"/api/online/games/{game['id']}/cancel", headers=_auth(alice["token"])
    )
    assert again.status_code == 409

    _, _, started = _create_and_join()
    late_cancel = client.post(
        f"/api/online/games/{started['id']}/cancel", headers=_auth(alice["token"])
    )
    assert late_cancel.status_code == 404  # Alice is not a participant


def test_creator_polls_while_waiting() -> None:
    alice = _register("Poller")
    game = _create(alice["token"])
    state = client.get(f"/api/online/games/{game['id']}", headers=_auth(alice["token"]))
    assert state.status_code == 200
    assert state.json()["status"] == "waiting"
