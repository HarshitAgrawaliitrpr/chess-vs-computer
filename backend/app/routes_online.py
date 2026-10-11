"""Online multiplayer: server-authoritative games over short polling.

Design notes
------------
Vercel's Python functions are stateless request/response (no WebSockets), and
chess is turn-based anyway - so the game lives in Turso and clients poll
``GET /api/online/games/{id}`` every ~2.5s (paused while the tab is hidden).
Every move is validated server-side with python-chess; the client can never
push an illegal position. Finished games are written into `games` for BOTH
players with ``difficulty='online'`` so history and the leaderboard light up
without any extra plumbing.

Endpoints (all JWT-authenticated):
    POST /api/online/games           create a game -> invite code (white)
    POST /api/online/games/join      join by 6-char code (black)
    GET  /api/online/games/{id}      poll full state (participants only)
    POST /api/online/games/{id}/move   apply your move (validated)
    POST /api/online/games/{id}/resign lose on purpose
    POST /api/online/games/{id}/cancel abort a waiting game (creator)
"""

from __future__ import annotations

import io
import secrets
from typing import Dict, List, Optional, Tuple

import chess
import chess.pgn
from fastapi import APIRouter, Depends, HTTPException

from . import db, security, store
from .schemas import OnlineGameOut, OnlineJoinRequest, OnlineMoveRequest

router = APIRouter(prefix="/api/online/games", tags=["online"])

_DB_UNAVAILABLE = "Database unavailable - set DATABASE_URL (Turso) to enable online play."

# Unambiguous alphabet: no 0/O and no 1/I/L, 32^6 ~= 1 billion codes.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _replay(pgn: str) -> chess.Board:
    """Rebuild the board WITH its move history (needed for threefold repetition)."""
    if not pgn.strip():
        return chess.Board()
    game = chess.pgn.read_game(io.StringIO(pgn))
    board = game.board()
    for move in game.mainline_moves():
        board.push(move)
    return board


def _terminal(board: chess.Board) -> Tuple[str, Optional[str], Optional[str]]:
    """Return (status, winner, result_detail) after a move has been pushed."""
    if board.is_checkmate():
        winner = "w" if board.turn == chess.BLACK else "b"
        return "over", winner, "checkmate"
    if board.is_stalemate():
        return "over", None, "stalemate"
    if board.is_insufficient_material():
        return "over", None, "insufficient material"
    if board.is_repetition():
        return "over", None, "threefold repetition"
    if board.halfmove_clock >= 100:
        return "over", None, "fifty-move rule"
    return "active", None, None


def _my_color(game: Dict, user_id: str) -> Optional[str]:
    if game["white_id"] == user_id:
        return "w"
    if game["black_id"] == user_id:
        return "b"
    return None


def _require_game(game_id: str, user: Dict) -> Dict:
    """Fetch a game the requester is a participant of (404 otherwise)."""
    try:
        game = store.get_online_game(game_id)
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    if game is None or _my_color(game, user["id"]) is None:
        # Do not leak the existence of other players' games.
        raise HTTPException(status_code=404, detail="Game not found.")
    return game


def _names(game: Dict) -> Tuple[str, Optional[str]]:
    white = store.get_user(game["white_id"])
    black = store.get_user(game["black_id"]) if game["black_id"] else None
    white_name = white["name"] if white else "White"
    black_name = black["name"] if black else None
    return white_name, black_name


def _to_out(game: Dict, viewer_id: str) -> OnlineGameOut:
    white_name, black_name = _names(game)
    my_color = _my_color(game, viewer_id) or "w"
    opponent = black_name if my_color == "w" else white_name

    pgn = game["pgn"]
    if pgn.strip():
        parsed = chess.pgn.read_game(io.StringIO(pgn))
        sans: List[str] = [node.san() for node in parsed.mainline()]
        board = parsed.board()
        for move in parsed.mainline_moves():
            board.push(move)
    else:
        sans = []
        board = chess.Board()

    result = None
    if game["status"] == "over":
        winner = game["winner"]
        result = "draw" if not winner else ("win" if winner == my_color else "loss")

    return OnlineGameOut(
        id=game["id"],
        code=game["code"],
        status=game["status"],
        fen=game["fen"],
        pgn=pgn,
        moves=sans,
        last_move=game["last_uci"],
        my_color=my_color,
        white_name=white_name,
        black_name=black_name,
        opponent_name=opponent,
        turn="w" if board.turn == chess.WHITE else "b",
        winner=game["winner"],
        result=result,
        result_detail=game["result_detail"],
        created_at=game["created_at"],
        updated_at=game["updated_at"],
    )


def _record_result(game: Dict, pgn: str, moves_count: int) -> None:
    """Write the finished game into `games` for both players."""
    white_name, black_name = _names(game)
    store.record_online_game_results(
        white_id=game["white_id"],
        black_id=game["black_id"],
        white_name=white_name,
        black_name=black_name,
        pgn=pgn,
        moves_count=moves_count,
        winner=game["winner"],
        result_detail=game["result_detail"],
    )


