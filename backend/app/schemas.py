"""Pydantic request/response models for the chess engine API."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Difficulty = Literal["easy", "medium", "hard", "master"]
GameStatus = Literal[
    "active",
    "check",
    "checkmate",
    "stalemate",
    "draw_repetition",
    "draw_50_moves",
    "draw_insufficient_material",
]


class MoveRequest(BaseModel):
    """Ask the engine to play the side to move in `fen`."""

    fen: str = Field(..., description="Board position (FEN) with the computer to move.")
    difficulty: Difficulty = Field("medium", description="Named strength profile.")
    depth: Optional[int] = Field(
        None, ge=1, le=10, description="Override the search depth (1 = easy, 3 = medium, 5+ = hard)."
    )
    time_limit_ms: Optional[int] = Field(
        None, ge=50, le=10_000, description="Override the wall-clock budget for the search."
    )


class MoveInfo(BaseModel):
    uci: str
    san: str
    from_square: str = Field(alias="from")
    to_square: str = Field(alias="to")
    promotion: Optional[str] = None

    model_config = {"populate_by_name": True}


class SearchResultModel(BaseModel):
    move: MoveInfo
    fen: str
    score: int
    score_type: Literal["cp", "mate"]
    mate_in: Optional[int] = None
    depth: int
    nodes: int
    time_ms: float
    pv: List[str] = Field(default_factory=list, description="Principal variation in SAN.")
    difficulty: Difficulty
    elo_estimate: int


class GameOverModel(BaseModel):
    """Returned instead of a move when the position is already finished."""

    move: Optional[MoveInfo] = None
    fen: str
    status: GameStatus
    winner: Optional[Literal["white", "black"]] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str