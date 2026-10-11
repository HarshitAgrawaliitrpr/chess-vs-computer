"""Game history endpoints: every finished game is stored for the signed-in user."""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException

from . import db, security, store
from .schemas import GameCreate, GameOut

router = APIRouter(prefix="/api/games", tags=["games"])

_DB_UNAVAILABLE = "Database unavailable - set DATABASE_URL (Turso) to enable game history."


@router.post("", response_model=GameOut, status_code=201)
def save_game(payload: GameCreate, user: Dict = Depends(security.get_current_user)) -> GameOut:
    try:
        game = store.insert_game(user["id"], payload.model_dump())
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    return GameOut(**game)


@router.get("", response_model=List[GameOut])
def list_games(user: Dict = Depends(security.get_current_user)) -> List[GameOut]:
    try:
        games = store.list_games(user["id"])
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    return [GameOut(**game) for game in games]
