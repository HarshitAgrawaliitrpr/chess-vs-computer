"""Print the whole database in plain text - users (with emails), games, online.

The Vercel dashboard masks secret env values and there is deliberately NO API
endpoint that lists user emails (that would leak every account to the public).
This local script is the owner's window into their own data instead.

Usage
-----
    # production Turso DB (get the token from the Turso dashboard -> your DB
    # -> "Tokens" -> create one, or: turso db tokens create <db-name>)
    set DATABASE_URL=https://turso-db-...-turso.io
    set DATABASE_AUTH_TOKEN=eyJ...
    python scripts/view_db.py

    # local dev DB (no env needed - reads ./chess.db)
    python scripts/view_db.py

Read-only: every query is a SELECT.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # noqa: E402

from app import db  # noqa: E402


def table(title: str, columns: list[str], rows: list[tuple]) -> None:
    print(f"\n== {title} ({len(rows)} rows) ==")
    if not rows:
        print("  (empty)")
        return
    widths = [len(c) for c in columns]
    rendered = [[("" if v is None else str(v)) for v in row] for row in rows]
    for row in rendered:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    line = "  " + "  ".join(c.ljust(w) for c, w in zip(columns, widths))
    print(line)
    print("  " + "  ".join("-" * w for w in widths))
    for row in rendered:
        print("  " + "  ".join(cell.ljust(w) for cell, w in zip(row, widths)))


def main() -> None:
    url = db.database_url()
    print(f"database: {url}")
    print(f"auth token: {'set' if db.database_auth_token() else 'not set (file/local?)'}")

    users = db.query(
        "SELECT u.id, u.name, u.email, u.provider, u.created_at,"
        " (SELECT COUNT(*) FROM games g WHERE g.user_id = u.id) AS games"
        " FROM users u ORDER BY u.created_at"
    )
    table("users (id, name, EMAIL, provider, created_at, games)", 
          ["id", "name", "email", "provider", "created_at", "games"], users)

    games = db.query(
        "SELECT g.created_at, u.email, u.name, g.difficulty, g.result,"
        " g.player_color, g.moves_count"
        " FROM games g JOIN users u ON u.id = g.user_id"
        " ORDER BY g.created_at DESC LIMIT 30"
    )
    table("recent engine games (latest 30)",
          ["created_at", "email", "name", "difficulty", "result", "color", "moves"], games)

    online = db.query(
        "SELECT o.created_at, o.updated_at, o.code, o.status, o.winner,"
        " w.name || ' (W) vs ' || COALESCE(b.name, '-') || ' (B)' AS players,"
        " o.last_uci"
        " FROM online_games o"
        " LEFT JOIN users w ON w.id = o.white_id"
        " LEFT JOIN users b ON b.id = o.black_id"
        " ORDER BY o.created_at DESC LIMIT 30"
    )
    table("recent online games (latest 30)",
          ["created_at", "updated_at", "code", "status", "winner", "players", "last_uci"], online)


if __name__ == "__main__":
    main()
