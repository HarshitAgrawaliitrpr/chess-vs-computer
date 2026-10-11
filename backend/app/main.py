"""FastAPI application exposing the chess engine over HTTP.

Endpoints
--------
GET  /api/health          liveness probe used by the Docker/CI pipeline
POST /api/engine/move     compute the best move for the side to move in a FEN
GET  /api/auth/config     whether Google sign-in is configured (+ client id)
POST /api/auth/register   create an email/password account
POST /api/auth/login      email/password sign-in
POST /api/auth/google     sign in with a Google Identity Services ID token
POST /api/auth/guest      anonymous play (still gets history + a JWT)
GET  /api/auth/me         the authenticated user
POST /api/games           store a finished game
GET  /api/games           the authenticated user's recent games
GET  /api/leaderboard     top players by points (optional ?difficulty=)
"""

from __future__ import annotations

import os
from typing import List, Optional

import chess
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .engine.search import MATE_THRESHOLD, Searcher
from .engine.strengths import PROFILES, resolve_profile
from .routes_auth import router as auth_router
from .routes_games import router as games_router
from .routes_leaderboard import router as leaderboard_router
from .schemas import (
    GameOverModel,
    HealthResponse,
    MoveInfo,
    MoveRequest,
    SearchResultModel,
)

VERSION = "1.0.0"

app = FastAPI(
    title="Chess vs Computer - Engine API",
    version=VERSION,
    description="Minimax + alpha-beta chess engine with adjustable difficulty.",
)

_allowed_origins: List[str] = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _describe_game_state(board: chess.Board) -> tuple[str, Optional[str]]:
    """Map a python-chess terminal/holdings state onto the API status enum."""
    if board.is_checkmate():
        winner = "white" if board.turn == chess.BLACK else "black"
        return "checkmate", winner
    if board.is_stalemate():
        return "stalemate", None
    if board.is_insufficient_material():
        return "draw_insufficient_material", None
    if board.is_repetition():
        return "draw_repetition", None
    if board.halfmove_clock >= 100:
        return "draw_50_moves", None
    if board.is_check():
        return "check", None
    return "active", None


def _to_move_info(board_before: chess.Board, move: chess.Move) -> MoveInfo:
    san = board_before.san(move)
    return MoveInfo(
        uci=move.uci(),
        san=san,
        **{"from": chess.square_name(move.from_square), "to": chess.square_name(move.to_square)},
        promotion=chess.piece_symbol(move.promotion) if move.promotion else None,
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="chess-engine-api", version=VERSION)


@app.get("/api/difficulties")
def difficulties() -> dict:
    return {
        name: {"label": p.label, "depth": p.max_depth, "time_limit_ms": p.time_limit_ms, "elo": p.elo}
        for name, p in PROFILES.items()
    }


@app.post("/api/engine/move", response_model=SearchResultModel)
def engine_move(request: MoveRequest) -> SearchResultModel:
    try:
        board = chess.Board(request.fen)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid FEN: {exc}") from exc

    status, _winner = _describe_game_state(board)
    if status not in ("active", "check"):
        # Nothing to search: hand back the terminal state.
        raise HTTPException(status_code=409, detail=f"Game is over ({status}); no move available.")

    profile = resolve_profile(request.difficulty, request.depth, request.time_limit_ms)

    searcher = Searcher(
        board,
        max_depth=profile.max_depth,
        time_limit_ms=profile.time_limit_ms,
        noise_cp=profile.noise_cp,
    )
    result = searcher.search()

    if result.move is None:  # pragma: no cover - guarded by status check above
        raise HTTPException(status_code=409, detail="No legal moves available.")

    board.push(result.move)
    new_fen = board.fen()

    pv_sans: List[str] = []
    pv_board = chess.Board(request.fen)
    for pv_move in result.pv:
        pv_sans.append(pv_board.san(pv_move))
        pv_board.push(pv_move)

    is_mate = abs(result.score) >= MATE_THRESHOLD
    return SearchResultModel(
        move=_to_move_info(chess.Board(request.fen), result.move),
        fen=new_fen,
        score=result.score,
        score_type="mate" if is_mate else "cp",
        mate_in=result.mate_in,
        depth=result.depth,
        nodes=result.nodes,
        time_ms=round(result.time_ms, 2),
        pv=pv_sans,
        difficulty=profile.name,
        elo_estimate=profile.elo,
    )


# ---------------------------------------------------------------------------
# Accounts + game history (Turso/libSQL). Registered before the static mount
# so `/api/*` always wins; if the database is unconfigured only these routes
# degrade to 503 - the engine keeps serving.
# ---------------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(games_router)
app.include_router(leaderboard_router)


# ---------------------------------------------------------------------------
# Single-server frontend hosting (Vercel and all-in-one deployments).
#
# Vercel loads the root `main.py` entrypoint, which re-exports this `app`, and
# the build command produces `frontend/dist`. The routes above are declared
# before this mount, so `/api/*` always wins; everything else is the React app.
# On the normal dev flow (Vite dev server + uvicorn) the block only activates
# if you have explicitly run `npm run build`.
# ---------------------------------------------------------------------------
_STATIC_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
)

if os.path.isdir(_STATIC_DIR):
    if hasattr(app, "frontend"):
        app.frontend("/", directory=_STATIC_DIR, fallback="index.html")
    else:  # pragma: no cover - FastAPI builds older than app.frontend()
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="frontend")