"""Connectivity check: run the whole auth + games flow against a REAL Turso
database, then delete every row it created (leaves the DB clean).

Usage (from backend/):
    $env:DATABASE_URL = "libsql://....turso.io"
    $env:DATABASE_AUTH_TOKEN = "..."
    python scripts/turso_smoke.py
"""

from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

assert os.getenv("DATABASE_URL"), "set DATABASE_URL to the Turso URL"
assert os.getenv("DATABASE_AUTH_TOKEN"), "set DATABASE_AUTH_TOKEN"

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
created_user_ids: list[str] = []


def ok(label: str, condition: bool, extra: str = "") -> None:
    print(f"  [{'OK' if condition else 'FAIL'}] {label}" + (f" - {extra}" if extra else ""))
    if not condition:
        sys.exit(1)


print(f"Turso target: {os.getenv('DATABASE_URL')}")

r = client.get("/api/auth/config")
ok("GET /api/auth/config", r.status_code == 200, r.text[:80])

r = client.post("/api/auth/guest", json={})
ok("POST /api/auth/guest", r.status_code == 201, r.text[:120])
guest = r.json()
created_user_ids.append(guest["user"]["id"])
guest_headers = {"Authorization": f"Bearer {guest['token']}"}

r = client.get("/api/auth/me", headers=guest_headers)
ok("GET /api/auth/me (guest token)", r.status_code == 200 and r.json()["provider"] == "guest")

email = f"turso-smoke-{uuid.uuid4().hex[:8]}@example.com"
r = client.post(
    "/api/auth/register", json={"email": email, "name": "Turso Smoke", "password": "castlerook1"}
)
ok("POST /api/auth/register (email)", r.status_code == 201, r.text[:120])
registered = r.json()
created_user_ids.append(registered["user"]["id"])

r = client.post("/api/auth/login", json={"email": email, "password": "castlerook1"})
ok("POST /api/auth/login", r.status_code == 200 and bool(r.json()["token"]))

auth_headers = {"Authorization": f"Bearer {registered['token']}"}
r = client.post(
    "/api/games",
    headers=auth_headers,
    json={
        "pgn": '[Event "Turso smoke"]\n1. e4 e5 2. Qh5 Nc6 3. Qxf7# 1-0',
        "result": "win",
        "result_detail": "checkmate",
        "player_color": "w",
        "difficulty": "hard",
        "moves_count": 5,
    },
)
ok("POST /api/games (email user)", r.status_code == 201, r.text[:120])

r = client.post(
    "/api/games",
    headers=guest_headers,
    json={
        "pgn": "1. d4 d5 *",
        "result": "draw",
        "player_color": "b",
        "difficulty": "easy",
        "moves_count": 2,
    },
)
ok("POST /api/games (guest)", r.status_code == 201, r.text[:120])

r = client.get("/api/games", headers=auth_headers)
games = r.json()
ok("GET /api/games lists the saved game", r.status_code == 200 and len(games) == 1, f"{len(games)} rows")

# --- cleanup: remove exactly what this smoke run created -------------------
for user_id in created_user_ids:
    db.execute("DELETE FROM games WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
r = client.get("/api/games", headers=auth_headers)
ok("cleanup removed the test rows", r.status_code == 401 or r.json() == [])

print("TURSO SMOKE: all checks passed")
