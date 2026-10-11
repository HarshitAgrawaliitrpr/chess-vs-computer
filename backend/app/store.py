"""Repository layer: schema management plus user/game row access.

Rows are plain dicts shaped like the API models, so routes can pass them
straight into Pydantic response models.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import db

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        name TEXT NOT NULL,
        provider TEXT NOT NULL,
        password_hash TEXT,
        google_sub TEXT UNIQUE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS games (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        pgn TEXT NOT NULL,
        result TEXT NOT NULL,
        result_detail TEXT,
        player_color TEXT NOT NULL,
        difficulty TEXT NOT NULL,
        moves_count INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_games_user ON games(user_id, created_at DESC)",
)

# `NULL` emails (guests) are allowed to repeat: SQLite UNIQUE treats NULLs as
# distinct, and Turso runs the same engine.

_schema_lock = threading.Lock()
_schema_ready = False


class DatabaseUnavailableError(db.DatabaseError):
    """The database could not be initialised (no DATABASE_URL, read-only FS...)."""


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_schema() -> None:
    """Create tables/indexes once per process; safe to call on every request."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        for statement in _SCHEMA:
            db.execute(statement)
        _schema_ready = True


def ensure_ready() -> None:
    """ensure_schema(), translating failures into DatabaseUnavailableError."""
    try:
        ensure_schema()
    except db.DatabaseError as exc:
        raise DatabaseUnavailableError(str(exc)) from exc


def is_unique_violation(exc: Exception) -> bool:
    text = str(exc).upper()
    return "UNIQUE" in text or "CONSTRAINT" in text


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

_USER_COLS = ("id", "email", "name", "provider", "created_at")


def _user_from_row(row: Tuple[Any, ...]) -> Dict[str, Any]:
    return dict(zip(_USER_COLS, row[: len(_USER_COLS)]))


_USER_SELECT = "SELECT id, email, name, provider, created_at FROM users WHERE "


def create_user(
    *,
    name: str,
    provider: str,
    email: Optional[str] = None,
    password_hash: Optional[str] = None,
    google_sub: Optional[str] = None,
) -> Dict[str, Any]:
    ensure_ready()
    user_id = new_id()
    created = utc_now()
    db.execute(
        "INSERT INTO users (id, email, name, provider, password_hash, google_sub, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, email, name, provider, password_hash, google_sub, created),
    )
    return {"id": user_id, "email": email, "name": name, "provider": provider, "created_at": created}


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    ensure_ready()
    rows = db.query(_USER_SELECT + "id = ?", (user_id,))
    return _user_from_row(rows[0]) if rows else None


def get_user_with_password(email: str) -> Optional[Tuple[Dict[str, Any], str]]:
    ensure_ready()
    rows = db.query(
        "SELECT id, email, name, provider, created_at, password_hash FROM users WHERE email = ?",
        (email,),
    )
    if not rows:
        return None
    row = rows[0]
    user = dict(zip(_USER_COLS, row[:5]))
    return user, row[5]


def get_user_by_google_sub(google_sub: str) -> Optional[Dict[str, Any]]:
    ensure_ready()
    rows = db.query(_USER_SELECT + "google_sub = ?", (google_sub,))
    return _user_from_row(rows[0]) if rows else None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    ensure_ready()
    rows = db.query(_USER_SELECT + "email = ?", (email,))
    return _user_from_row(rows[0]) if rows else None


def attach_google_sub(user_id: str, google_sub: str) -> None:
    """Link an existing account to a Google identity (first Google sign-in)."""
    db.execute(
        "UPDATE users SET google_sub = ? WHERE id = ? AND google_sub IS NULL",
        (google_sub, user_id),
    )


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------

_GAME_COLS = (
    "id",
    "pgn",
    "result",
    "result_detail",
    "player_color",
    "difficulty",
    "moves_count",
    "created_at",
)


def _game_from_row(row: Tuple[Any, ...]) -> Dict[str, Any]:
    return dict(zip(_GAME_COLS, row[: len(_GAME_COLS)]))


def insert_game(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_ready()
    game_id = new_id()
    created = utc_now()
    db.execute(
        "INSERT INTO games (id, user_id, pgn, result, result_detail, player_color, difficulty, "
        "moves_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            game_id,
            user_id,
            payload["pgn"],
            payload["result"],
            payload.get("result_detail"),
            payload["player_color"],
            payload["difficulty"],
            payload.get("moves_count", 0),
            created,
        ),
    )
    return {
        "id": game_id,
        "pgn": payload["pgn"],
        "result": payload["result"],
        "result_detail": payload.get("result_detail"),
        "player_color": payload["player_color"],
        "difficulty": payload["difficulty"],
        "moves_count": payload.get("moves_count", 0),
        "created_at": created,
    }


def list_games(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    ensure_ready()
    rows = db.query(
        "SELECT id, pgn, result, result_detail, player_color, difficulty, moves_count, created_at "
        "FROM games WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        (user_id, limit),
    )
    return [_game_from_row(row) for row in rows]


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


def leaderboard(difficulty: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Top players ranked by classic chess points (win=1, draw=0.5, loss=0).

    One aggregate query over the games table; ties break on wins, then games
    played, then name. An optional difficulty filter restricts the ranking to
    games played at that level.
    """
    ensure_ready()
    where = "WHERE g.difficulty = ?" if difficulty else ""
    params: List[Any] = [difficulty] if difficulty else []
    params.append(limit)
    rows = db.query(
        "SELECT u.id, u.name, u.provider, COUNT(*) AS games, "
        "SUM(CASE WHEN g.result = 'win' THEN 1 ELSE 0 END) AS wins, "
        "SUM(CASE WHEN g.result = 'draw' THEN 1 ELSE 0 END) AS draws, "
        "SUM(CASE WHEN g.result = 'loss' THEN 1 ELSE 0 END) AS losses "
        f"FROM games g JOIN users u ON u.id = g.user_id {where} "
        "GROUP BY u.id, u.name, u.provider "
        "ORDER BY SUM(CASE WHEN g.result = 'win' THEN 1.0 "
        "WHEN g.result = 'draw' THEN 0.5 ELSE 0.0 END) DESC, "
        "wins DESC, games DESC, u.name ASC "
        "LIMIT ?",
        tuple(params),
    )
    entries: List[Dict[str, Any]] = []
    for row in rows:
        games = int(row[3] or 0)
        wins = int(row[4] or 0)
        draws = int(row[5] or 0)
        losses = int(row[6] or 0)
        entries.append(
            {
                "user_id": row[0],
                "name": row[1],
                "provider": row[2],
                "games": games,
                "wins": wins,
                "draws": draws,
                "losses": losses,
                "points": wins + 0.5 * draws,
                "win_rate": round(100.0 * wins / games, 1) if games else 0.0,
            }
        )
    return entries
