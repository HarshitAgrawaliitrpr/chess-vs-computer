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


# ---------------------------------------------------------------------------
# Accounts + game history (Turso/libSQL backed)
# ---------------------------------------------------------------------------

AuthProvider = Literal["email", "google", "guest"]
GameOutcome = Literal["win", "loss", "draw"]


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254, description="Email address (unique).")
    name: str = Field(..., min_length=1, max_length=60, description="Display name.")
    password: str = Field(..., min_length=8, max_length=128, description="At least 8 characters.")


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(..., min_length=10, max_length=8192, description="GIS ID token.")


class GuestLoginRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=40, description="Optional guest display name.")


class UserOut(BaseModel):
    id: str
    email: Optional[str] = None
    name: str
    provider: AuthProvider
    created_at: str


class AuthResponse(BaseModel):
    token: str
    user: UserOut


class AuthConfig(BaseModel):
    """Frontend bootstrap: is Google sign-in available, and with which client id?"""

    google_enabled: bool
    google_client_id: Optional[str] = None


class GameCreate(BaseModel):
    pgn: str = Field(..., min_length=1, max_length=20000)
    result: GameOutcome
    result_detail: Optional[str] = Field(None, max_length=60)
    player_color: Literal["w", "b"]
    difficulty: str = Field(..., min_length=1, max_length=20)
    moves_count: int = Field(0, ge=0, le=500)


class GameOut(BaseModel):
    id: str
    pgn: str
    result: GameOutcome
    result_detail: Optional[str] = None
    player_color: Literal["w", "b"]
    difficulty: str
    moves_count: int
    created_at: str


class LeaderboardEntry(BaseModel):
    """Aggregated player ranking (points = wins + 0.5 * draws)."""

    rank: int
    user_id: str
    name: str
    provider: AuthProvider
    games: int
    wins: int
    draws: int
    losses: int
    points: float
    win_rate: float = Field(..., description="Win percentage, 0-100.")