"""Owner-only window into the database: which accounts exist, with emails.

Why this exists
---------------
Vercel stores DATABASE_AUTH_TOKEN as a *sensitive* env var - its value is
write-only and can never be read back, not even by the owner through the
API - so the account owner has no way to browse their own data through
Turso/Vercel tooling alone (the dashboard needs a login they may not
have handy). This router is the minimal, opt-in escape hatch:

* If the ``ADMIN_TOKEN`` env var is NOT set, every route here 404s -
  the endpoint effectively does not exist in normal operation.
* When set, ``GET /api/admin/users?token=...`` lists the accounts
  (id, name, email, provider, created_at, game count). Password hashes
  are never returned.

Intended lifecycle: set ADMIN_TOKEN -> make the one call you need ->
delete the env var (and redeploy) -> the endpoint goes dark again.
Token comparison is constant-time; wrong token is 403.
"""

from __future__ import annotations

import hmac
import os
from typing import List

from fastapi import APIRouter, HTTPException, Query

from . import db, store

router = APIRouter(prefix="/api/admin", tags=["admin"])

_DB_UNAVAILABLE = "Database unavailable."


def _require_token(token: str) -> None:
    expected = os.getenv("ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=404, detail="Not found.")
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Forbidden.")


@router.get("/users")
def list_users(token: str = Query(...)) -> dict:
    _require_token(token)
    try:
        store.ensure_ready()
        rows = db.query(
            "SELECT u.id, u.name, u.email, u.provider, u.created_at,"
            " (SELECT COUNT(*) FROM games g WHERE g.user_id = u.id)"
            " AS games"
            " FROM users u ORDER BY u.created_at"
        )
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    users: List[dict] = [
        {
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "provider": row[3],
            "created_at": row[4],
            "games": row[5],
        }
        for row in rows
    ]
    return {"count": len(users), "users": users}
