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
    """
    CREATE TABLE IF NOT EXISTS online_games (
        id TEXT PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        white_id TEXT NOT NULL,
        black_id TEXT,
        status TEXT NOT NULL,
        fen TEXT NOT NULL,
        pgn TEXT NOT NULL,
        last_uci TEXT,
        winner TEXT,
        result_detail TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_online_games_players "
    "ON online_games(white_id, black_id, status)",
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
        _migrate_games_table()
        _schema_ready = True


def _migrate_games_table() -> None:
    """Additive migrations for databases created before the column existed."""
    rows = db.query("PRAGMA table_info(games)")
    columns = {row[1] for row in rows}
    if "opponent" not in columns:
        db.execute("ALTER TABLE games ADD COLUMN opponent TEXT")


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
    "opponent",
)


def _game_from_row(row: Tuple[Any, ...]) -> Dict[str, Any]:
    return dict(zip(_GAME_COLS, row[: len(_GAME_COLS)]))


def insert_game(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_ready()
    game_id = new_id()
    created = utc_now()
    db.execute(
        "INSERT INTO games (id, user_id, pgn, result, result_detail, player_color, difficulty, "
        "moves_count, created_at, opponent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            payload.get("opponent"),
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
        "opponent": payload.get("opponent"),
    }


def list_games(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    ensure_ready()
    rows = db.query(
        "SELECT id, pgn, result, result_detail, player_color, difficulty, moves_count, "
        "created_at, opponent FROM games WHERE user_id = ? "
        "ORDER BY created_at DESC, id DESC LIMIT ?",
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


# ---------------------------------------------------------------------------
# Online multiplayer games
# ---------------------------------------------------------------------------

_ONLINE_COLS = (
    "id",
    "code",
    "white_id",
    "black_id",
    "status",
    "fen",
    "pgn",
    "last_uci",
    "winner",
    "result_detail",
    "created_at",
    "updated_at",
)


def _online_from_row(row: Tuple[Any, ...]) -> Dict[str, Any]:
    return dict(zip(_ONLINE_COLS, row[: len(_ONLINE_COLS)]))


_ONLINE_SELECT = (
    "SELECT id, code, white_id, black_id, status, fen, pgn, last_uci, winner, "
    "result_detail, created_at, updated_at FROM online_games WHERE "
)


def create_online_game(*, white_id: str, code: str, fen: str, pgn: str) -> Dict[str, Any]:
    ensure_ready()
    game_id = new_id()
    now = utc_now()
    db.execute(
        "INSERT INTO online_games (id, code, white_id, status, fen, pgn, created_at, updated_at) "
        "VALUES (?, ?, ?, 'waiting', ?, ?, ?, ?)",
        (game_id, code, white_id, fen, pgn, now, now),
    )
    return get_online_game(game_id)


def get_online_game(game_id: str) -> Optional[Dict[str, Any]]:
    ensure_ready()
    rows = db.query(_ONLINE_SELECT + "id = ?", (game_id,))
    return _online_from_row(rows[0]) if rows else None


def find_online_game_by_code(code: str) -> Optional[Dict[str, Any]]:
    ensure_ready()
    rows = db.query(_ONLINE_SELECT + "code = ?", (code,))
    return _online_from_row(rows[0]) if rows else None


def join_online_game(game_id: str, black_id: str) -> int:
    """Assign the second player atomically; returns 0 if the seat was taken."""
    ensure_ready()
    now = utc_now()
    return db.execute(
        "UPDATE online_games SET black_id = ?, status = 'active', updated_at = ? "
        "WHERE id = ? AND status = 'waiting' AND black_id IS NULL",
        (black_id, now, game_id),
    )


def update_online_position(
    game_id: str,
    *,
    fen: str,
    pgn: str,
    last_uci: Optional[str],
    status: str,
    winner: Optional[str],
    result_detail: Optional[str],
    expected_fen: Optional[str] = None,
) -> int:
    """Apply a new position; returns rows updated (0 = stale read lost the race)."""
    ensure_ready()
    where = "id = ?"
    params: List[Any] = [fen, pgn, last_uci, status, winner, result_detail, utc_now(), game_id]
    if expected_fen is not None:
        where += " AND fen = ?"
        params.append(expected_fen)
    return db.execute(
        "UPDATE online_games SET fen = ?, pgn = ?, last_uci = ?, status = ?, winner = ?, "
        f"result_detail = ?, updated_at = ? WHERE {where}",
        tuple(params),
    )


def cancel_online_game(game_id: str, white_id: str) -> int:
    """Cancel a waiting game (creator only); returns 0 if it was not waiting."""
    ensure_ready()
    return db.execute(
        "UPDATE online_games SET status = 'cancelled', updated_at = ? "
        "WHERE id = ? AND white_id = ? AND status = 'waiting'",
        (utc_now(), game_id, white_id),
    )


def record_online_game_results(
    *,
    white_id: str,
    black_id: Optional[str],
    white_name: str,
    black_name: Optional[str],
    pgn: str,
    moves_count: int,
    winner: Optional[str],
    result_detail: Optional[str],
) -> None:
    """Persist the finished game into `games` for BOTH players.

    Recorded as difficulty='online' so the leaderboard's difficulty filter and
    the history panel pick them up with zero extra plumbing.
    """
    for user_id, color, opponent in (
        (white_id, "w", black_name),
        (black_id, "b", white_name),
    ):
        if not user_id:
            continue
        if winner is None:
            result = "draw"
        elif winner == color:
            result = "win"
        else:
            result = "loss"
        insert_game(
            user_id,
            {
                "pgn": pgn,
                "result": result,
                "result_detail": result_detail,
                "player_color": color,
                "difficulty": "online",
                "moves_count": moves_count,
                "opponent": opponent,
            },
        )
