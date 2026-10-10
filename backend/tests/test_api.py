"""API level tests (FastAPI TestClient)."""

from __future__ import annotations

import chess
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

START_FEN = chess.STARTING_FEN


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "chess-engine-api"


def test_difficulties_are_exposed() -> None:
    response = client.get("/api/difficulties")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"easy", "medium", "hard", "master"}
    assert body["easy"]["depth"] == 1
    assert body["hard"]["depth"] >= 5


def test_invalid_fen_is_rejected() -> None:
    response = client.post("/api/engine/move", json={"fen": "not-a-fen", "difficulty": "easy"})
    assert response.status_code == 422


def test_engine_returns_legal_move_from_start_position() -> None:
    response = client.post(
        "/api/engine/move",
        json={"fen": START_FEN, "difficulty": "easy", "time_limit_ms": 300},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    board = chess.Board(START_FEN)
    move = chess.Move.from_uci(body["move"]["uci"])
    assert move in list(board.legal_moves)

    board.push_uci(body["move"]["uci"])
    assert body["fen"] == board.fen()
    assert body["score_type"] in ("cp", "mate")
    assert body["depth"] >= 1
    assert body["nodes"] > 0


def test_difficulty_changes_search_depth() -> None:
    easy = client.post(
        "/api/engine/move", json={"fen": START_FEN, "difficulty": "easy", "time_limit_ms": 300}
    ).json()
    hard = client.post(
        "/api/engine/move", json={"fen": START_FEN, "difficulty": "hard", "time_limit_ms": 3000}
    ).json()
    assert hard["depth"] >= easy["depth"]


def test_mate_in_one_via_api() -> None:
    fen = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
    response = client.post(
        "/api/engine/move", json={"fen": fen, "difficulty": "medium", "depth": 4, "time_limit_ms": 5000}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["score_type"] == "mate"
    board = chess.Board(fen)
    board.push_uci(body["move"]["uci"])
    assert board.is_checkmate()


def test_game_over_position_returns_conflict() -> None:
    # Stalemate position: black to move, no legal moves, not in check.
    fen = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
    response = client.post("/api/engine/move", json={"fen": fen, "difficulty": "easy"})
    assert response.status_code == 409