def _commit(
    game: Dict,
    *,
    fen: str,
    pgn: str,
    last_uci: Optional[str],
    status: str,
    winner: Optional[str],
    result_detail: Optional[str],
) -> None:
    """Store the new position with optimistic concurrency (stale reads lose)."""
    rows = store.update_online_position(
        game["id"],
        fen=fen,
        pgn=pgn,
        last_uci=last_uci,
        status=status,
        winner=winner,
        result_detail=result_detail,
        expected_fen=game["fen"],
    )
    if rows == 0:
        raise HTTPException(
            status_code=409,
            detail="The position changed while you were moving - refreshed state, try again.",
        )


# ---------------------------------------------------------------------------
# lobby
# ---------------------------------------------------------------------------
@router.post("", response_model=OnlineGameOut, status_code=201)
def create_game(user: Dict = Depends(security.get_current_user)) -> OnlineGameOut:
    for _ in range(4):  # code collisions are ~1 in a billion; retry anyway
        code = _generate_code()
        try:
            game = store.create_online_game(
                white_id=user["id"], code=code, fen=chess.STARTING_FEN, pgn=""
            )
        except db.DatabaseError as exc:
            if store.is_unique_violation(exc):
                continue
            raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
        return _to_out(game, user["id"])
    raise HTTPException(status_code=503, detail="Could not allocate an invite code.")


@router.post("/join", response_model=OnlineGameOut)
def join_game(
    payload: OnlineJoinRequest, user: Dict = Depends(security.get_current_user)
) -> OnlineGameOut:
    code = payload.code.strip().upper()
    try:
        game = store.find_online_game_by_code(code)
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc

    if game is None:
        raise HTTPException(status_code=404, detail="No game with that invite code.")
    if game["white_id"] == user["id"]:
        raise HTTPException(status_code=409, detail="You cannot join your own game.")
    if game["status"] != "waiting":
        raise HTTPException(status_code=409, detail="This game already started or ended.")

    try:
        rows = store.join_online_game(game["id"], user["id"])
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    if rows == 0:
        raise HTTPException(status_code=409, detail="Someone else joined first.")

    joined = store.get_online_game(game["id"])
    return _to_out(joined, user["id"])


# ---------------------------------------------------------------------------
# polling + moves
# ---------------------------------------------------------------------------
@router.get("/{game_id}", response_model=OnlineGameOut)
def game_state(game_id: str, user: Dict = Depends(security.get_current_user)) -> OnlineGameOut:
    return _to_out(_require_game(game_id, user), user["id"])


@router.post("/{game_id}/move", response_model=OnlineGameOut)
def play_move(
    game_id: str,
    payload: OnlineMoveRequest,
    user: Dict = Depends(security.get_current_user),
) -> OnlineGameOut:
    game = _require_game(game_id, user)
    if game["status"] != "active":
        raise HTTPException(status_code=409, detail="This game is not active.")

    my_color = _my_color(game, user["id"])
    board = _replay(game["pgn"])
    if ("w" if board.turn == chess.WHITE else "b") != my_color:
        raise HTTPException(status_code=409, detail="It is not your turn.")

    try:
        move = chess.Move.from_uci(f"{payload.from_square}{payload.to_square}")
        mover = board.piece_at(move.from_square)
        if (
            mover is not None
            and mover.piece_type == chess.PAWN
            and chess.square_rank(move.to_square) in (0, 7)
        ):
            # Auto-queen (matches the engine game); a explicit piece still validated.
            move = chess.Move(
                move.from_square, move.to_square, payload.promotion or chess.QUEEN
            )
        if move not in board.legal_moves:
            raise ValueError("illegal")
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=422, detail="Illegal move.") from exc

    board.push(move)
    status, winner, detail = _terminal(board)
    pgn = str(chess.pgn.Game.from_board(board))
    fen = board.fen()

    _commit(
        game,
        fen=fen,
        pgn=pgn,
        last_uci=move.uci(),
        status=status,
        winner=winner,
        result_detail=detail,
    )
    if status == "over":
        refreshed = store.get_online_game(game_id)
        _record_result(refreshed, pgn, len(board.move_stack))

    return _to_out(store.get_online_game(game_id), user["id"])


@router.post("/{game_id}/resign", response_model=OnlineGameOut)
def resign(game_id: str, user: Dict = Depends(security.get_current_user)) -> OnlineGameOut:
    game = _require_game(game_id, user)
    if game["status"] != "active":
        raise HTTPException(status_code=409, detail="This game is not active.")

    my_color = _my_color(game, user["id"])
    winner = "b" if my_color == "w" else "w"
    _commit(
        game,
        fen=game["fen"],
        pgn=game["pgn"],
        last_uci=game["last_uci"],
        status="over",
        winner=winner,
        result_detail="resignation",
    )
    refreshed = store.get_online_game(game_id)
    _record_result(refreshed, game["pgn"], len(_replay(game["pgn"]).move_stack))
    return _to_out(refreshed, user["id"])


@router.post("/{game_id}/cancel", response_model=OnlineGameOut)
def cancel(game_id: str, user: Dict = Depends(security.get_current_user)) -> OnlineGameOut:
    game = _require_game(game_id, user)  # not a participant -> 404, no leaks
    if game["status"] != "waiting" or game["white_id"] != user["id"]:
        raise HTTPException(
            status_code=409, detail="Only the creator can cancel a game that has not started."
        )
    try:
        store.cancel_online_game(game_id, user["id"])
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    return _to_out(store.get_online_game(game_id), user["id"])
