"""Leaderboard endpoint: top players by points (win=1, draw=0.5, loss=0).

Public (no auth needed) - the ranking only exposes display names and stats.
An optional `difficulty` query parameter ranks within a single level.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from . import db, store
from .schemas import LeaderboardEntry

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])

_DB_UNAVAILABLE = "Database unavailable - set DATABASE_URL (Turso) to enable the leaderboard."


@router.get("", response_model=List[LeaderboardEntry])
def get_leaderboard(
    difficulty: Optional[str] = Query(None, description="Restrict to one difficulty."),
    limit: int = Query(10, ge=1, le=50),
) -> List[LeaderboardEntry]:
    try:
        rows = store.leaderboard(difficulty=difficulty, limit=limit)
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    return [LeaderboardEntry(rank=index + 1, **row) for index, row in enumerate(rows)]
